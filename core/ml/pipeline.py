# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end machine learning pipeline orchestration for GeoSync."""

from __future__ import annotations

import logging
import math
import statistics
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import mlflow
except Exception:  # pragma: no cover - fallback when MLflow is absent
    mlflow = None

try:  # pragma: no cover - optional dependency
    import optuna
except Exception:  # pragma: no cover - fallback when Optuna is absent
    optuna = None  # type: ignore[assignment]


FeatureFunction = Callable[["PipelineContext"], Mapping[str, Any]]


@dataclass(slots=True)
class FeatureNode:
    """Single node inside the feature engineering DAG."""

    name: str
    compute: FeatureFunction
    dependencies: tuple[str, ...] = ()
    description: str | None = None


@dataclass(slots=True)
class FeatureEngineeringDAG:
    """Dependency graph coordinating feature generation."""

    nodes: MutableMapping[str, FeatureNode] = field(default_factory=dict)

    def register(self, node: FeatureNode) -> None:
        if node.name in self.nodes:
            raise ValueError(f"Feature node {node.name} already registered")
        self.nodes[node.name] = node

    def _resolve_order(self) -> list[FeatureNode]:
        resolved: list[FeatureNode] = []
        seen: set[str] = set()
        pending = dict(self.nodes)
        while pending:
            progress = False
            for name, node in list(pending.items()):
                if all(dep in seen for dep in node.dependencies):
                    resolved.append(node)
                    seen.add(name)
                    pending.pop(name)
                    progress = True
            if not progress:
                raise RuntimeError("Cyclic dependency detected in feature DAG")
        return resolved

    def run(self, context: "PipelineContext") -> Mapping[str, Mapping[str, Any]]:
        features: dict[str, Mapping[str, Any]] = {}
        for node in self._resolve_order():
            context.logger.debug("Computing feature node %s", node.name)
            result = node.compute(context)
            features[node.name] = result
            context.feature_store[node.name] = result
        return features


@dataclass(slots=True)
class PipelineContext:
    """Shared state passed to feature functions and trainers."""

    training_frame: Any
    validation_frame: Any | None = None
    inference_frame: Any | None = None
    params: MutableMapping[str, Any] = field(default_factory=dict)
    feature_store: MutableMapping[str, Mapping[str, Any]] = field(default_factory=dict)
    logger: logging.Logger = field(default_factory=lambda: LOGGER)


class MLExperimentManager:
    """MLflow-backed experiment lifecycle manager."""

    def __init__(self, experiment_name: str = "GeoSync") -> None:
        self._experiment_name = experiment_name
        self._active_run = None
        if mlflow is not None:
            mlflow.set_experiment(experiment_name)

    def __enter__(self) -> "MLExperimentManager":
        if mlflow is not None:
            self._active_run = mlflow.start_run()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context protocol
        if mlflow is not None and self._active_run is not None:
            mlflow.end_run(status="FAILED" if exc else "FINISHED")
            self._active_run = None

    def log_params(self, params: Mapping[str, Any]) -> None:
        if mlflow is None:
            LOGGER.debug("MLflow unavailable; skipping param logging")
            return
        mlflow.log_params(params)

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        if mlflow is None:
            LOGGER.debug("MLflow unavailable; skipping metric logging")
            return
        mlflow.log_metrics(metrics)

    def log_artifact_json(self, name: str, payload: Mapping[str, Any]) -> None:
        if mlflow is None:
            return
        mlflow.log_dict(payload, f"artifacts/{name}.json")


class OptunaTuner:
    """Hyper-parameter tuning abstraction around Optuna."""

    def __init__(self, objective: Callable[[Mapping[str, Any]], float], n_trials: int = 25) -> None:
        self._objective = objective
        self._n_trials = n_trials

    def optimise(
        self, search_space: Callable[["optuna.trial.Trial"], Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        if optuna is None:
            LOGGER.warning("Optuna not installed; using default parameters")
            return search_space(MockTrial())
        study = optuna.create_study(direction="maximize")

        def _objective(trial: "optuna.trial.Trial") -> float:
            params = search_space(trial)
            return self._objective(params)

        study.optimize(_objective, n_trials=self._n_trials)
        return study.best_params


class MockTrial:
    """Fallback Optuna trial when the dependency is missing."""

    def suggest_float(self, name: str, low: float, high: float, *, log: bool = False) -> float:
        return (low + high) / 2

    def suggest_int(self, name: str, low: int, high: int) -> int:
        return (low + high) // 2

    def suggest_categorical(self, name: str, choices: Sequence[Any]) -> Any:
        return choices[0]


class ABTestManager:
    """Simple online A/B testing harness."""

    def __init__(self) -> None:
        self._metrics: MutableMapping[str, deque[float]] = {}

    def record_metric(self, variant: str, value: float, *, max_points: int = 1_000) -> None:
        series = self._metrics.setdefault(variant, deque(maxlen=max_points))
        series.append(value)

    def lift(self, control: str, treatment: str) -> float:
        control_values = self._metrics.get(control)
        treatment_values = self._metrics.get(treatment)
        if not control_values or not treatment_values:
            return 0.0
        return statistics.fmean(treatment_values) - statistics.fmean(control_values)


class ModelDriftDetector:
    """Detect model drift using Population Stability Index (PSI)."""

    def __init__(self, threshold: float = 0.2) -> None:
        self._threshold = threshold

    def psi(
        self, expected: Sequence[float], observed: Sequence[float], *, buckets: int = 10
    ) -> float:
        if buckets <= 0:
            raise ValueError("buckets must be positive")
        if not expected or not observed:
            return 0.0
        expected_sorted = sorted(expected)
        observed_sorted = sorted(observed)
        if not expected_sorted:
            return 0.0

        quantile_edges: list[float] = []
        for i in range(1, buckets):
            quantile_position = (len(expected_sorted) * i) / buckets
            index = max(0, min(len(expected_sorted) - 1, math.ceil(quantile_position) - 1))
            quantile_edges.append(expected_sorted[index])
        quantile_edges.sort()

        limits = quantile_edges + [math.inf]
        exp_start = 0
        obs_start = 0
        psi_value = 0.0
        for limit in limits:
            exp_end = bisect_right(expected_sorted, limit, exp_start)
            obs_end = bisect_right(observed_sorted, limit, obs_start)
            exp_count = exp_end - exp_start
            obs_count = obs_end - obs_start
            exp_ratio = max(1e-6, exp_count / len(expected_sorted))
            obs_ratio = max(1e-6, obs_count / len(observed_sorted))
            psi_value += (exp_ratio - obs_ratio) * math.log(exp_ratio / obs_ratio)
            exp_start = exp_end
            obs_start = obs_end
        return psi_value

    def is_drifted(self, expected: Sequence[float], observed: Sequence[float]) -> bool:
        return self.psi(expected, observed) >= self._threshold


@dataclass(slots=True)
class PipelineResult:
    model: Any
    metrics: Mapping[str, float]
    params: Mapping[str, Any]


class MLPipeline:
    """Coordinates feature engineering, tuning, training, and deployment."""

    def __init__(
        self,
        feature_dag: FeatureEngineeringDAG,
        train_fn: Callable[[PipelineContext, Mapping[str, Any]], tuple[Any, Mapping[str, float]]],
        *,
        tuner: OptunaTuner | None = None,
        experiment_manager: MLExperimentManager | None = None,
        drift_detector: ModelDriftDetector | None = None,
        ab_tester: ABTestManager | None = None,
    ) -> None:
        self._feature_dag = feature_dag
        self._train_fn = train_fn
        self._tuner = tuner
        self._experiment_manager = experiment_manager
        self._drift_detector = drift_detector
        self._ab_tester = ab_tester

    def run(
        self,
        context: PipelineContext,
        *,
        search_space: Callable[[Any], Mapping[str, Any]] | None = None,
    ) -> PipelineResult:
        features = self._feature_dag.run(context)
        context.logger.info("Generated %s feature groups", len(features))

        params: Mapping[str, Any]
        if self._tuner and search_space is not None:
            params = self._tuner.optimise(search_space)
        else:
            params = context.params

        manager = self._experiment_manager
        if manager is None:
            manager = MLExperimentManager()

        with manager:
            manager.log_params(params)
            model, metrics = self._train_fn(context, params)

            if (
                self._drift_detector
                and {
                    "baseline_scores",
                    "observed_scores",
                }
                <= context.params.keys()
            ):
                expected = context.params["baseline_scores"]
                observed = context.params["observed_scores"]
                drifted, psi_value = detect_model_drift(
                    self._drift_detector,
                    expected_scores=expected,
                    observed_scores=observed,
                )
                metrics = dict(metrics)
                metrics["drift_psi"] = psi_value
                metrics["drift_alert"] = 1.0 if drifted else 0.0

            manager.log_metrics(metrics)
            manager.log_artifact_json(
                "feature_metadata",
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "features": list(features.keys()),
                },
            )

        if self._ab_tester and "ab_variant" in params:
            self._ab_tester.record_metric(params["ab_variant"], metrics.get("sharpe", 0.0))

        return PipelineResult(model=model, metrics=metrics, params=params)


def shadow_mode_inference(
    model_a: Any, model_b: Any, inputs: Iterable[Any]
) -> list[dict[str, Any]]:
    """Run model B in shadow mode alongside model A and capture divergences."""

    results = []
    for payload in inputs:
        pred_a = model_a.predict(payload)
        pred_b = model_b.predict(payload)
        delta = pred_b - pred_a
        results.append({"input": payload, "primary": pred_a, "shadow": pred_b, "delta": delta})
    return results


def record_online_learning_event(
    storage: MutableMapping[str, Any], *, model_id: str, payload: Mapping[str, Any]
) -> None:
    """Persist an online-learning event for replay."""

    events = storage.setdefault(model_id, [])
    events.append({"payload": payload, "recorded_at": datetime.now(timezone.utc).isoformat()})


def detect_model_drift(
    detector: ModelDriftDetector,
    *,
    expected_scores: Sequence[float],
    observed_scores: Sequence[float],
) -> tuple[bool, float]:
    """Utility for quickly checking drift status."""

    psi_value = detector.psi(expected_scores, observed_scores)
    return detector.is_drifted(expected_scores, observed_scores), psi_value


__all__ = [
    "ABTestManager",
    "FeatureEngineeringDAG",
    "MLExperimentManager",
    "MLPipeline",
    "MockTrial",
    "ModelDriftDetector",
    "OptunaTuner",
    "PipelineContext",
    "PipelineResult",
    "detect_model_drift",
    "record_online_learning_event",
    "shadow_mode_inference",
]
