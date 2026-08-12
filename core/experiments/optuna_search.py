# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Optuna-powered hyperparameter search orchestrator for trading strategies.

This module provides a battle-tested orchestration layer around Optuna that is
tailored for GeoSync strategy optimisation.  It combines Bayesian search
(``TPESampler``), structured early stopping via Optuna pruners, cross-validation
aware scoring, registry logging and automatic promotion of the best
configuration once it outperforms a baseline.

The public surface intentionally favours explicit configuration objects so that
call sites remain declarative and the behaviour can be reasoned about during
code reviews.  The implementation is kept side-effect free (beyond interacting
with the experiment registry) to guarantee reproducibility and testability.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, MutableMapping, Protocol

import numpy as np
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from .registry import ArtifactSpec, ModelRegistry

if TYPE_CHECKING:
    from core.agent.strategy import Strategy

LOGGER = logging.getLogger(__name__)


class ParameterSampler(Protocol):
    """Callable responsible for sampling hyperparameters for a trial."""

    def __call__(self, trial: optuna.trial.Trial) -> Mapping[str, Any]: ...


class ObjectiveFunction(Protocol):
    """Objective used during optimisation returning a scalar score."""

    def __call__(self, params: Mapping[str, Any], *, data: Any) -> float: ...


class StrategyFactory(Protocol):
    """Factory producing :class:`~core.agent.strategy.Strategy` instances."""

    def __call__(self, params: Mapping[str, Any], *, name: str) -> "Strategy": ...


@dataclass(slots=True)
class OptunaSearchConfig:
    """Declarative configuration describing how the search should behave."""

    experiment: str
    parameter_sampler: ParameterSampler
    metric_name: str = "score"
    direction: optuna.study.StudyDirection = optuna.study.StudyDirection.MAXIMIZE
    n_trials: int | None = 50
    timeout: float | None = None
    n_splits: int = 4
    random_seed: int | None = None
    n_startup_trials: int = 8
    promotion_threshold: float = 0.0
    baseline_params: Mapping[str, Any] = field(default_factory=dict)
    objective: ObjectiveFunction | None = None
    strategy_factory: StrategyFactory | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.n_trials is not None and self.n_trials <= 0:
            msg = "n_trials must be positive when provided"
            raise ValueError(msg)
        if self.n_splits <= 0:
            msg = "n_splits must be a positive integer"
            raise ValueError(msg)
        if self.n_startup_trials < 0:
            msg = "n_startup_trials must not be negative"
            raise ValueError(msg)
        if (
            self.objective is None and self.strategy_factory is None
        ):  # pragma: no cover - configuration guard
            msg = "Either objective or strategy_factory must be provided"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class HyperparameterSearchResult:
    """Rich result describing the outcome of the optimisation run."""

    best_params: Mapping[str, Any]
    best_score: float
    baseline_score: float
    improvement: float
    improvement_pct: float | None
    promoted: bool
    registry_run_id: str
    study: optuna.study.Study
    trial_history: tuple[Mapping[str, Any], ...]


def _normalise_params(params: Mapping[str, Any]) -> dict[str, Any]:
    normalised: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, (np.floating, float)):
            normalised[key] = float(value)
        elif isinstance(value, (np.integer, int)):
            normalised[key] = int(value)
        elif isinstance(value, Mapping):
            normalised[key] = _normalise_params(value)
        elif isinstance(value, (list, tuple)):
            normalised[key] = [
                (_normalise_params(item) if isinstance(item, Mapping) else _coerce_scalar(item))
                for item in value
            ]
        else:
            normalised[key] = _coerce_scalar(value)
    return normalised


def _coerce_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (set, frozenset)):
        return sorted(_coerce_scalar(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value


def _coerce_json_serialisable(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _coerce_json_serialisable(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_coerce_json_serialisable(item) for item in payload]
    return _coerce_scalar(payload)


def _default_strategy_objective(factory: StrategyFactory) -> ObjectiveFunction:
    from core.agent.strategy import Strategy  # Local import to avoid cycles

    def _objective(params: Mapping[str, Any], *, data: Any) -> float:
        name = params.get("name", "candidate")
        strategy = factory(params, name=name)
        if not isinstance(strategy, Strategy):
            msg = "strategy_factory must return a Strategy instance"
            raise TypeError(msg)
        score = strategy.simulate_performance(data)
        return float(score)

    return _objective


def _slice_time_series(data: Any, n_splits: int) -> list[Any]:
    if n_splits <= 1:
        return [data]

    if hasattr(data, "__len__"):
        length = len(data)
    else:
        data = list(data)
        length = len(data)

    if length == 0:
        raise ValueError("Dataset must contain at least one observation")

    effective_splits = min(n_splits, length)
    base_size = length // effective_splits
    remainder = length % effective_splits

    folds: list[Any] = []
    start = 0
    for index in range(effective_splits):
        fold_size = base_size + (1 if index < remainder else 0)
        end = start + fold_size
        if hasattr(data, "iloc"):
            fold = data.iloc[start:end]
        elif isinstance(data, np.ndarray):
            fold = data[start:end]
        elif isinstance(data, list):
            fold = data[start:end]
        else:
            sequence = list(data)
            fold = sequence[start:end]
        if hasattr(fold, "copy"):
            fold = fold.copy()
        folds.append(fold)
        start = end
    return folds


class StrategyHyperparameterSearch:
    """Run Optuna-driven hyperparameter optimisation for trading strategies."""

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry
        self._trial_history: list[MutableMapping[str, Any]] = []
        self._history_lock = threading.Lock()

    def run(
        self,
        *,
        data: Any,
        config: OptunaSearchConfig,
    ) -> HyperparameterSearchResult:
        objective = config.objective
        if objective is None:
            assert config.strategy_factory is not None  # for type checkers
            objective = _default_strategy_objective(config.strategy_factory)

        folds = _slice_time_series(data, config.n_splits)
        self._trial_history = []

        baseline_scores = [
            self._evaluate_objective(objective, dict(config.baseline_params), fold)
            for fold in folds
        ]
        baseline_score = statistics.fmean(baseline_scores)

        sampler = TPESampler(
            seed=config.random_seed,
            multivariate=True,
            warn_independent_sampling=False,
        )
        pruner = MedianPruner(n_startup_trials=config.n_startup_trials, interval_steps=1)
        study = optuna.create_study(direction=config.direction, sampler=sampler, pruner=pruner)

        optimisation_start = time.perf_counter()

        def _objective_wrapper(trial: optuna.trial.Trial) -> float:
            params = dict(config.parameter_sampler(trial))
            params = _normalise_params(params)
            fold_scores: list[float] = []
            start_time = time.perf_counter()
            for step, fold in enumerate(folds):
                score = self._evaluate_objective(objective, params, fold)
                if not math.isfinite(score):
                    msg = (
                        f"Objective returned a non-finite score for trial {trial.number}: {score!r}"
                    )
                    raise ValueError(msg)
                fold_scores.append(float(score))
                trial.report(float(score), step=step)
                if trial.should_prune():
                    trial.set_user_attr("fold_scores", list(fold_scores))
                    trial.set_user_attr("duration", time.perf_counter() - start_time)
                    raise optuna.TrialPruned()

            aggregate = statistics.fmean(fold_scores)
            trial.set_user_attr("fold_scores", list(fold_scores))
            trial.set_user_attr("duration", time.perf_counter() - start_time)
            trial.set_user_attr("params", params)
            return float(aggregate)

        def _callback(study: optuna.study.Study, trial: optuna.trial.FrozenTrial) -> None:
            payload: MutableMapping[str, Any] = {
                "number": trial.number,
                "state": trial.state.name,
                "value": trial.value,
                "params": trial.params,
                "fold_scores": trial.user_attrs.get("fold_scores", []),
                "duration": trial.user_attrs.get("duration"),
            }
            with self._history_lock:
                self._trial_history.append(payload)

        study.optimize(
            _objective_wrapper,
            n_trials=config.n_trials,
            timeout=config.timeout,
            callbacks=[_callback],
            gc_after_trial=True,
        )

        optimisation_duration = time.perf_counter() - optimisation_start

        if not study.best_trials:
            raise RuntimeError("Optuna study did not complete any trials successfully")

        best_trial = study.best_trial
        best_params = _normalise_params(best_trial.params)
        best_score = float(best_trial.value)
        delta = best_score - float(baseline_score)
        if config.direction == optuna.study.StudyDirection.MINIMIZE:
            improvement = -delta
        else:
            improvement = delta
        improvement_pct: float | None
        if baseline_score == 0.0:
            improvement_pct = None
        else:
            improvement_pct = improvement / abs(float(baseline_score))

        promoted = improvement >= config.promotion_threshold

        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_dir = Path(tmp_dir)
            summary, artifacts = self._persist_artifacts(
                artifact_dir=artifact_dir,
                config=config,
                study=study,
                folds=folds,
                baseline_scores=baseline_scores,
                best_trial=best_trial,
                optimisation_duration=optimisation_duration,
                promoted=promoted,
                improvement=improvement,
                improvement_pct=improvement_pct,
            )

            metrics = {
                config.metric_name: best_score,
                f"baseline_{config.metric_name}": float(baseline_score),
                "improvement": improvement,
            }
            if improvement_pct is not None:
                metrics["improvement_pct"] = improvement_pct

            registry_params = {
                "best_params": best_params,
                "baseline_params": _normalise_params(dict(config.baseline_params)),
            }

            metadata = {
                "n_trials_requested": config.n_trials,
                "timeout": config.timeout,
                "n_trials_completed": sum(
                    1 for trial in study.trials if trial.state == optuna.trial.TrialState.COMPLETE
                ),
                "n_trials_pruned": sum(
                    1 for trial in study.trials if trial.state == optuna.trial.TrialState.PRUNED
                ),
                "n_trials_failed": sum(
                    1 for trial in study.trials if trial.state == optuna.trial.TrialState.FAIL
                ),
                "promotion": {
                    "promoted": promoted,
                    "threshold": config.promotion_threshold,
                },
                "baseline": {
                    "score": float(baseline_score),
                    "fold_scores": list(map(float, baseline_scores)),
                },
                "study": {
                    "sampler": type(study.sampler).__name__,
                    "pruner": type(study.pruner).__name__,
                    "direction": study.direction.name,
                    "duration_seconds": optimisation_duration,
                },
                "summary": summary,
            }

            tags = ["promoted"] if promoted else ["evaluated"]
            run = self._registry.register_run(
                config.experiment,
                parameters=_coerce_json_serialisable(registry_params),
                metrics=_coerce_json_serialisable(metrics),
                artifacts=artifacts,
                tags=tags,
                notes=config.notes,
                metadata=_coerce_json_serialisable(metadata),
            )

        # registry run occurs inside TemporaryDirectory context; ensure run variable defined
        run_id = run.id

        LOGGER.info(
            "Optuna search completed for experiment %s | best_score=%.6f | baseline=%.6f | "
            "improvement=%.6f | promoted=%s",
            config.experiment,
            best_score,
            baseline_score,
            improvement,
            promoted,
        )

        return HyperparameterSearchResult(
            best_params=best_params,
            best_score=best_score,
            baseline_score=float(baseline_score),
            improvement=improvement,
            improvement_pct=improvement_pct,
            promoted=promoted,
            registry_run_id=run_id,
            study=study,
            trial_history=tuple(self._trial_history),
        )

    def _evaluate_objective(
        self,
        objective: ObjectiveFunction,
        params: Mapping[str, Any],
        data: Any,
    ) -> float:
        params_copy = dict(params)
        return float(objective(params_copy, data=data))

    def _persist_artifacts(
        self,
        *,
        artifact_dir: Path,
        config: OptunaSearchConfig,
        study: optuna.study.Study,
        folds: Iterable[Any],
        baseline_scores: Iterable[float],
        best_trial: optuna.trial.FrozenTrial,
        optimisation_duration: float,
        promoted: bool,
        improvement: float,
        improvement_pct: float | None,
    ) -> tuple[dict[str, Any], list[ArtifactSpec]]:
        fold_count = len(folds)
        summary_payload = {
            "experiment": config.experiment,
            "metric": config.metric_name,
            "direction": config.direction.name,
            "folds": fold_count,
            "best_trial": {
                "number": best_trial.number,
                "value": best_trial.value,
                "params": best_trial.params,
            },
            "baseline": {
                "params": dict(config.baseline_params),
                "scores": list(map(float, baseline_scores)),
            },
            "improvement": improvement,
            "improvement_pct": improvement_pct,
            "promotion": {
                "promoted": promoted,
                "threshold": config.promotion_threshold,
            },
            "study_duration_seconds": optimisation_duration,
        }

        trial_history = [
            _coerce_json_serialisable(history)
            for history in sorted(self._trial_history, key=lambda item: int(item["number"]))
        ]

        summary_path = artifact_dir / "study_summary.json"
        history_path = artifact_dir / "trials_history.json"
        best_params_path = artifact_dir / "best_params.json"

        summary_path.write_text(
            json.dumps(_coerce_json_serialisable(summary_payload), indent=2),
            encoding="utf-8",
        )
        history_path.write_text(
            json.dumps(trial_history, indent=2),
            encoding="utf-8",
        )
        best_params_path.write_text(
            json.dumps(_coerce_json_serialisable(best_trial.params), indent=2),
            encoding="utf-8",
        )

        artifacts = [
            ArtifactSpec(
                path=summary_path,
                name="study_summary.json",
                kind="optuna-summary",
                metadata={"experiment": config.experiment},
            ),
            ArtifactSpec(
                path=history_path,
                name="trials_history.json",
                kind="optuna-trials",
                metadata={"experiment": config.experiment},
            ),
            ArtifactSpec(
                path=best_params_path,
                name="best_params.json",
                kind="optuna-params",
                metadata={"experiment": config.experiment},
            ),
        ]

        run_summary = _coerce_json_serialisable(summary_payload)
        return run_summary, artifacts


__all__ = [
    "HyperparameterSearchResult",
    "OptunaSearchConfig",
    "StrategyHyperparameterSearch",
]
