"""Parity coordination utilities across backtest, paper, and live runs.

The helpers defined here provide a structured way to compare strategy results
across execution environments.  They encapsulate the logic required to enforce
metric tolerances, detect code or parameter drift, and surface actionable
reports that downstream orchestration layers (health monitors, deployment
pipelines) can consume.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, MutableMapping, Sequence

from core.utils.metrics import get_metrics_collector

_DEFAULT_METADATA_IGNORES = {"environment", "environment_name"}


class EnvironmentParityError(RuntimeError):
    """Raised when parity checks detect blocking mismatches."""


@dataclass(frozen=True, slots=True)
class MetricTolerance:
    """Absolute and/or relative tolerance allowed for a metric deviation."""

    absolute: float | None = None
    relative: float | None = None

    def allows(self, baseline: float, candidate: float) -> bool:
        """Return ``True`` when ``candidate`` is within tolerance of ``baseline``."""

        difference = abs(candidate - baseline)
        if self.absolute is not None and difference > self.absolute:
            return False

        if self.relative is not None:
            scale = max(abs(baseline), abs(candidate), 1.0)
            if difference > self.relative * scale:
                return False

        return True


def _normalise_mapping(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    normalised: MutableMapping[str, Any] = {}
    for key, value in mapping.items():
        normalised[str(key)] = _normalise_value(value)
    return normalised


def _normalise_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _normalise_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_normalise_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def compute_parameters_digest(parameters: Mapping[str, Any]) -> str:
    """Return a deterministic SHA256 digest for *parameters*."""

    canonical = json.dumps(
        _normalise_mapping(parameters),
        sort_keys=True,
        separators=(",", ":"),
        default=lambda obj: repr(obj),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_code_digest(target: Any) -> str:
    """Return a SHA256 digest for the source code associated with *target*."""

    if isinstance(target, (str, Path)):
        path = Path(target)
        if not path.exists():  # pragma: no cover - defensive guard
            raise FileNotFoundError(f"Strategy source not found at {path!s}")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    try:
        source = inspect.getsource(target)
    except (OSError, TypeError):
        source_path = inspect.getsourcefile(target)
        if not source_path:
            raise TypeError(f"Cannot determine source for object: {target!r}")
        return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()

    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StrategyRunSnapshot:
    """Immutable snapshot describing a strategy evaluation in an environment."""

    environment: str
    strategy: str
    metrics: Mapping[str, float] = field(default_factory=dict)
    timestamp: datetime | None = None
    code_digest: str | None = None
    parameters_digest: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.environment:
            raise ValueError("environment must be provided")
        if not self.strategy:
            raise ValueError("strategy must be provided")

        normalised_env = str(self.environment).strip().lower()
        object.__setattr__(self, "environment", normalised_env)

        cleaned_metrics: MutableMapping[str, float] = {}
        for key, value in dict(self.metrics).items():
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            cleaned_metrics[str(key)] = numeric
        object.__setattr__(
            self, "metrics", MappingProxyType(dict(sorted(cleaned_metrics.items())))
        )

        cleaned_metadata = {
            str(key): value for key, value in dict(self.metadata).items()
        }
        object.__setattr__(self, "metadata", MappingProxyType(cleaned_metadata))

    @classmethod
    def from_performance_report(
        cls,
        environment: str,
        strategy: str,
        report: Any,
        *,
        timestamp: datetime | None = None,
        code_digest: str | None = None,
        parameters_digest: str | None = None,
        extra_metrics: Mapping[str, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyRunSnapshot:
        """Build a snapshot from a :class:`backtest.performance.PerformanceReport`."""

        metrics: MutableMapping[str, float] = {}
        if hasattr(report, "as_dict"):
            metrics.update(
                {
                    key: float(value)
                    for key, value in report.as_dict().items()
                    if value is not None
                }
            )

        if extra_metrics:
            for key, value in extra_metrics.items():
                if value is None:
                    continue
                metrics[str(key)] = float(value)

        return cls(
            environment=environment,
            strategy=strategy,
            metrics=metrics,
            timestamp=timestamp,
            code_digest=code_digest,
            parameters_digest=parameters_digest,
            metadata=metadata or {},
        )

    def get_metric(self, name: str) -> float | None:
        """Return the metric value associated with *name* if available."""

        return self.metrics.get(name)

    @property
    def metric_names(self) -> tuple[str, ...]:
        """Return the metric names tracked by the snapshot."""

        return tuple(self.metrics.keys())


@dataclass(frozen=True, slots=True)
class MetricDeviation:
    """Deviation observed between two environments for a single metric."""

    metric: str
    baseline_environment: str
    comparison_environment: str
    baseline_value: float
    comparison_value: float
    absolute_difference: float
    relative_difference: float

    @property
    def comparison_label(self) -> str:
        return f"{self.baseline_environment}->{self.comparison_environment}"


@dataclass(slots=True)
class EnvironmentParityConfig:
    """Configuration governing environment parity evaluation."""

    baseline_environment: str = "backtest"
    required_environments: tuple[str, ...] = ("backtest", "paper", "live")
    comparison_pairs: tuple[tuple[str, str], ...] | None = None
    metric_tolerances: Mapping[str, MetricTolerance] = field(default_factory=dict)
    default_tolerance: MetricTolerance = field(
        default_factory=lambda: MetricTolerance(relative=0.005)
    )
    required_metrics: tuple[str, ...] | None = None
    optional_metrics: tuple[str, ...] = ()
    excluded_metrics: tuple[str, ...] = ()
    require_code_digest: bool = True
    require_parameter_digest: bool = True
    metadata_keys: tuple[str, ...] = ()
    allow_missing_metrics: bool = False


@dataclass(slots=True)
class EnvironmentParityReport:
    """Structured outcome returned by :class:`EnvironmentParityChecker`."""

    strategy: str
    baseline_environment: str
    comparison_pairs: tuple[tuple[str, str], ...]
    snapshots: Mapping[str, StrategyRunSnapshot]
    missing_environments: tuple[str, ...]
    missing_metrics: Mapping[str, tuple[str, ...]]
    metric_deviations: tuple[MetricDeviation, ...]
    optional_missing_metrics: Mapping[str, tuple[str, ...]]
    code_digests: Mapping[str, str | None]
    parameter_digests: Mapping[str, str | None]
    metadata_drift: Mapping[str, Mapping[str, Any]]
    status: str

    @property
    def ok(self) -> bool:
        """Return ``True`` when no blocking issues were detected."""

        return self.status == "pass"

    def raise_for_failure(self) -> None:
        """Raise :class:`EnvironmentParityError` when the report failed."""

        if self.status != "fail":
            return

        parts: list[str] = []
        if self.missing_environments:
            missing = ", ".join(self.missing_environments)
            parts.append(f"Missing environments: {missing}")
        if self.missing_metrics:
            detail = ", ".join(
                f"{env}({', '.join(metrics)})"
                for env, metrics in self.missing_metrics.items()
            )
            parts.append(f"Missing metrics: {detail}")
        if self.metric_deviations:
            sample = self.metric_deviations[0]
            parts.append(
                f"Deviation {sample.metric} {sample.comparison_label} = {sample.absolute_difference:.4g}"
            )
        if self.metadata_drift:
            drift_keys = ", ".join(sorted(self.metadata_drift.keys()))
            parts.append(f"Metadata drift: {drift_keys}")
        if len({value for value in self.code_digests.values() if value} or []) > 1:
            parts.append("Strategy code digest mismatch")
        if len({value for value in self.parameter_digests.values() if value} or []) > 1:
            parts.append("Strategy parameter digest mismatch")

        message = "; ".join(parts) if parts else "Environment parity failed"
        raise EnvironmentParityError(message)


class EnvironmentParityChecker:
    """Evaluate strategy consistency across environments."""

    def __init__(self) -> None:
        self._metrics = get_metrics_collector()

    def evaluate(
        self,
        snapshots: Sequence[StrategyRunSnapshot],
        config: EnvironmentParityConfig | None = None,
    ) -> EnvironmentParityReport:
        if not snapshots:
            raise ValueError("At least one snapshot is required for parity evaluation")

        config = config or EnvironmentParityConfig()
        env_map: dict[str, StrategyRunSnapshot] = {
            snapshot.environment: snapshot for snapshot in snapshots
        }

        strategy_names = {snapshot.strategy for snapshot in snapshots}
        if len(strategy_names) != 1:
            raise ValueError("Snapshots must refer to the same strategy")
        strategy = strategy_names.pop()

        missing_envs = tuple(
            env for env in config.required_environments if env not in env_map
        )

        baseline_snapshot = env_map.get(config.baseline_environment)

        excluded = set(config.excluded_metrics)
        optional = set(config.optional_metrics) - excluded
        if config.required_metrics is not None:
            required_metrics = set(config.required_metrics) - excluded
        elif baseline_snapshot is not None:
            required_metrics = set(baseline_snapshot.metric_names) - excluded
        else:
            required_metrics = set()

        required_metrics.update(
            metric
            for metric in config.metric_tolerances.keys()
            if metric not in excluded
        )

        missing_metrics: MutableMapping[str, tuple[str, ...]] = {}
        optional_missing: MutableMapping[str, tuple[str, ...]] = {}

        for environment in config.required_environments:
            snapshot = env_map.get(environment)
            if snapshot is None:
                continue
            missing = sorted(
                metric for metric in required_metrics if metric not in snapshot.metrics
            )
            optional_absent = sorted(
                metric for metric in optional if metric not in snapshot.metrics
            )
            if missing:
                missing_metrics[environment] = tuple(missing)
            if optional_absent:
                optional_missing[environment] = tuple(optional_absent)

        if config.comparison_pairs is not None:
            pairs = config.comparison_pairs
        else:
            ordered = [env for env in config.required_environments if env in env_map]
            pairs_list: list[tuple[str, str]] = []
            for env in ordered:
                if env == config.baseline_environment:
                    continue
                pairs_list.append((config.baseline_environment, env))
            if len(ordered) > 1:
                for left, right in combinations(ordered, 2):
                    if (
                        left,
                        right,
                    ) not in pairs_list and left != config.baseline_environment:
                        pairs_list.append((left, right))
            pairs = tuple(pairs_list)

        deviations: list[MetricDeviation] = []
        for left_env, right_env in pairs:
            left_snapshot = env_map.get(left_env)
            right_snapshot = env_map.get(right_env)
            if left_snapshot is None or right_snapshot is None:
                continue

            metric_names = required_metrics | (
                set(left_snapshot.metric_names) | set(right_snapshot.metric_names)
            )
            metric_names -= excluded
            for metric in sorted(metric_names):
                left_value = left_snapshot.get_metric(metric)
                right_value = right_snapshot.get_metric(metric)
                if left_value is None or right_value is None:
                    continue

                tolerance = config.metric_tolerances.get(
                    metric, config.default_tolerance
                )
                if not tolerance.allows(left_value, right_value):
                    difference = abs(right_value - left_value)
                    scale = max(abs(left_value), abs(right_value), 1.0)
                    deviations.append(
                        MetricDeviation(
                            metric=metric,
                            baseline_environment=left_env,
                            comparison_environment=right_env,
                            baseline_value=left_value,
                            comparison_value=right_value,
                            absolute_difference=difference,
                            relative_difference=difference / scale,
                        )
                    )

        code_digests = {env: snapshot.code_digest for env, snapshot in env_map.items()}
        parameter_digests = {
            env: snapshot.parameters_digest for env, snapshot in env_map.items()
        }

        if config.metadata_keys:
            metadata_keys = set(config.metadata_keys)
        else:
            metadata_sets = [
                set(snapshot.metadata.keys()) for snapshot in env_map.values()
            ]
            metadata_keys = set.intersection(*metadata_sets) if metadata_sets else set()
            metadata_keys -= _DEFAULT_METADATA_IGNORES

        metadata_drift: MutableMapping[str, Mapping[str, Any]] = {}
        for key in sorted(metadata_keys):
            values = {env: env_map[env].metadata.get(key) for env in env_map}
            unique = {value for value in values.values()}
            if len(unique) > 1:
                metadata_drift[key] = values

        digest_values = {value for value in code_digests.values() if value}
        params_values = {value for value in parameter_digests.values() if value}

        fail_conditions = []
        fail_conditions.extend(missing_envs)
        if missing_metrics and not config.allow_missing_metrics:
            fail_conditions.append("missing-metrics")
        if deviations:
            fail_conditions.append("metric-deviation")
        if config.require_code_digest and len(digest_values) > 1:
            fail_conditions.append("code-drift")
        if config.require_parameter_digest and len(params_values) > 1:
            fail_conditions.append("param-drift")
        if metadata_drift:
            fail_conditions.append("metadata-drift")

        if fail_conditions:
            status = "fail"
        elif missing_metrics:
            status = "warning"
        else:
            status = "pass"

        report = EnvironmentParityReport(
            strategy=strategy,
            baseline_environment=config.baseline_environment,
            comparison_pairs=pairs,
            snapshots=MappingProxyType(env_map),
            missing_environments=missing_envs,
            missing_metrics=MappingProxyType(dict(missing_metrics)),
            metric_deviations=tuple(deviations),
            optional_missing_metrics=MappingProxyType(dict(optional_missing)),
            code_digests=MappingProxyType(code_digests),
            parameter_digests=MappingProxyType(parameter_digests),
            metadata_drift=MappingProxyType(dict(metadata_drift)),
            status=status,
        )

        if hasattr(self._metrics, "record_environment_parity"):
            self._metrics.record_environment_parity(
                strategy=report.strategy,
                status=report.status,
                deviations=report.metric_deviations,
            )

        return report


__all__ = [
    "EnvironmentParityChecker",
    "EnvironmentParityConfig",
    "EnvironmentParityError",
    "EnvironmentParityReport",
    "MetricDeviation",
    "MetricTolerance",
    "StrategyRunSnapshot",
    "compute_code_digest",
    "compute_parameters_digest",
]
