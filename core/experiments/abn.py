"""Utilities to design, run, and evaluate production A/B/n experiments.

This module provides a high-level orchestration layer for controlled
experiments in TradePulse.  It focuses on the lifecycle of
production-grade A/B/n tests: participant segmentation, deterministic
randomisation, stratified traffic isolation, runtime guardrails,
variance reduction (CUPED), multiple testing corrections, confidence
interval estimation, and automated publication of experiment
conclusions to the central model registry.

The implementation intentionally favours readability and testability.
All public dataclasses are immutable, intermediate calculations are
performed with explicit helper functions, and statistical primitives
delegate to the Python standard library wherever possible.  The
behaviour is fully deterministic which makes it straightforward to
reproduce experiment outcomes across environments.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist, fmean
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

from .registry import ArtifactSpec, ModelRegistry

__all__ = [
    "ExperimentArm",
    "Guardrail",
    "MetricDefinition",
    "StoppingPolicy",
    "ExperimentSegmenter",
    "RandomisationEngine",
    "ABNExperiment",
    "ExperimentResult",
    "MetricComparison",
]


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _z_value(confidence_level: float) -> float:
    alpha = 1.0 - confidence_level
    return NormalDist().inv_cdf(1.0 - alpha / 2.0)


@dataclass(frozen=True, slots=True)
class ExperimentArm:
    """Single variant in an A/B/n experiment."""

    name: str
    allocation: float
    is_control: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            msg = "Experiment arm name must not be empty"
            raise ValueError(msg)
        if not (0.0 < self.allocation <= 1.0):
            msg = f"Allocation for arm '{self.name}' must be within (0, 1]"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Guardrail:
    """Policy thresholds that should remain within safe bounds."""

    metric: str
    minimum: float | None = None
    maximum: float | None = None
    max_relative_drop: float | None = None

    def check(
        self,
        *,
        control_mean: float,
        variant_mean: float,
        higher_is_better: bool,
    ) -> tuple[bool, str | None]:
        """Return whether the guardrail passes and diagnostic context."""

        if self.minimum is not None and variant_mean < self.minimum:
            return False, f"Mean {variant_mean:.6f} is below minimum {self.minimum:.6f}"
        if self.maximum is not None and variant_mean > self.maximum:
            return False, f"Mean {variant_mean:.6f} exceeds maximum {self.maximum:.6f}"

        if self.max_relative_drop is not None and control_mean:
            allowed_drop = abs(control_mean) * self.max_relative_drop
            delta = variant_mean - control_mean
            if higher_is_better and delta < -allowed_drop:
                msg = (
                    f"Relative drop {delta / control_mean:.6f} exceeds allowed "
                    f"{self.max_relative_drop:.6f}"
                )
                return False, msg
            if not higher_is_better and delta > allowed_drop:
                msg = (
                    f"Relative increase {delta / control_mean:.6f} exceeds allowed "
                    f"{self.max_relative_drop:.6f}"
                )
                return False, msg

        return True, None


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Description of a tracked experiment metric."""

    key: str
    higher_is_better: bool = True
    guardrail: Guardrail | None = None
    covariate_key: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            msg = "Metric key must not be empty"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class StoppingPolicy:
    """Rules describing when an experiment may be concluded."""

    min_samples_per_arm: int = 0
    min_duration: timedelta | None = None
    max_duration: timedelta | None = None
    p_value_threshold: float = 0.05
    require_guardrails: bool = True
    stop_on_guardrail_breach: bool = True

    def __post_init__(self) -> None:
        if not (0.0 < self.p_value_threshold <= 1.0):
            msg = "p-value threshold must be in (0, 1]"
            raise ValueError(msg)
        if self.min_samples_per_arm < 0:
            msg = "min_samples_per_arm must be non-negative"
            raise ValueError(msg)


# ---------------------------------------------------------------------------
# Segmentation and randomisation
# ---------------------------------------------------------------------------


class ExperimentSegmenter:
    """Segment participants and derive stratification keys."""

    def __init__(
        self,
        *,
        include: Iterable[Callable[[Mapping[str, object]], bool]] | None = None,
        exclude: Iterable[Callable[[Mapping[str, object]], bool]] | None = None,
        stratify_by: Sequence[str] | None = None,
    ) -> None:
        self._include = tuple(include or ())
        self._exclude = tuple(exclude or ())
        self._stratify_by = tuple(stratify_by or ())

    def segment(self, attributes: Mapping[str, object]) -> str | None:
        """Return the stratification key or ``None`` when excluded."""

        if self._include and not all(predicate(attributes) for predicate in self._include):
            return None
        if self._exclude and any(predicate(attributes) for predicate in self._exclude):
            return None

        if not self._stratify_by:
            return "default"

        values: list[str] = []
        for key in self._stratify_by:
            value = attributes.get(key, "__missing__")
            values.append(f"{key}={value}")
        return "|".join(values)


class RandomisationEngine:
    """Deterministic hash-based randomisation with traffic isolation."""

    def __init__(
        self,
        experiment_id: str,
        arms: Sequence[ExperimentArm],
        *,
        bucket_count: int = 10_000,
        holdout_fraction: float = 0.0,
    ) -> None:
        if not experiment_id:
            msg = "experiment_id must not be empty"
            raise ValueError(msg)
        if bucket_count <= 0:
            msg = "bucket_count must be positive"
            raise ValueError(msg)
        if not (0.0 <= holdout_fraction < 1.0):
            msg = "holdout_fraction must be within [0, 1)"
            raise ValueError(msg)

        total_allocation = sum(arm.allocation for arm in arms)
        if total_allocation > 1.0 + 1e-9:
            msg = "Arm allocations must sum to <= 1.0"
            raise ValueError(msg)

        self._experiment_id = experiment_id
        self._bucket_count = bucket_count
        self._active_buckets = int(bucket_count * (1.0 - holdout_fraction))
        self._ranges: dict[str, tuple[int, int]] = {}

        cursor = 0
        for arm in arms:
            width = int(round(arm.allocation * self._active_buckets))
            end = min(self._active_buckets, cursor + width)
            if width == 0:
                end = cursor
            self._ranges[arm.name] = (cursor, end)
            cursor = end

        self._control_name = next((arm.name for arm in arms if arm.is_control), arms[0].name)

    @property
    def control_name(self) -> str:
        return self._control_name

    def assign(self, participant_id: str, stratum: str) -> str | None:
        """Return the arm assignment for ``participant_id`` in ``stratum``."""

        import hashlib

        payload = f"{self._experiment_id}:{stratum}:{participant_id}".encode("utf-8")
        bucket = int.from_bytes(hashlib.sha1(payload).digest()[:8], "big") % self._bucket_count
        if bucket >= self._active_buckets:
            return None
        for arm, (start, end) in self._ranges.items():
            if start <= bucket < end:
                return arm
        return self._control_name


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Aggregate:
    mean: float
    variance: float
    sample_size: int
    cuped_theta: float | None = None
    cuped_variance_reduction: float | None = None


def _variance(values: Sequence[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _cuped_adjust(values: Sequence[float], covariates: Sequence[float | None]) -> tuple[list[float], float | None, float | None]:
    usable = [(value, cov) for value, cov in zip(values, covariates) if cov is not None]
    if len(usable) < 2:
        return list(values), None, None

    y_values = [value for value, _ in usable]
    x_values = [float(cov) for _, cov in usable]
    mean_y = fmean(y_values)
    mean_x = fmean(x_values)
    cov = sum((y - mean_y) * (x - mean_x) for y, x in usable) / (len(usable) - 1)
    var_x = sum((x - mean_x) ** 2 for x in x_values) / (len(usable) - 1)
    if var_x == 0.0:
        return list(values), None, None

    theta = cov / var_x
    adjusted = [value - theta * (covariate - mean_x) if covariate is not None else value for value, covariate in zip(values, covariates)]

    baseline_variance = _variance(y_values, mean_y)
    adjusted_variance = _variance(adjusted[: len(y_values)], fmean(adjusted[: len(y_values)]))
    reduction = None
    if baseline_variance:
        reduction = max(0.0, 1.0 - adjusted_variance / baseline_variance)

    return adjusted, theta, reduction


def _aggregate_metric(
    values: Sequence[float],
    covariates: Sequence[float | None],
) -> _Aggregate:
    if not values:
        return _Aggregate(mean=0.0, variance=0.0, sample_size=0)

    adjusted_values, theta, reduction = _cuped_adjust(values, covariates)
    mean = fmean(adjusted_values)
    variance = _variance(adjusted_values, mean)
    return _Aggregate(
        mean=mean,
        variance=variance,
        sample_size=len(adjusted_values),
        cuped_theta=theta,
        cuped_variance_reduction=reduction,
    )


def _holms_correction(p_values: Mapping[tuple[str, str], float]) -> dict[tuple[str, str], float]:
    if not p_values:
        return {}

    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[tuple[str, str], float] = {}
    previous = 0.0
    for index, (key, p_value) in enumerate(ordered):
        factor = m - index
        corrected = min(1.0, p_value * factor)
        corrected = max(corrected, previous)
        adjusted[key] = corrected
        previous = corrected
    return adjusted


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: str
    variant: str
    control_mean: float
    variant_mean: float
    absolute_diff: float
    relative_diff: float | None
    lift: float
    p_value: float
    adjusted_p_value: float
    ci_low: float
    ci_high: float
    guardrail: Guardrail | None
    guardrail_passed: bool
    guardrail_reason: str | None
    sample_size_control: int
    sample_size_variant: int
    cuped_theta_control: float | None
    cuped_theta_variant: float | None
    cuped_variance_reduction_control: float | None
    cuped_variance_reduction_variant: float | None


@dataclass(frozen=True, slots=True)
class ArmStatistics:
    metric: str
    arm: str
    mean: float
    variance: float
    sample_size: int
    cuped_theta: float | None
    cuped_variance_reduction: float | None


@dataclass(slots=True)
class ExperimentResult:
    experiment_id: str
    metrics: list[MetricComparison]
    arm_statistics: list[ArmStatistics]
    strata_balance: dict[str, dict[str, float]]
    should_stop: bool
    stop_reasons: list[str]
    observation_start: datetime | None
    observation_end: datetime | None

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "metrics": [asdict(comparison) for comparison in self.metrics],
            "arm_statistics": [asdict(stat) for stat in self.arm_statistics],
            "strata_balance": self.strata_balance,
            "should_stop": self.should_stop,
            "stop_reasons": self.stop_reasons,
            "observation_start": self.observation_start.isoformat() if self.observation_start else None,
            "observation_end": self.observation_end.isoformat() if self.observation_end else None,
        }


# ---------------------------------------------------------------------------
# Main experiment orchestration
# ---------------------------------------------------------------------------


class ABNExperiment:
    """Run and evaluate an A/B/n experiment with statistical safeguards."""

    def __init__(
        self,
        experiment_id: str,
        arms: Sequence[ExperimentArm],
        metrics: Sequence[MetricDefinition],
        *,
        segmenter: ExperimentSegmenter | None = None,
        randomiser: RandomisationEngine | None = None,
        stopping_policy: StoppingPolicy | None = None,
        confidence_level: float = 0.95,
    ) -> None:
        if not experiment_id:
            msg = "experiment_id must not be empty"
            raise ValueError(msg)
        if not arms:
            msg = "At least one experiment arm must be provided"
            raise ValueError(msg)
        if not metrics:
            msg = "At least one metric must be provided"
            raise ValueError(msg)
        if not (0.5 <= confidence_level < 1.0):
            msg = "confidence_level must be within [0.5, 1)"
            raise ValueError(msg)

        self._experiment_id = experiment_id
        self._arms = tuple(arms)
        self._metrics = tuple(metrics)
        self._segmenter = segmenter or ExperimentSegmenter()
        self._randomiser = randomiser or RandomisationEngine(experiment_id, arms)
        self._stopping = stopping_policy or StoppingPolicy()
        self._confidence_level = confidence_level

        self._assignments: dict[str, tuple[str, str]] = {}
        self._observations: dict[str, dict[str, list[float]]] = {
            metric.key: {arm.name: [] for arm in self._arms} for metric in self._metrics
        }
        self._covariates: dict[str, dict[str, list[float | None]]] = {
            metric.key: {arm.name: [] for arm in self._arms} for metric in self._metrics
        }
        self._strata_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._observation_start: datetime | None = None
        self._observation_end: datetime | None = None

    @property
    def experiment_id(self) -> str:
        return self._experiment_id

    def assign(self, participant_id: str, attributes: Mapping[str, object]) -> str | None:
        """Deterministically assign *participant_id* to an experiment arm."""

        if participant_id in self._assignments:
            return self._assignments[participant_id][0]

        stratum = self._segmenter.segment(attributes)
        if stratum is None:
            return None

        arm = self._randomiser.assign(participant_id, stratum)
        if arm is None:
            return None

        self._assignments[participant_id] = (arm, stratum)
        return arm

    def record_observation(
        self,
        participant_id: str,
        metrics: Mapping[str, float | int | bool],
        *,
        covariates: Mapping[str, float | int] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a metric observation for *participant_id*."""

        if participant_id not in self._assignments:
            msg = f"Participant '{participant_id}' has not been assigned"
            raise KeyError(msg)

        arm, stratum = self._assignments[participant_id]
        self._strata_counts[stratum][arm] += 1

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        timestamp = _ensure_timezone(timestamp)
        if self._observation_start is None or timestamp < self._observation_start:
            self._observation_start = timestamp
        if self._observation_end is None or timestamp > self._observation_end:
            self._observation_end = timestamp

        for metric in self._metrics:
            if metric.key not in metrics:
                continue
            raw_value = metrics[metric.key]
            value = float(raw_value)
            self._observations[metric.key][arm].append(value)
            cov_store = self._covariates[metric.key][arm]
            if metric.covariate_key is not None:
                cov_value = None
                if covariates and metric.covariate_key in covariates:
                    cov_value = float(covariates[metric.covariate_key])
                cov_store.append(cov_value)
            else:
                cov_store.append(None)

    def _strata_distribution(self) -> dict[str, dict[str, float]]:
        distribution: dict[str, dict[str, float]] = {}
        for stratum, counts in self._strata_counts.items():
            total = sum(counts.values()) or 1
            distribution[stratum] = {
                arm: counts.get(arm, 0) / total for arm in (arm.name for arm in self._arms)
            }
        return distribution

    def evaluate(self) -> ExperimentResult:
        """Return an :class:`ExperimentResult` describing the current state."""

        control_name = self._randomiser.control_name
        z_score = _z_value(self._confidence_level)

        aggregates: dict[tuple[str, str], _Aggregate] = {}
        arm_statistics: list[ArmStatistics] = []
        for metric in self._metrics:
            for arm in self._arms:
                values = self._observations[metric.key][arm.name]
                covariates = self._covariates[metric.key][arm.name]
                aggregate = _aggregate_metric(values, covariates)
                aggregates[(metric.key, arm.name)] = aggregate
                arm_statistics.append(
                    ArmStatistics(
                        metric=metric.key,
                        arm=arm.name,
                        mean=aggregate.mean,
                        variance=aggregate.variance,
                        sample_size=aggregate.sample_size,
                        cuped_theta=aggregate.cuped_theta,
                        cuped_variance_reduction=aggregate.cuped_variance_reduction,
                    )
                )

        p_values: dict[tuple[str, str], float] = {}
        comparisons: list[MetricComparison] = []
        guardrail_failures = 0

        for metric in self._metrics:
            control = aggregates[(metric.key, control_name)]
            for arm in self._arms:
                if arm.name == control_name:
                    continue
                variant = aggregates[(metric.key, arm.name)]
                diff = variant.mean - control.mean
                rel_diff = None
                if control.mean:
                    rel_diff = diff / control.mean
                se = 0.0
                if control.sample_size > 0 and variant.sample_size > 0:
                    se = math.sqrt(
                        (control.variance / control.sample_size)
                        + (variant.variance / variant.sample_size)
                    )
                p_value = 1.0
                ci_low = diff
                ci_high = diff
                if se > 0.0:
                    z = diff / se
                    p_value = 2.0 * (1.0 - NormalDist().cdf(abs(z)))
                    ci_low = diff - z_score * se
                    ci_high = diff + z_score * se

                p_values[(metric.key, arm.name)] = p_value

        adjusted_p_values = _holms_correction(p_values)

        for metric in self._metrics:
            control = aggregates[(metric.key, control_name)]
            for arm in self._arms:
                if arm.name == control_name:
                    continue
                variant = aggregates[(metric.key, arm.name)]
                diff = variant.mean - control.mean
                rel_diff = None
                if control.mean:
                    rel_diff = diff / control.mean
                se = 0.0
                if control.sample_size > 0 and variant.sample_size > 0:
                    se = math.sqrt(
                        (control.variance / control.sample_size)
                        + (variant.variance / variant.sample_size)
                    )
                z = diff / se if se else 0.0
                ci_low = diff - z_score * se
                ci_high = diff + z_score * se
                p_value = p_values[(metric.key, arm.name)]
                adjusted = adjusted_p_values.get((metric.key, arm.name), p_value)
                lift = rel_diff or 0.0

                guardrail_passed = True
                guardrail_reason = None
                if metric.guardrail:
                    guardrail_passed, guardrail_reason = metric.guardrail.check(
                        control_mean=control.mean,
                        variant_mean=variant.mean,
                        higher_is_better=metric.higher_is_better,
                    )
                    if not guardrail_passed:
                        guardrail_failures += 1

                comparisons.append(
                    MetricComparison(
                        metric=metric.key,
                        variant=arm.name,
                        control_mean=control.mean,
                        variant_mean=variant.mean,
                        absolute_diff=diff,
                        relative_diff=rel_diff,
                        lift=lift,
                        p_value=p_value,
                        adjusted_p_value=adjusted,
                        ci_low=ci_low,
                        ci_high=ci_high,
                        guardrail=metric.guardrail,
                        guardrail_passed=guardrail_passed,
                        guardrail_reason=guardrail_reason,
                        sample_size_control=control.sample_size,
                        sample_size_variant=variant.sample_size,
                        cuped_theta_control=control.cuped_theta,
                        cuped_theta_variant=variant.cuped_theta,
                        cuped_variance_reduction_control=control.cuped_variance_reduction,
                        cuped_variance_reduction_variant=variant.cuped_variance_reduction,
                    )
                )

        should_stop = False
        stop_reasons: list[str] = []
        min_samples_met = all(
            aggregates[(metric.key, arm.name)].sample_size >= self._stopping.min_samples_per_arm
            for metric in self._metrics
            for arm in self._arms
        )

        if self._stopping.min_samples_per_arm and not min_samples_met:
            stop_reasons.append("Insufficient sample size per arm")

        if self._observation_start and self._observation_end and self._stopping.min_duration:
            elapsed = self._observation_end - self._observation_start
            if elapsed < self._stopping.min_duration:
                stop_reasons.append("Minimum duration not yet satisfied")

        if self._observation_start and self._observation_end and self._stopping.max_duration:
            elapsed = self._observation_end - self._observation_start
            if elapsed >= self._stopping.max_duration:
                should_stop = True
                stop_reasons.append("Maximum duration reached")

        if guardrail_failures and self._stopping.stop_on_guardrail_breach:
            should_stop = True
            stop_reasons.append("Guardrail breach detected")

        significant_effects = [
            comparison
            for comparison in comparisons
            if comparison.adjusted_p_value <= self._stopping.p_value_threshold
        ]

        if (
            significant_effects
            and (self._stopping.require_guardrails is False or guardrail_failures == 0)
            and min_samples_met
        ):
            should_stop = True
            stop_reasons.append("Statistical significance reached")

        if not should_stop and not stop_reasons:
            stop_reasons.append("Continue monitoring")

        result = ExperimentResult(
            experiment_id=self._experiment_id,
            metrics=comparisons,
            arm_statistics=arm_statistics,
            strata_balance=self._strata_distribution(),
            should_stop=should_stop,
            stop_reasons=stop_reasons,
            observation_start=self._observation_start,
            observation_end=self._observation_end,
        )
        return result

    def recommended_duration(
        self,
        *,
        daily_traffic: int,
        baseline_std: float,
        min_detectable_effect: float,
        alpha: float | None = None,
        power: float = 0.8,
    ) -> timedelta:
        """Estimate the experiment duration needed to achieve desired power."""

        if daily_traffic <= 0:
            msg = "daily_traffic must be positive"
            raise ValueError(msg)
        if baseline_std <= 0:
            msg = "baseline_std must be positive"
            raise ValueError(msg)
        if min_detectable_effect <= 0:
            msg = "min_detectable_effect must be positive"
            raise ValueError(msg)
        alpha = alpha or (1.0 - self._confidence_level)
        if not (0.0 < alpha < 1.0):
            msg = "alpha must be within (0, 1)"
            raise ValueError(msg)
        if not (0.0 < power < 1.0):
            msg = "power must be within (0, 1)"
            raise ValueError(msg)

        z_alpha = NormalDist().inv_cdf(1.0 - alpha / 2.0)
        z_beta = NormalDist().inv_cdf(power)
        required_per_group = 2.0 * ((z_alpha + z_beta) * baseline_std / min_detectable_effect) ** 2
        total_required = math.ceil(required_per_group * len(self._arms))
        days = math.ceil(total_required / daily_traffic)
        return timedelta(days=days)

    def publish_conclusions(
        self,
        registry: ModelRegistry,
        *,
        experiment_name: str | None = None,
        parameters: Mapping[str, object] | None = None,
        metadata: MutableMapping[str, object] | None = None,
        tags: Iterable[str] | None = None,
    ) -> ExperimentResult:
        """Persist the latest evaluation summary to the model registry."""

        result = self.evaluate()
        experiment_label = experiment_name or self._experiment_id
        params = dict(parameters or {})
        meta = dict(metadata or {})
        meta.update(
            {
                "should_stop": result.should_stop,
                "stop_reasons": result.stop_reasons,
            }
        )

        metrics_payload: dict[str, float] = {}
        for comparison in result.metrics:
            key_base = f"{comparison.metric}:{comparison.variant}"
            metrics_payload[f"{key_base}:lift"] = comparison.lift
            metrics_payload[f"{key_base}:p_adjusted"] = comparison.adjusted_p_value

        with TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / f"{self._experiment_id}_summary.json"
            summary_path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")

            registry.register_run(
                experiment_label,
                parameters=params,
                metrics=metrics_payload,
                artifacts=[
                    ArtifactSpec(
                        path=summary_path,
                        name=summary_path.name,
                        kind="abn-summary",
                        metadata={"confidence_level": self._confidence_level},
                    )
                ],
                tags=(set(tags or set()) | {"abn", "auto-publish"}),
                metadata=meta,
            )

        return result

