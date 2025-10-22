"""High-level training scenario orchestration for TradePulse models."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import subprocess
import textwrap
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

import numpy as np

try:  # Python 3.11 standard library
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback when stripped
    tomllib = None  # type: ignore[assignment]

try:  # Optional YAML support
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]

from src.data.experiment_registry import ArtifactRecord, ExperimentRegistry, ExperimentRunRecord
from observability.drift import DriftDetector, FeatureDriftSummary, FeatureSnapshot
from observability.finops import Budget, CostReport, FinOpsController, ResourceUsageSample

from core.neuro.training import (
    CheckpointManager,
    TrainingComponent,
    TrainingConfig,
    TrainingEngine,
    TrainingSummary,
)

LOGGER = logging.getLogger(__name__)
UTC = timezone.utc
RUN_ID_PLACEHOLDER = "__RUN_ID_PLACEHOLDER__"

__all__ = [
    "DistributedRunConfig",
    "GPUAutoscalePolicy",
    "CostGuardrailConfig",
    "ValidationRule",
    "ValidationSuiteConfig",
    "RegressionCheckConfig",
    "DriftMonitorConfig",
    "ReportingConfig",
    "TestGenerationConfig",
    "ExperimentConfig",
    "ValidationResult",
    "RegressionCheckResult",
    "AutoscalePlan",
    "ScenarioArtifacts",
    "TrainingScenarioResult",
    "TrainingScenarioRunner",
]


# ---------------------------------------------------------------------------
# Configuration primitives
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DistributedRunConfig:
    """Configuration describing a distributed launch."""

    enabled: bool = False
    backend: str = "auto"
    world_size: int | None = None
    timeout_seconds: int = 180
    init_method: str | None = None
    gradient_sync: bool = True
    auto_backend_priority: tuple[str, ...] = ("nccl", "gloo")

    def resolved_backend(self) -> str | None:
        if not self.enabled:
            return None
        if self.backend != "auto":
            return self.backend
        for candidate in self.auto_backend_priority:
            if candidate == "nccl":
                try:
                    import torch

                    if torch.cuda.is_available():  # pragma: no branch - quick guard
                        return candidate
                except Exception:  # pragma: no cover - torch optional
                    continue
            else:
                return candidate
        return "gloo"


@dataclass(slots=True)
class GPUAutoscalePolicy:
    """Heuristic GPU autoscaler based on profiler statistics."""

    enabled: bool = True
    min_workers: int = 1
    max_workers: int = 8
    target_utilisation: float = 0.7
    scale_out_threshold: float = 0.85
    scale_in_threshold: float = 0.45

    def plan(self, profiling: Mapping[str, Any], *, current_workers: int | None) -> "AutoscalePlan":
        if not self.enabled:
            return AutoscalePlan(
                recommended_workers=current_workers or self.min_workers,
                reason="Autoscaler disabled",
                utilisation=None,
                current_workers=current_workers,
                details={"enabled": False},
            )
        current = current_workers or self.min_workers
        wall_time_total = float(profiling.get("wall_time_total") or 0.0)
        steps = int(profiling.get("steps", 0)) or 1
        wall_time_avg = wall_time_total / max(steps, 1)
        utilisation = None
        if wall_time_avg > 0:
            throughput = 1.0 / wall_time_avg
            utilisation = min(1.0, throughput / max(self.target_utilisation, 1e-6))
        recommended = current
        reason = "Maintaining current capacity"
        if utilisation is not None:
            if utilisation >= self.scale_out_threshold and current < self.max_workers:
                recommended = min(self.max_workers, current + 1)
                reason = "Projected saturation"
            elif utilisation <= self.scale_in_threshold and current > self.min_workers:
                recommended = max(self.min_workers, current - 1)
                reason = "Under-utilised"
        return AutoscalePlan(
            recommended_workers=recommended,
            reason=reason,
            utilisation=utilisation,
            current_workers=current,
            details={
                "wall_time_avg": wall_time_avg,
                "steps": steps,
                "utilisation": utilisation,
            },
        )


@dataclass(slots=True)
class CostGuardrailConfig:
    """Cost limits enforced against profiler-derived estimates."""

    enabled: bool = True
    budget_name: str = "training"
    limit: float = 50.0
    period_hours: float = 24.0
    currency: str = "USD"
    cost_per_gpu_hour: float = 2.5


@dataclass(slots=True, frozen=True)
class ValidationRule:
    """Single validation guardrail."""

    metric: str
    lower: float | None = None
    upper: float | None = None
    strict: bool = True

    def evaluate(self, value: float | None) -> tuple[bool, str | None]:
        if value is None:
            message = "Metric missing"
            return (not self.strict, message)
        if self.lower is not None and value < self.lower:
            return False, f"expected >= {self.lower}, received {value:.6f}"
        if self.upper is not None and value > self.upper:
            return False, f"expected <= {self.upper}, received {value:.6f}"
        return True, None


@dataclass(slots=True)
class ValidationSuiteConfig:
    """Collection of validation rules."""

    rules: tuple[ValidationRule, ...] = ()


@dataclass(slots=True, frozen=True)
class RegressionCheckConfig:
    """Regression guardrail referencing previous experiment runs."""

    metric: str
    tolerance: float
    direction: str = "min"  # "min" or "max"
    strategy: str = "previous"  # "previous" | "best" | "specified"
    baseline_run_id: str | None = None


@dataclass(slots=True)
class DriftMonitorConfig:
    """Parameters for drift monitoring."""

    enabled: bool = True
    psi_threshold: float = 0.2
    ks_confidence: float = 0.95
    bins: int = 10


@dataclass(slots=True)
class ReportingConfig:
    """Controls report generation."""

    enable_markdown: bool = True
    enable_dashboard: bool = True
    publish_to: Path | None = None
    dashboard_name: str = "training_dashboard"


@dataclass(slots=True)
class TestGenerationConfig:
    """Controls auto-generated regression tests."""

    enable: bool = True
    output_dir: Path = Path("reports/training/tests")
    module_prefix: str = "generated"


@dataclass(slots=True)
class ExperimentConfig:
    """Declarative training scenario configuration."""

    experiment_name: str
    training: TrainingConfig
    workspace: Path = Path("reports/training")
    seed: int = 17
    hyperparameters: Mapping[str, Any] = field(default_factory=dict)
    tags: Sequence[str] = field(default_factory=tuple)
    notes: str | None = None
    resume: bool = True
    resume_checkpoint: Path | str | None = None
    distributed: DistributedRunConfig | None = None
    gpu_autoscale: GPUAutoscalePolicy | None = None
    cost_guardrail: CostGuardrailConfig | None = None
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    test_generation: TestGenerationConfig = field(default_factory=TestGenerationConfig)
    drift: DriftMonitorConfig | None = None
    validations: ValidationSuiteConfig = field(default_factory=ValidationSuiteConfig)
    regressions: tuple[RegressionCheckConfig, ...] = ()

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).expanduser().resolve()
        self.test_generation.output_dir = Path(self.test_generation.output_dir).expanduser().resolve()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExperimentConfig":
        payload = dict(payload)
        training_cfg = payload.get("training", {})
        training = training_cfg if isinstance(training_cfg, TrainingConfig) else TrainingConfig(**training_cfg)
        distributed_cfg = payload.get("distributed")
        distributed = DistributedRunConfig(**distributed_cfg) if distributed_cfg else None
        autoscale_cfg = payload.get("gpu_autoscale")
        gpu_autoscale = GPUAutoscalePolicy(**autoscale_cfg) if autoscale_cfg else None
        cost_cfg = payload.get("cost_guardrail")
        cost_guardrail = CostGuardrailConfig(**cost_cfg) if cost_cfg else None
        reporting = ReportingConfig(**(payload.get("reporting") or {}))
        test_generation = TestGenerationConfig(**(payload.get("test_generation") or {}))
        drift_cfg = payload.get("drift")
        drift = DriftMonitorConfig(**drift_cfg) if drift_cfg else None
        validations_cfg = payload.get("validations") or {}
        rules = tuple(ValidationRule(**rule) for rule in validations_cfg.get("rules", []))
        validations = ValidationSuiteConfig(rules=rules)
        regressions_cfg = payload.get("regressions") or []
        regressions = tuple(RegressionCheckConfig(**cfg) for cfg in regressions_cfg)
        return cls(
            experiment_name=payload["experiment_name"],
            training=training,
            workspace=Path(payload.get("workspace", "reports/training")),
            seed=int(payload.get("seed", 17)),
            hyperparameters=payload.get("hyperparameters", {}),
            tags=tuple(payload.get("tags") or ()),
            notes=payload.get("notes"),
            resume=bool(payload.get("resume", True)),
            resume_checkpoint=payload.get("resume_checkpoint"),
            distributed=distributed,
            gpu_autoscale=gpu_autoscale,
            cost_guardrail=cost_guardrail,
            reporting=reporting,
            test_generation=test_generation,
            drift=drift,
            validations=validations,
            regressions=regressions,
        )

    @classmethod
    def from_file(cls, path: Path) -> "ExperimentConfig":
        path = Path(path).expanduser().resolve()
        suffix = path.suffix.lower()
        if suffix in {".toml", ".tml"} and tomllib is not None:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        elif suffix in {".yaml", ".yml"} and yaml is not None:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise TypeError("Experiment configuration must be a mapping")
        return cls.from_mapping(data)

    def resolved_training_config(self) -> TrainingConfig:
        directory = self.training.checkpoint_directory
        if directory is None:
            directory = self.workspace / "checkpoints" / self.experiment_name
        return replace(self.training, checkpoint_directory=directory)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ValidationResult:
    metric: str
    value: float | None
    passed: bool
    message: str | None = None


@dataclass(slots=True)
class RegressionCheckResult:
    metric: str
    baseline_run_id: str | None
    baseline_value: float | None
    current_value: float | None
    tolerance: float
    direction: str
    passed: bool
    message: str


@dataclass(slots=True)
class AutoscalePlan:
    recommended_workers: int
    reason: str
    utilisation: float | None
    current_workers: int | None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScenarioArtifacts:
    base_dir: Path
    summary_path: Path
    report_path: Path | None
    dashboard_path: Path | None
    drift_path: Path | None
    cost_path: Path | None
    autoscale_path: Path | None
    test_path: Path | None


@dataclass(slots=True)
class TrainingScenarioResult:
    run_record: ExperimentRunRecord
    summary: TrainingSummary
    validations: tuple[ValidationResult, ...]
    regressions: tuple[RegressionCheckResult, ...]
    drift: tuple[FeatureDriftSummary, ...]
    autoscale_plan: AutoscalePlan | None
    cost_report: CostReport | None
    artifacts: ScenarioArtifacts
    unit_test_explanation: str | None


# ---------------------------------------------------------------------------
# Scenario runner implementation
# ---------------------------------------------------------------------------


class TrainingScenarioRunner:
    """Coordinate a fully-instrumented training run."""

    def __init__(
        self,
        component: TrainingComponent,
        config: ExperimentConfig,
        registry: ExperimentRegistry,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._component = component
        self._config = config
        self._registry = registry
        self._logger = logger or LOGGER
        self._training_config = config.resolved_training_config()
        self._timestamp = datetime.now(UTC)
        self._workspace = (
            config.workspace / config.experiment_name / self._timestamp.strftime("%Y%m%dT%H%M%S")
        )
        self._workspace.mkdir(parents=True, exist_ok=True)
        checkpoint_dir = Path(self._training_config.checkpoint_directory)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        dataset: Iterable[Any],
        *,
        validation_dataset: Iterable[Any] | None = None,
        validation_fn: Callable[[TrainingComponent, Iterable[Any]], Mapping[str, float]] | None = None,
        drift_snapshots: Sequence[FeatureSnapshot] | None = None,
        training_data_fingerprint: str | None = None,
        resume_checkpoint: Path | str | None = None,
    ) -> TrainingScenarioResult:
        self._logger.info("Launching training scenario for '%s'", self._config.experiment_name)
        self._fix_random_seed(self._config.seed)
        resume_state = self._prepare_resume_state(resume_checkpoint)
        engine = TrainingEngine(self._component, self._training_config)
        with self._distributed_context():
            summary = engine.fit(dataset, resume_state=resume_state)
        self._logger.info("Training finished with %d steps", summary.steps)

        validation_results, validation_metrics = self._run_validations(
            validation_dataset or dataset,
            validation_fn,
        )
        drift_results = self._run_drift_monitor(drift_snapshots)
        cost_report = self._enforce_cost_guardrail(summary)
        autoscale_plan = self._compute_autoscale_plan(summary)
        regression_results = self._evaluate_regressions(validation_metrics, summary)

        summary_metrics = self._collect_metrics(summary, validation_metrics, cost_report, autoscale_plan)
        training_hash = training_data_fingerprint or self._fingerprint_training_data(dataset)

        artifacts = self._persist_artifacts(
            summary=summary,
            validations=validation_results,
            regressions=regression_results,
            drift=drift_results,
            cost_report=cost_report,
            autoscale_plan=autoscale_plan,
            validation_metrics=validation_metrics,
        )

        run_record = self._register_run(
            summary_metrics=summary_metrics,
            summary=summary,
            validations=validation_results,
            regressions=regression_results,
            drift=drift_results,
            cost_report=cost_report,
            autoscale_plan=autoscale_plan,
            artifacts=artifacts,
            training_data_hash=training_hash,
            resume_state=resume_state,
        )

        explanation = self._finalise_artifacts(
            run_record=run_record,
            artifacts=artifacts,
            validations=validation_results,
            regressions=regression_results,
            drift=drift_results,
            cost_report=cost_report,
            autoscale_plan=autoscale_plan,
            validation_metrics=validation_metrics,
        )

        self._publish_results(artifacts)

        return TrainingScenarioResult(
            run_record=run_record,
            summary=summary,
            validations=tuple(validation_results),
            regressions=tuple(regression_results),
            drift=tuple(drift_results),
            autoscale_plan=autoscale_plan,
            cost_report=cost_report,
            artifacts=artifacts,
            unit_test_explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fix_random_seed(self, seed: int) -> None:
        random.seed(seed)
        os.environ["PYTHONHASHSEED"] = str(seed)
        try:
            import numpy as np

            np.random.seed(seed)
        except Exception:  # pragma: no cover - numpy optional
            self._logger.debug("NumPy seeding skipped", exc_info=True)
        try:
            import torch

            torch.manual_seed(seed)
            if torch.cuda.is_available():  # pragma: no branch - guard
                torch.cuda.manual_seed_all(seed)
        except Exception:  # pragma: no cover - torch optional
            self._logger.debug("Torch seeding skipped", exc_info=True)

    def _prepare_resume_state(self, resume_checkpoint: Path | str | None) -> Mapping[str, Any] | None:
        if not self._config.resume:
            return None
        manager = CheckpointManager(
            self._training_config.checkpoint_directory,
            keep_last=self._training_config.keep_last_checkpoints,
        )
        state = manager.resume_state(resume_checkpoint or self._config.resume_checkpoint)
        if state and state.get("state_dict"):
            try:
                self._component.load_state_dict(state["state_dict"])
                self._logger.info("Component state restored from checkpoint %s", state["checkpoint_path"])
            except NotImplementedError:  # pragma: no cover - optional implementation
                self._logger.warning("Component lacks load_state_dict; continuing without state restore")
        return state

    @contextlib.contextmanager
    def _distributed_context(self):
        cfg = self._config.distributed
        if not cfg or not cfg.enabled:
            yield
            return
        backend = cfg.resolved_backend()
        if backend is None:
            self._logger.warning("Distributed backend unavailable; falling back to single process")
            yield
            return
        try:
            import torch.distributed as dist

            if dist.is_initialized():
                yield
                return
            world_size = cfg.world_size or int(os.environ.get("WORLD_SIZE", "1"))
            timeout = timedelta(seconds=cfg.timeout_seconds)
            init_method = cfg.init_method or "env://"
            self._logger.info(
                "Initialising torch.distributed backend=%s world_size=%s",
                backend,
                world_size,
            )
            dist.init_process_group(
                backend=backend,
                world_size=world_size,
                timeout=timeout,
                init_method=init_method,
            )
            try:
                yield
            finally:
                if cfg.gradient_sync:
                    try:
                        dist.barrier()
                    except Exception:  # pragma: no cover - best effort
                        pass
                dist.destroy_process_group()
        except Exception as exc:  # pragma: no cover - torch optional
            self._logger.warning("Distributed initialisation failed: %s", exc)
            yield

    def _run_validations(
        self,
        dataset: Iterable[Any],
        validation_fn: Callable[[TrainingComponent, Iterable[Any]], Mapping[str, float]] | None,
    ) -> tuple[list[ValidationResult], dict[str, float]]:
        metrics: dict[str, float] = {}
        if validation_fn:
            try:
                metrics = {str(k): float(v) for k, v in validation_fn(self._component, dataset).items()}
            except Exception as exc:
                self._logger.exception("Validation function failed", exc_info=exc)
        results: list[ValidationResult] = []
        for rule in self._config.validations.rules:
            value = metrics.get(rule.metric)
            passed, message = rule.evaluate(value)
            results.append(
                ValidationResult(metric=rule.metric, value=value, passed=passed, message=message)
            )
        return results, metrics

    def _run_drift_monitor(self, snapshots: Sequence[FeatureSnapshot] | None) -> list[FeatureDriftSummary]:
        cfg = self._config.drift
        if not cfg or not cfg.enabled or not snapshots:
            return []
        detector = DriftDetector(
            psi_threshold=cfg.psi_threshold,
            ks_confidence=cfg.ks_confidence,
            bins=cfg.bins,
        )
        results: list[FeatureDriftSummary] = []
        for snapshot in snapshots:
            try:
                results.append(detector.evaluate(snapshot))
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.error("Failed to evaluate drift for %s: %s", snapshot.name, exc)
        return results

    def _enforce_cost_guardrail(self, summary: TrainingSummary) -> CostReport | None:
        cfg = self._config.cost_guardrail
        if not cfg or not cfg.enabled:
            return None
        controller = FinOpsController()
        controller.add_budget(
            Budget(
                name=cfg.budget_name,
                limit=cfg.limit,
                period=timedelta(hours=cfg.period_hours),
                currency=cfg.currency,
            )
        )
        world_size = 1
        if self._config.distributed and self._config.distributed.enabled:
            world_size = self._config.distributed.world_size or int(os.environ.get("WORLD_SIZE", "1"))
        duration = float(summary.profiling.get("wall_time_total") or 0.0)
        gpu_hours = duration / 3600.0 * world_size
        cost = gpu_hours * cfg.cost_per_gpu_hour
        sample = ResourceUsageSample(
            resource_id=f"training:{self._config.experiment_name}",
            timestamp=self._timestamp,
            cost=cost,
            usage={"gpu_hours": gpu_hours, "steps": float(summary.steps)},
            metadata={"experiment": self._config.experiment_name},
        )
        controller.record_usage(sample)
        report = controller.analyse_costs(timedelta(hours=cfg.period_hours))
        if report.total_cost > cfg.limit:
            self._logger.warning(
                "Cost guardrail breached: %.2f %s > %.2f",
                report.total_cost,
                cfg.currency,
                cfg.limit,
            )
        return report

    def _compute_autoscale_plan(self, summary: TrainingSummary) -> AutoscalePlan | None:
        policy = self._config.gpu_autoscale
        if not policy:
            return None
        workers = None
        if self._config.distributed and self._config.distributed.enabled:
            workers = self._config.distributed.world_size
        return policy.plan(summary.profiling, current_workers=workers)

    def _evaluate_regressions(
        self,
        validation_metrics: Mapping[str, float],
        summary: TrainingSummary,
    ) -> list[RegressionCheckResult]:
        if not self._config.regressions:
            return []
        history = self._registry.list_runs(self._config.experiment_name)
        latest_metrics: dict[str, float] = {}
        if summary.metrics_history:
            latest_metrics.update(summary.metrics_history[-1])
        latest_metrics.update({f"val_{k}": v for k, v in validation_metrics.items()})
        results: list[RegressionCheckResult] = []
        for check in self._config.regressions:
            baseline: ExperimentRunRecord | None = None
            if check.strategy == "specified" and check.baseline_run_id:
                try:
                    baseline = self._registry.get_run(check.baseline_run_id, experiment_name=self._config.experiment_name)
                except KeyError:
                    baseline = None
            elif check.strategy == "best":
                baseline = self._select_best_run(history, check.metric, check.direction)
            elif history:
                baseline = history[-1]
            baseline_value = baseline.metrics.get(check.metric) if baseline else None
            baseline_run_id = baseline.run_id if baseline else None
            current_value = latest_metrics.get(check.metric) or latest_metrics.get(f"val_{check.metric}")
            passed, message = self._compare_regression(check, baseline_value, current_value)
            results.append(
                RegressionCheckResult(
                    metric=check.metric,
                    baseline_run_id=baseline_run_id,
                    baseline_value=baseline_value,
                    current_value=current_value,
                    tolerance=check.tolerance,
                    direction=check.direction,
                    passed=passed,
                    message=message,
                )
            )
        return results

    def _collect_metrics(
        self,
        summary: TrainingSummary,
        validation_metrics: Mapping[str, float],
        cost_report: CostReport | None,
        autoscale_plan: AutoscalePlan | None,
    ) -> dict[str, float]:
        metrics: dict[str, float] = {}
        if summary.metrics_history:
            metrics.update(summary.metrics_history[-1])
        if summary.loss_history:
            metrics["train_loss"] = summary.loss_history[-1]
        for name, value in validation_metrics.items():
            metrics[f"val_{name}"] = value
        if cost_report:
            metrics["cost_total"] = float(cost_report.total_cost)
            metrics["cost_avg_daily"] = float(cost_report.average_daily_cost)
        if autoscale_plan and autoscale_plan.utilisation is not None:
            metrics["gpu_utilisation"] = float(autoscale_plan.utilisation)
        return metrics

    def _fingerprint_training_data(self, dataset: Iterable[Any]) -> str | None:
        if isinstance(dataset, Sequence):
            hasher = sha256()
            for item in dataset:
                hasher.update(repr(item).encode("utf-8"))
            return hasher.hexdigest()
        return None

    def _persist_artifacts(
        self,
        *,
        summary: TrainingSummary,
        validations: Sequence[ValidationResult],
        regressions: Sequence[RegressionCheckResult],
        drift: Sequence[FeatureDriftSummary],
        cost_report: CostReport | None,
        autoscale_plan: AutoscalePlan | None,
        validation_metrics: Mapping[str, float],
    ) -> ScenarioArtifacts:
        summary_path = self._workspace / "summary.json"
        report_path = self._workspace / "report.md"
        dashboard_path = self._workspace / "dashboard.json"
        drift_path = self._workspace / "drift.json"
        cost_path = self._workspace / "cost.json"
        autoscale_path = self._workspace / "autoscale.json"

        summary_payload = self._build_summary_payload(
            summary=summary,
            validations=validations,
            regressions=regressions,
            drift=drift,
            cost_report=cost_report,
            autoscale_plan=autoscale_plan,
            validation_metrics=validation_metrics,
            run_id=None,
        )
        summary_path.write_text(json.dumps(summary_payload, indent=2, default=self._json_serializer), encoding="utf-8")

        report_file = None
        if self._config.reporting.enable_markdown:
            report_content = self._build_markdown_report(summary_payload)
            report_path.write_text(report_content, encoding="utf-8")
            report_file = report_path

        dashboard_file = None
        if self._config.reporting.enable_dashboard:
            dashboard_spec = self._build_dashboard_spec(summary_payload)
            dashboard_path.write_text(json.dumps(dashboard_spec, indent=2), encoding="utf-8")
            dashboard_file = dashboard_path

        drift_file = None
        if drift:
            drift_payload = [self._drift_summary_to_dict(item) for item in drift]
            drift_path.write_text(json.dumps(drift_payload, indent=2), encoding="utf-8")
            drift_file = drift_path

        cost_file = None
        if cost_report:
            cost_path.write_text(json.dumps(self._cost_report_to_dict(cost_report), indent=2), encoding="utf-8")
            cost_file = cost_path

        autoscale_file = None
        if autoscale_plan:
            autoscale_path.write_text(json.dumps(asdict(autoscale_plan), indent=2, default=self._json_serializer), encoding="utf-8")
            autoscale_file = autoscale_path

        test_file = None
        if self._config.test_generation.enable:
            tests_dir = self._config.test_generation.output_dir / self._config.test_generation.module_prefix
            tests_dir.mkdir(parents=True, exist_ok=True)
            test_file = tests_dir / f"test_{self._timestamp.strftime('%Y%m%dT%H%M%S')}_{self._config.experiment_name}.py"
            test_file.write_text("\"\"\"Auto-generated placeholder\"\"\"\n", encoding="utf-8")

        return ScenarioArtifacts(
            base_dir=self._workspace,
            summary_path=summary_path,
            report_path=report_file,
            dashboard_path=dashboard_file,
            drift_path=drift_file,
            cost_path=cost_file,
            autoscale_path=autoscale_file,
            test_path=test_file,
        )

    def _register_run(
        self,
        *,
        summary_metrics: Mapping[str, float],
        summary: TrainingSummary,
        validations: Sequence[ValidationResult],
        regressions: Sequence[RegressionCheckResult],
        drift: Sequence[FeatureDriftSummary],
        cost_report: CostReport | None,
        autoscale_plan: AutoscalePlan | None,
        artifacts: ScenarioArtifacts,
        training_data_hash: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> ExperimentRunRecord:
        artifact_records: list[ArtifactRecord] = [
            ArtifactRecord(name="summary", uri=str(artifacts.summary_path), kind="report"),
        ]
        if artifacts.report_path:
            artifact_records.append(
                ArtifactRecord(name="report", uri=str(artifacts.report_path), kind="markdown")
            )
        if artifacts.dashboard_path:
            artifact_records.append(
                ArtifactRecord(name=self._config.reporting.dashboard_name, uri=str(artifacts.dashboard_path), kind="dashboard")
            )
        if artifacts.drift_path:
            artifact_records.append(
                ArtifactRecord(name="drift", uri=str(artifacts.drift_path), kind="metrics")
            )
        if artifacts.cost_path:
            artifact_records.append(
                ArtifactRecord(name="cost", uri=str(artifacts.cost_path), kind="metrics")
            )
        if artifacts.autoscale_path:
            artifact_records.append(
                ArtifactRecord(name="autoscale_plan", uri=str(artifacts.autoscale_path), kind="plan")
            )
        if artifacts.test_path:
            artifact_records.append(
                ArtifactRecord(name="regression_tests", uri=str(artifacts.test_path), kind="tests")
            )

        tags = set(self._config.tags)
        if self._training_config.mixed_precision:
            tags.add("mixed_precision")
        if self._training_config.gradient_accumulation_steps > 1:
            tags.add("grad_accum")
        if self._config.distributed and self._config.distributed.enabled:
            tags.add("distributed")

        notes_sections: list[str] = []
        if self._config.notes:
            notes_sections.append(self._config.notes)
        failing_regressions = [result for result in regressions if not result.passed]
        if failing_regressions:
            notes_sections.append(
                "Failed regressions: " + ", ".join(result.metric for result in failing_regressions)
            )
        drifted = [result.feature for result in drift if result.drifted]
        if drifted:
            notes_sections.append("Drift detected for: " + ", ".join(drifted))
        notes = "\n".join(notes_sections) if notes_sections else None

        try:
            git_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
                text=True,
            )
            revision = git_result.stdout.strip()
        except Exception:  # pragma: no cover - git optional
            revision = None

        parent_run_id = None
        for result in regressions:
            if result.baseline_run_id:
                parent_run_id = result.baseline_run_id
                break

        return self._registry.register_run(
            self._config.experiment_name,
            params=dict(self._config.hyperparameters),
            metrics=summary_metrics,
            artifacts=artifact_records,
            tags=tags,
            notes=notes,
            parent_run_id=parent_run_id,
            training_data_hash=training_data_hash,
            code_revision=revision,
        )

    def _finalise_artifacts(
        self,
        *,
        run_record: ExperimentRunRecord,
        artifacts: ScenarioArtifacts,
        validations: Sequence[ValidationResult],
        regressions: Sequence[RegressionCheckResult],
        drift: Sequence[FeatureDriftSummary],
        cost_report: CostReport | None,
        autoscale_plan: AutoscalePlan | None,
        validation_metrics: Mapping[str, float],
    ) -> str | None:
        summary_payload = self._build_summary_payload(
            summary=run_record.reproducibility_manifest(),
            validations=validations,
            regressions=regressions,
            drift=drift,
            cost_report=cost_report,
            autoscale_plan=autoscale_plan,
            validation_metrics=validation_metrics,
            run_id=run_record.run_id,
        )
        artifacts.summary_path.write_text(json.dumps(summary_payload, indent=2, default=self._json_serializer), encoding="utf-8")

        explanation = None
        if artifacts.test_path and self._config.test_generation.enable:
            explanation = self._render_tests(
                run_record=run_record,
                summary_path=artifacts.summary_path,
                validations=validations,
                regressions=regressions,
                validation_metrics=validation_metrics,
                test_path=artifacts.test_path,
            )
        return explanation

    def _publish_results(self, artifacts: ScenarioArtifacts) -> None:
        target = self._config.reporting.publish_to
        if not target:
            return
        target = Path(target).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        for path in [
            artifacts.summary_path,
            artifacts.report_path,
            artifacts.dashboard_path,
            artifacts.drift_path,
            artifacts.cost_path,
            artifacts.autoscale_path,
        ]:
            if path is None:
                continue
            destination = target / path.name
            destination.write_bytes(path.read_bytes())

    def _build_summary_payload(
        self,
        *,
        summary: TrainingSummary | Mapping[str, Any],
        validations: Sequence[ValidationResult],
        regressions: Sequence[RegressionCheckResult],
        drift: Sequence[FeatureDriftSummary],
        cost_report: CostReport | None,
        autoscale_plan: AutoscalePlan | None,
        validation_metrics: Mapping[str, float],
        run_id: str | None,
    ) -> dict[str, Any]:
        if isinstance(summary, TrainingSummary):
            training_payload = {
                "epochs_completed": summary.epochs_completed,
                "steps": summary.steps,
                "loss_history": summary.loss_history,
                "metrics_history": summary.metrics_history,
                "profiling": summary.profiling,
                "checkpoints": [str(path) for path in summary.checkpoints],
                "resumed_from": str(summary.resumed_from) if summary.resumed_from else None,
                "start_epoch": summary.start_epoch,
                "start_step": summary.start_step,
            }
        else:
            training_payload = dict(summary)
        return {
            "experiment": {
                "name": self._config.experiment_name,
                "run_id": run_id or RUN_ID_PLACEHOLDER,
                "timestamp": self._timestamp.isoformat(),
                "hyperparameters": dict(self._config.hyperparameters),
                "tags": sorted(self._config.tags),
            },
            "training": training_payload,
            "validations": {
                "metrics": dict(validation_metrics),
                "results": [asdict(result) for result in validations],
            },
            "regressions": [asdict(result) for result in regressions],
            "drift": [self._drift_summary_to_dict(item) for item in drift],
            "cost": self._cost_report_to_dict(cost_report) if cost_report else None,
            "autoscale": asdict(autoscale_plan) if autoscale_plan else None,
            "artifacts": {
                "workspace": str(self._workspace),
            },
        }

    def _build_markdown_report(self, payload: Mapping[str, Any]) -> str:
        lines: list[str] = []
        lines.append(f"# Experiment {payload['experiment']['name']}")
        lines.append("")
        lines.append(f"- Run ID: {payload['experiment']['run_id']}")
        lines.append(f"- Timestamp: {payload['experiment']['timestamp']}")
        lines.append("")
        lines.append("## Training Summary")
        lines.append(f"Steps: {payload['training'].get('steps')}")
        if payload["training"].get("loss_history"):
            lines.append(f"Final loss: {payload['training']['loss_history'][-1]:.6f}")
        lines.append("")
        if payload["validations"]["results"]:
            lines.append("## Validation Guardrails")
            for entry in payload["validations"]["results"]:
                status = "✅" if entry["passed"] else "❌"
                message = entry.get("message") or "within bounds"
                lines.append(f"- {status} {entry['metric']}: {entry.get('value')} ({message})")
            lines.append("")
        if payload["regressions"]:
            lines.append("## Regression Checks")
            for entry in payload["regressions"]:
                status = "✅" if entry["passed"] else "❌"
                message = entry.get("message", "")
                lines.append(
                    f"- {status} {entry['metric']} vs baseline {entry.get('baseline_run_id')}: {message}"
                )
            lines.append("")
        if payload["drift"]:
            lines.append("## Drift Monitoring")
            for entry in payload["drift"]:
                status = "⚠️" if entry["drifted"] else "✅"
                lines.append(f"- {status} {entry['feature']} (severity={entry['worst_severity']})")
            lines.append("")
        if payload["cost"]:
            cost = payload["cost"]
            lines.append("## Cost Summary")
            lines.append(f"Total cost: {cost['total_cost']:.2f} {cost['currency']}")
            lines.append(f"Average daily cost: {cost['average_daily_cost']:.2f} {cost['currency']}")
            lines.append("")
        if payload.get("autoscale"):
            plan = payload["autoscale"]
            lines.append("## Autoscale Recommendation")
            lines.append(
                f"Recommended workers: {plan['recommended_workers']} (reason: {plan['reason']})"
            )
            if plan.get("utilisation") is not None:
                lines.append(f"Observed utilisation: {plan['utilisation']:.2f}")
            lines.append("")
        return "\n".join(lines)

    def _build_dashboard_spec(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "title": f"{self._config.experiment_name} – Training Overview",
            "generated_at": self._timestamp.isoformat(),
            "widgets": [
                {
                    "type": "stat",
                    "name": "Steps",
                    "value": payload["training"].get("steps", 0),
                },
                {
                    "type": "stat",
                    "name": "Final loss",
                    "value": payload["training"].get("loss_history", [None])[-1],
                },
                {
                    "type": "table",
                    "name": "Validation metrics",
                    "headers": ["metric", "value", "status"],
                    "rows": [
                        [
                            entry["metric"],
                            entry.get("value"),
                            "pass" if entry["passed"] else "fail",
                        ]
                        for entry in payload["validations"]["results"]
                    ],
                },
            ],
        }

    def _drift_summary_to_dict(self, summary: FeatureDriftSummary) -> dict[str, Any]:
        metrics_payload: list[dict[str, Any]] = []
        for metric in summary.metrics:
            details = {
                key: float(value) if isinstance(value, (int, float, np.floating)) else value
                for key, value in metric.details.items()
            }
            metrics_payload.append(
                {
                    "feature": metric.feature,
                    "metric": metric.metric,
                    "value": float(metric.value),
                    "threshold": float(metric.threshold),
                    "drifted": bool(metric.drifted),
                    "details": details,
                }
            )
        return {
            "feature": summary.feature,
            "metrics": metrics_payload,
            "drifted": bool(summary.drifted),
            "metadata": {key: value for key, value in summary.metadata.items()},
            "worst_severity": summary.worst_severity,
        }

    def _cost_report_to_dict(self, report: CostReport) -> dict[str, Any]:
        return {
            "total_cost": float(report.total_cost),
            "average_daily_cost": float(report.average_daily_cost),
            "currency": getattr(report, "currency", self._config.cost_guardrail.currency if self._config.cost_guardrail else "USD"),
            "window_start": report.window_start.isoformat(),
            "window_end": report.window_end.isoformat(),
            "resource_costs": dict(report.resource_costs),
            "usage_totals": dict(report.usage_totals),
        }

    def _render_tests(
        self,
        *,
        run_record: ExperimentRunRecord,
        summary_path: Path,
        validations: Sequence[ValidationResult],
        regressions: Sequence[RegressionCheckResult],
        validation_metrics: Mapping[str, float],
        test_path: Path,
    ) -> str:
        relative_summary = Path(os.path.relpath(summary_path, test_path.parent))
        guardrails: dict[str, MutableMapping[str, float | None]] = {}
        for result in validations:
            guardrails[result.metric] = {
                "value": result.value,
                "passed": result.passed,
                "message": result.message,
            }
        regression_specs: list[dict[str, Any]] = []
        for result in regressions:
            regression_specs.append(
                {
                    "metric": result.metric,
                    "baseline_run_id": result.baseline_run_id,
                    "baseline_value": result.baseline_value,
                    "current_value": result.current_value,
                    "tolerance": result.tolerance,
                    "direction": result.direction,
                    "passed": result.passed,
                }
            )
        explanation = textwrap.dedent(
            """\
            These tests were generated automatically for experiment '{name}' (run {run_id}).
            They ensure validation metrics remain within configured guardrails and
            regression checks respect declared tolerances.
            """
        ).format(name=run_record.experiment_name, run_id=run_record.run_id).strip()
        guardrails_literal = repr({key: dict(value) for key, value in guardrails.items()})
        regression_literal = repr(regression_specs)
        template = textwrap.dedent(
            '''"""{explanation}"""

            from __future__ import annotations

            import json
            from pathlib import Path

            import pytest

            SUMMARY_PATH = Path(__file__).resolve().parent / Path({summary_path_literal})


            def _load_summary() -> dict[str, object]:
                return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


            def test_summary_contains_run_identifier() -> None:
                data = _load_summary()
                experiment = data["experiment"]
                assert experiment["run_id"] and experiment["run_id"] != {placeholder!r}


            GUARDRAILS = {guardrails_literal}


            def test_validation_guardrails() -> None:
                data = _load_summary()
                metrics = data["validations"]["metrics"]
                for metric, spec in GUARDRAILS.items():
                    value = metrics.get(metric)
                    if spec.get("passed"):
                        assert value is not None, f"metric {{metric}} missing"
                    else:
                        pytest.skip(f"Guardrail for {{metric}} intentionally failing: {{spec.get('message')}}")


            REGRESSION_CHECKS = {regression_literal}


            def test_regression_guardrails() -> None:
                if not REGRESSION_CHECKS:
                    pytest.skip("No regression checks configured")
                data = _load_summary()
                history = data["training"].get("metrics_history", [{{}}])
                latest = history[-1] if history else {{}}
                metrics = {{**latest, **data["validations"]["metrics"]}}
                for check in REGRESSION_CHECKS:
                    metric = check.get("metric")
                    baseline = check.get("baseline_value")
                    current = metrics.get(metric) or metrics.get(f"val_{{metric}}")
                    if baseline is None or current is None:
                        continue
                    tolerance = check.get("tolerance", 0.0)
                    if check.get("direction") == "min":
                        assert current <= baseline + tolerance, f"{{metric}} regressed beyond tolerance"
                    else:
                        assert current >= baseline - tolerance, f"{{metric}} regressed beyond tolerance"
            '''
        )
        content = template.format(
            explanation=explanation,
            summary_path_literal=repr(relative_summary.as_posix()),
            placeholder=RUN_ID_PLACEHOLDER,
            guardrails_literal=guardrails_literal,
            regression_literal=regression_literal,
        )
        test_path.write_text(content, encoding="utf-8")
        return explanation

    def _compare_regression(
        self,
        check: RegressionCheckConfig,
        baseline_value: float | None,
        current_value: float | None,
    ) -> tuple[bool, str]:
        if baseline_value is None or current_value is None:
            return True, "baseline or current value missing"
        if check.direction == "min":
            threshold = baseline_value + check.tolerance
            passed = current_value <= threshold
            message = f"current={current_value:.6f} baseline={baseline_value:.6f} threshold={threshold:.6f}"
        else:
            threshold = baseline_value - check.tolerance
            passed = current_value >= threshold
            message = f"current={current_value:.6f} baseline={baseline_value:.6f} threshold={threshold:.6f}"
        return passed, message

    def _select_best_run(
        self,
        runs: Sequence[ExperimentRunRecord],
        metric: str,
        direction: str,
    ) -> ExperimentRunRecord | None:
        if not runs:
            return None
        best: ExperimentRunRecord | None = None
        for record in runs:
            value = record.metrics.get(metric)
            if value is None:
                continue
            if best is None:
                best = record
                continue
            if direction == "min":
                if value < best.metrics.get(metric, float("inf")):
                    best = record
            else:
                if value > best.metrics.get(metric, float("-inf")):
                    best = record
        return best

    def _json_serializer(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value
