"""FinOps cost control utilities for TradePulse.

The module provides primitives to monitor infrastructure usage, evaluate budget
compliance, and emit actionable optimisation guidance.  It favours an
in-memory ledger that can be embedded in schedulers, CLI tooling, or
server-side daemons without requiring a backing database.  Consumers feed
`ResourceUsageSample` instances obtained from billing exports or provider APIs
and the controller keeps rolling aggregates aligned with configured budgets.
"""

from __future__ import annotations

import asyncio
import math
import statistics
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import (
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
    runtime_checkable,
)

from .notifications import NotificationDispatcher

__all__ = [
    "ResourceUsageSample",
    "Budget",
    "BudgetStatus",
    "CostReport",
    "OptimizationRecommendation",
    "ResourceProfile",
    "CostOptimisationPlan",
    "FinOpsAlert",
    "AlertSink",
    "NotificationAlertSink",
    "FinOpsController",
]


def _ensure_positive_duration(value: timedelta) -> None:
    if value <= timedelta(0):
        raise ValueError("Duration must be positive")


@dataclass(slots=True, frozen=True)
class ResourceUsageSample:
    """Snapshot describing the utilisation and spend of a resource."""

    resource_id: str
    timestamp: datetime
    cost: float
    usage: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be provided")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime instance")
        if self.cost < 0.0 or not math.isfinite(self.cost):
            raise ValueError("cost must be a finite, non-negative number")
        for key, value in self.usage.items():
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(
                    f"usage metric '{key}' must be a finite, non-negative number"
                )


@dataclass(slots=True, frozen=True)
class Budget:
    """Declarative budget with optional metadata matching scope."""

    name: str
    limit: float
    period: timedelta
    scope: Mapping[str, str] | None = None
    alert_thresholds: Sequence[float] = (0.8, 1.0)
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Budget name must be provided")
        if self.limit <= 0.0 or not math.isfinite(self.limit):
            raise ValueError("Budget limit must be a finite, positive number")
        _ensure_positive_duration(self.period)
        if not self.alert_thresholds:
            raise ValueError("At least one alert threshold must be specified")
        sorted_thresholds = sorted(self.alert_thresholds)
        if any(threshold <= 0.0 for threshold in sorted_thresholds):
            raise ValueError("Alert thresholds must be greater than zero")
        if any(not math.isfinite(threshold) for threshold in sorted_thresholds):
            raise ValueError("Alert thresholds must be finite")
        object.__setattr__(self, "alert_thresholds", tuple(sorted_thresholds))


@dataclass(slots=True, frozen=True)
class BudgetStatus:
    """Current utilisation snapshot of a budget."""

    budget: Budget
    total_cost: float
    window_start: datetime
    window_end: datetime
    utilisation: float
    remaining: float
    breached: bool


@dataclass(slots=True, frozen=True)
class CostReport:
    """Aggregated cost analytics for a time window."""

    total_cost: float
    average_daily_cost: float
    max_sample_cost: float
    resource_costs: Mapping[str, float]
    usage_totals: Mapping[str, float]
    window_start: datetime
    window_end: datetime


@dataclass(slots=True, frozen=True)
class OptimizationRecommendation:
    """Actionable optimisation recommendation derived from usage data."""

    resource_id: str
    message: str
    severity: str
    metadata: Mapping[str, float | str] = field(default_factory=dict)
    category: str = "general"


@dataclass(slots=True, frozen=True)
class ResourceProfile:
    """Normalised resource level profile for plan generation."""

    resource_id: str
    cloud: str | None
    instance_type: str | None
    purchase_option: str | None
    total_cost: float
    average_utilisation: float | None
    max_sample_cost: float
    metadata: Mapping[str, str]


@dataclass(slots=True, frozen=True)
class CostOptimisationPlan:
    """Structured plan covering FinOps optimisation levers."""

    generated_at: datetime
    window_start: datetime
    window_end: datetime
    cloud_costs: Mapping[str, float]
    instance_costs: Mapping[str, float]
    resource_profiles: tuple[ResourceProfile, ...]
    recommendations: tuple[OptimizationRecommendation, ...]
    budget_statuses: tuple[BudgetStatus, ...]
    review_schedule: tuple[datetime, ...]


@dataclass(slots=True, frozen=True)
class FinOpsAlert:
    """Alert emitted when a budget crosses a utilisation threshold."""

    budget: Budget
    threshold: float
    total_cost: float
    remaining: float
    utilisation: float
    window_start: datetime
    window_end: datetime
    breached: bool


@runtime_checkable
class AlertSink(Protocol):
    """Protocol implemented by alert sinks receiving FinOps alerts."""

    def handle_alert(self, alert: FinOpsAlert) -> None:  # pragma: no cover - protocol
        """Process a triggered alert."""


class NotificationAlertSink:
    """Adapter that routes alerts through :class:`NotificationDispatcher`."""

    def __init__(
        self,
        dispatcher: NotificationDispatcher,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._loop = loop

    def handle_alert(self, alert: FinOpsAlert) -> None:
        subject, message, metadata = self._build_payload(alert)
        coroutine = self._dispatcher.dispatch(
            "finops.budget", subject=subject, message=message, metadata=metadata
        )
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(coroutine)
                return
        if loop.is_running():
            loop.create_task(coroutine)
        else:  # pragma: no cover - exercised when explicitly providing event loop
            loop.run_until_complete(coroutine)

    @staticmethod
    def _build_payload(alert: FinOpsAlert) -> tuple[str, str, Mapping[str, object]]:
        budget = alert.budget
        utilisation_pct = round(alert.utilisation * 100, 2)
        status = "breached" if alert.breached else "warning"
        subject = f"[FinOps] Budget {budget.name} {status}"
        message = (
            f"Budget '{budget.name}' is at {utilisation_pct}% of its limit"
            f" ({budget.currency} {alert.total_cost:.2f} spent of {budget.currency} {budget.limit:.2f})."
        )
        if alert.breached:
            message += " Limit exceeded; immediate action required."
        metadata = {
            "budget": budget.name,
            "threshold_ratio": round(alert.threshold, 3),
            "utilisation_pct": utilisation_pct,
            "total_cost": round(alert.total_cost, 2),
            "remaining_budget": round(alert.remaining, 2),
            "window_start": alert.window_start.isoformat(),
            "window_end": alert.window_end.isoformat(),
            "currency": budget.currency,
        }
        if budget.scope:
            metadata["scope"] = dict(budget.scope)
        return subject, message, metadata


class FinOpsController:
    """Coordinate FinOps analytics, budgets, and alerting."""

    def __init__(
        self,
        *,
        alert_sink: AlertSink | None = None,
        clock: callable[[], datetime] | None = None,
    ) -> None:
        self._alert_sink = alert_sink
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._usage_by_resource: MutableMapping[str, list[ResourceUsageSample]] = (
            defaultdict(list)
        )
        self._budgets: MutableMapping[str, Budget] = {}
        self._budget_ledgers: MutableMapping[str, list[tuple[datetime, float]]] = (
            defaultdict(list)
        )
        self._budget_thresholds: MutableMapping[str, float] = defaultdict(float)

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------
    def add_budget(self, budget: Budget) -> None:
        """Register a new budget, replacing any previous definition."""

        self._budgets[budget.name] = budget
        self._budget_ledgers.setdefault(budget.name, [])
        self._budget_thresholds.setdefault(budget.name, 0.0)

    def remove_budget(self, name: str) -> None:
        """Remove a configured budget."""

        self._budgets.pop(name, None)
        self._budget_ledgers.pop(name, None)
        self._budget_thresholds.pop(name, None)

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------
    def record_usage(self, sample: ResourceUsageSample) -> tuple[FinOpsAlert, ...]:
        """Record a usage sample and evaluate affected budgets."""

        self._store_usage_sample(sample)
        alerts: list[FinOpsAlert] = []
        for budget in self._budgets.values():
            if not self._sample_matches_scope(sample, budget.scope):
                continue
            ledger = self._budget_ledgers[budget.name]
            self._insert_ledger_entry(ledger, sample)
            total_cost, window_start = self._prune_and_sum(
                ledger, budget, sample.timestamp
            )
            alert_events = self._evaluate_budget(
                budget,
                total_cost,
                window_start,
                sample.timestamp,
            )
            if alert_events:
                alerts.extend(alert_events)
        return tuple(alerts)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    def analyse_costs(
        self,
        window: timedelta,
        *,
        metadata_filter: Mapping[str, str] | None = None,
        as_of: datetime | None = None,
    ) -> CostReport:
        """Aggregate cost and usage statistics across resources."""

        _ensure_positive_duration(window)
        as_of = as_of or self._clock()
        window_start = as_of - window

        resource_costs: MutableMapping[str, float] = defaultdict(float)
        usage_totals: MutableMapping[str, float] = defaultdict(float)
        total_cost = 0.0
        max_sample_cost = 0.0

        for resource_id, samples in self._usage_by_resource.items():
            relevant_samples = self._slice_samples(
                samples, window_start, as_of, metadata_filter
            )
            resource_sum = 0.0
            for sample in relevant_samples:
                resource_sum += sample.cost
                total_cost += sample.cost
                max_sample_cost = max(max_sample_cost, sample.cost)
                for metric, value in sample.usage.items():
                    usage_totals[metric] += value
            if resource_sum:
                resource_costs[resource_id] += resource_sum

        days = max(window.total_seconds() / 86400.0, 1e-6)
        average_daily_cost = total_cost / days

        return CostReport(
            total_cost=total_cost,
            average_daily_cost=average_daily_cost,
            max_sample_cost=max_sample_cost,
            resource_costs=dict(sorted(resource_costs.items())),
            usage_totals=dict(sorted(usage_totals.items())),
            window_start=window_start,
            window_end=as_of,
        )

    def recommend_optimisations(
        self,
        window: timedelta,
        *,
        utilisation_threshold: float = 0.25,
        spike_multiplier: float = 1.5,
        metadata_filter: Mapping[str, str] | None = None,
        as_of: datetime | None = None,
    ) -> tuple[OptimizationRecommendation, ...]:
        """Derive optimisation recommendations from recent usage."""

        if utilisation_threshold <= 0.0:
            raise ValueError("utilisation_threshold must be positive")
        if spike_multiplier <= 1.0:
            raise ValueError("spike_multiplier must be greater than 1")

        _ensure_positive_duration(window)
        as_of = as_of or self._clock()
        window_start = as_of - window

        recommendations: list[OptimizationRecommendation] = []

        for resource_id, samples in self._usage_by_resource.items():
            relevant = self._slice_samples(
                samples, window_start, as_of, metadata_filter
            )
            if not relevant:
                continue

            utilisation_values: list[float] = []
            costs = [sample.cost for sample in relevant]
            for sample in relevant:
                for value in sample.usage.values():
                    if 0.0 <= value <= 1.0 and math.isfinite(value):
                        utilisation_values.append(value)

            if utilisation_values:
                avg_utilisation = statistics.fmean(utilisation_values)
                total_cost = sum(costs)
                if avg_utilisation < utilisation_threshold and total_cost > 0.0:
                    recommendations.append(
                        OptimizationRecommendation(
                            resource_id=resource_id,
                            message=(
                                "Resource exhibits sustained low utilisation; consider rightsizing or scheduling shutdowns."
                            ),
                            severity="medium",
                            metadata={
                                "average_utilisation": round(avg_utilisation, 4),
                                "total_cost": round(total_cost, 2),
                            },
                            category="rightsizing",
                        )
                    )

            if len(costs) >= 3:
                historical = costs[:-1]
                latest = costs[-1]
                median_cost = statistics.median(historical)
                if median_cost > 0.0 and latest >= median_cost * spike_multiplier:
                    recommendations.append(
                        OptimizationRecommendation(
                            resource_id=resource_id,
                            message="Latest cost sample spikes above historical trend; investigate anomalies or misconfigurations.",
                            severity="high",
                            metadata={
                                "latest_cost": round(latest, 2),
                                "median_cost": round(median_cost, 2),
                                "spike_multiplier": spike_multiplier,
                            },
                            category="anomaly_detection",
                        )
                    )

        return tuple(recommendations)

    def generate_cost_optimisation_plan(
        self,
        window: timedelta,
        *,
        metadata_filter: Mapping[str, str] | None = None,
        as_of: datetime | None = None,
    ) -> CostOptimisationPlan:
        """Synthesize a holistic FinOps action plan for the supplied window."""

        _ensure_positive_duration(window)
        as_of = as_of or self._clock()
        window_start = as_of - window

        base_recommendations = list(
            self.recommend_optimisations(
                window,
                metadata_filter=metadata_filter,
                as_of=as_of,
            )
        )

        resource_profiles: list[ResourceProfile] = []
        additional_recommendations: list[OptimizationRecommendation] = []
        cloud_costs: MutableMapping[str, float] = defaultdict(float)
        instance_costs: MutableMapping[str, float] = defaultdict(float)
        dedupe_index: dict[tuple[str, ...], ResourceProfile] = {}

        for resource_id, samples in self._usage_by_resource.items():
            relevant = self._slice_samples(
                samples, window_start, as_of, metadata_filter
            )
            if not relevant:
                continue

            profile = self._build_resource_profile(resource_id, relevant)
            resource_profiles.append(profile)

            cloud_key = profile.cloud or "unknown"
            instance_key = profile.instance_type or "unknown"
            cloud_costs[cloud_key] += profile.total_cost
            instance_costs[f"{cloud_key}:{instance_key}"] += profile.total_cost

            additional_recommendations.extend(
                self._derive_resource_recommendations(profile, relevant)
            )

            dedupe_key = self._build_deduplication_key(profile)
            if dedupe_key:
                existing = dedupe_index.get(dedupe_key)
                if existing is not None and existing.resource_id != profile.resource_id:
                    additional_recommendations.append(
                        OptimizationRecommendation(
                            resource_id=profile.resource_id,
                            message=(
                                "Duplicate workload detected across resources; consolidate deployments to eliminate redundant spend."
                            ),
                            severity="medium",
                            metadata={
                                "duplicate_of": existing.resource_id,
                                "workload_key": "|".join(dedupe_key),
                            },
                            category="deduplication",
                        )
                    )
                else:
                    dedupe_index[dedupe_key] = profile

        cloud_costs_map = dict(sorted(cloud_costs.items(), key=lambda item: item[0]))
        instance_costs_map = dict(
            sorted(instance_costs.items(), key=lambda item: item[0])
        )

        cloud_highlights = self._build_cloud_profile_recommendations(cloud_costs_map)
        additional_recommendations.extend(cloud_highlights)

        budget_statuses = self._collect_budget_statuses(as_of, metadata_filter)
        additional_recommendations.extend(
            self._derive_budget_recommendations(budget_statuses)
        )

        review_schedule = self._build_weekly_review_schedule(as_of)
        if review_schedule:
            additional_recommendations.append(
                OptimizationRecommendation(
                    resource_id="finops-governance",
                    message=(
                        "Institute weekly savings reviews to track realised optimisations and recalibrate forecasts."
                    ),
                    severity="low",
                    metadata={"next_review": review_schedule[0].isoformat()},
                    category="governance",
                )
            )

        combined_recommendations = self._deduplicate_recommendations(
            base_recommendations + additional_recommendations
        )

        resource_profiles_sorted = tuple(
            sorted(resource_profiles, key=lambda profile: profile.resource_id)
        )

        return CostOptimisationPlan(
            generated_at=as_of,
            window_start=window_start,
            window_end=as_of,
            cloud_costs={
                key: round(value, 2) for key, value in cloud_costs_map.items()
            },
            instance_costs={
                key: round(value, 2) for key, value in instance_costs_map.items()
            },
            resource_profiles=resource_profiles_sorted,
            recommendations=tuple(combined_recommendations),
            budget_statuses=budget_statuses,
            review_schedule=review_schedule,
        )

    # ------------------------------------------------------------------
    # Budget status queries
    # ------------------------------------------------------------------
    def get_budget_status(
        self, name: str, *, as_of: datetime | None = None
    ) -> BudgetStatus:
        """Return the current status of a budget."""

        if name not in self._budgets:
            raise KeyError(f"Unknown budget '{name}'")
        budget = self._budgets[name]
        as_of = as_of or self._clock()
        ledger = self._budget_ledgers.get(name, [])
        total_cost, window_start = self._prune_and_sum(ledger, budget, as_of)
        utilisation = total_cost / budget.limit
        remaining = max(budget.limit - total_cost, 0.0)
        return BudgetStatus(
            budget=budget,
            total_cost=total_cost,
            window_start=window_start,
            window_end=as_of,
            utilisation=utilisation,
            remaining=remaining,
            breached=total_cost >= budget.limit,
        )

    def iter_budget_statuses(
        self, *, as_of: datetime | None = None
    ) -> Sequence[BudgetStatus]:
        """Return statuses for all budgets."""

        as_of = as_of or self._clock()
        return [self.get_budget_status(name, as_of=as_of) for name in self._budgets]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _store_usage_sample(self, sample: ResourceUsageSample) -> None:
        entries = self._usage_by_resource[sample.resource_id]
        if not entries or sample.timestamp >= entries[-1].timestamp:
            entries.append(sample)
            return
        timestamps = [entry.timestamp for entry in entries]
        index = bisect_left(timestamps, sample.timestamp)
        entries.insert(index, sample)

    def _build_resource_profile(
        self, resource_id: str, samples: Sequence[ResourceUsageSample]
    ) -> ResourceProfile:
        total_cost = sum(sample.cost for sample in samples)
        max_sample_cost = max((sample.cost for sample in samples), default=0.0)

        utilisation_values: list[float] = []
        for sample in samples:
            for value in sample.usage.values():
                if 0.0 <= value <= 1.0 and math.isfinite(value):
                    utilisation_values.append(value)

        average_utilisation = (
            statistics.fmean(utilisation_values) if utilisation_values else None
        )

        metadata_snapshot: dict[str, str] = {}
        for sample in samples:
            metadata_snapshot.update(sample.metadata)

        cloud = self._most_common_metadata(
            samples, ("cloud", "cloud_provider", "provider")
        )
        instance_type = self._most_common_metadata(
            samples,
            ("instance_type", "machine_type", "instance_class", "flavor"),
        )
        purchase_option = self._most_common_metadata(
            samples, ("purchase_option", "pricing", "billing_mode")
        )

        return ResourceProfile(
            resource_id=resource_id,
            cloud=cloud,
            instance_type=instance_type,
            purchase_option=purchase_option,
            total_cost=total_cost,
            average_utilisation=average_utilisation,
            max_sample_cost=max_sample_cost,
            metadata=dict(sorted(metadata_snapshot.items())),
        )

    def _derive_resource_recommendations(
        self,
        profile: ResourceProfile,
        samples: Sequence[ResourceUsageSample],
    ) -> list[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []
        metadata = profile.metadata

        costs = [sample.cost for sample in samples]
        mean_cost = statistics.fmean(costs) if costs else 0.0
        cost_variation = 0.0
        if len(costs) >= 2 and mean_cost > 0.0:
            cost_variation = statistics.pstdev(costs) / mean_cost

        utilisation_values: list[float] = []
        for sample in samples:
            for value in sample.usage.values():
                if 0.0 <= value <= 1.0 and math.isfinite(value):
                    utilisation_values.append(value)

        min_utilisation = min(utilisation_values) if utilisation_values else None
        max_utilisation = max(utilisation_values) if utilisation_values else None

        # Autoscaling guidance based on utilisation volatility
        scaling_policy = (metadata.get("scaling_policy") or "").lower()
        utilisation_span = (
            max_utilisation - min_utilisation
            if min_utilisation is not None and max_utilisation is not None
            else 0.0
        )
        if utilisation_span >= 0.35 and "auto" not in scaling_policy:
            severity = "high" if utilisation_span >= 0.6 else "medium"
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "Large utilisation swings observed; deploy autoscaling policies to match demand curves."
                    ),
                    severity=severity,
                    metadata={
                        "min_utilisation": round(min_utilisation or 0.0, 4),
                        "max_utilisation": round(max_utilisation or 0.0, 4),
                    },
                    category="autoscaling",
                )
            )

        # Reserved instances / commitments for stable high spend
        purchase = (profile.purchase_option or "").lower()
        if (
            purchase not in {"reserved", "savings_plan", "commitment"}
            and profile.total_cost >= 50.0
            and cost_variation <= 0.15
        ):
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "Spend pattern is steady; evaluate reserved instances or savings plans to lock in lower rates."
                    ),
                    severity="high",
                    metadata={
                        "cost_variation": round(cost_variation, 4),
                        "average_cost": round(mean_cost, 2),
                    },
                    category="reserved_instances",
                )
            )

        # Spot/pre-emptible opportunities for tolerant workloads
        spot_eligible = self._is_truthy_metadata(
            metadata, ("spot_eligible", "use_spot", "preemptible", "fault_tolerant")
        )
        workload_type = (
            metadata.get("workload_type") or metadata.get("service_type") or ""
        ).lower()
        if (
            purchase not in {"spot", "preemptible"}
            and profile.total_cost >= 20.0
            and (spot_eligible or workload_type in {"batch", "training", "analytics"})
        ):
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "Workload tolerates interruption; migrate a portion to spot/preemptible capacity for cost relief."
                    ),
                    severity="medium",
                    metadata={
                        "workload_type": workload_type or "unspecified",
                        "purchase_option": purchase or "unspecified",
                    },
                    category="spot",
                )
            )

        # GPU sharing and scheduling guidance
        resource_kind = (metadata.get("resource_kind") or "").lower()
        accelerator = (metadata.get("accelerator_type") or "").lower()
        gpu_count = self._parse_float_metadata(metadata, "gpu_count")
        average_utilisation = profile.average_utilisation
        if (
            average_utilisation is not None
            and average_utilisation < 0.65
            and (
                "gpu" in resource_kind
                or "gpu" in accelerator
                or (gpu_count is not None and gpu_count > 0.0)
            )
        ):
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "GPU capacity is underutilised; introduce time-slicing or shared job queues to increase occupancy."
                    ),
                    severity="medium",
                    metadata={
                        "average_utilisation": round(average_utilisation, 4),
                        "gpu_count": gpu_count or 0.0,
                    },
                    category="gpu_sharing",
                )
            )

        # Model footprint optimisation (compression / quantisation / distillation)
        model_size = self._parse_float_metadata(metadata, "model_size_gb")
        parameter_count = self._parse_float_metadata(
            metadata, "parameter_count_billion"
        )
        throughput = self._parse_float_metadata(metadata, "throughput_rps")
        heavy_model = False
        if model_size is not None and model_size >= 20.0:
            heavy_model = True
        if parameter_count is not None and parameter_count >= 10.0:
            heavy_model = True
        low_throughput = throughput is None or throughput < 0.5
        if heavy_model and low_throughput:
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "Model footprint is heavy relative to throughput; pursue weight compression, quantisation, or distillation."
                    ),
                    severity="medium",
                    metadata={
                        "model_size_gb": round(model_size or 0.0, 2),
                        "parameter_count_billion": round(parameter_count or 0.0, 2),
                        "throughput_rps": (
                            round(throughput or 0.0, 3) if throughput else 0.0
                        ),
                    },
                    category="model_optimisation",
                )
            )

        # Idle shutdown recommendation
        if (
            average_utilisation is not None
            and average_utilisation < 0.05
            and profile.total_cost > 0.0
        ):
            recommendations.append(
                OptimizationRecommendation(
                    resource_id=profile.resource_id,
                    message=(
                        "Resource spends most of the window idle; enforce shutdown or scale-to-zero policies."
                    ),
                    severity="high",
                    metadata={
                        "average_utilisation": round(average_utilisation, 4),
                        "total_cost": round(profile.total_cost, 2),
                    },
                    category="idle_shutdown",
                )
            )

        return recommendations

    def _build_deduplication_key(
        self, profile: ResourceProfile
    ) -> tuple[str, ...] | None:
        metadata = profile.metadata
        key_parts: list[str] = []
        for key_name in ("workload_id", "model_id", "dataset_id"):
            value = metadata.get(key_name)
            if value:
                key_parts.append(f"{key_name}:{value}")
        env = metadata.get("env")
        if env:
            key_parts.append(f"env:{env}")
        if len(key_parts) >= 2:
            return tuple(sorted(key_parts))
        return None

    def _build_cloud_profile_recommendations(
        self, cloud_costs: Mapping[str, float]
    ) -> list[OptimizationRecommendation]:
        if not cloud_costs:
            return []
        sorted_clouds = sorted(
            cloud_costs.items(), key=lambda item: item[1], reverse=True
        )
        top_cloud, top_cost = sorted_clouds[0]
        recommendations = [
            OptimizationRecommendation(
                resource_id=f"cloud:{top_cloud}",
                message=(
                    "Cloud spend profile updated; validate placement and leverage provider-native cost optimisation programmes."
                ),
                severity="medium",
                metadata={"cloud": top_cloud, "total_cost": round(top_cost, 2)},
                category="cloud_profile",
            )
        ]
        if len(sorted_clouds) > 1:
            tail_cost = sum(cost for _, cost in sorted_clouds[1:])
            recommendations.append(
                OptimizationRecommendation(
                    resource_id="cloud:long_tail",
                    message=(
                        "Fragmented tail spend detected across secondary clouds; review consolidation or shared services."
                    ),
                    severity="low",
                    metadata={"tail_cost": round(tail_cost, 2)},
                    category="cloud_profile",
                )
            )
        return recommendations

    def _collect_budget_statuses(
        self, as_of: datetime, metadata_filter: Mapping[str, str] | None
    ) -> tuple[BudgetStatus, ...]:
        statuses = []
        for status in self.iter_budget_statuses(as_of=as_of):
            if metadata_filter and not self._scope_matches_filter(
                status.budget.scope, metadata_filter
            ):
                continue
            statuses.append(status)
        return tuple(sorted(statuses, key=lambda status: status.budget.name))

    def _derive_budget_recommendations(
        self, statuses: Sequence[BudgetStatus]
    ) -> list[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []
        for status in statuses:
            metadata = {
                "utilisation": round(status.utilisation, 4),
                "remaining": round(status.remaining, 2),
                "limit": round(status.budget.limit, 2),
                "currency": status.budget.currency,
            }
            if status.utilisation >= 0.8 or status.breached:
                severity = "critical" if status.breached else "high"
                recommendations.append(
                    OptimizationRecommendation(
                        resource_id=status.budget.name,
                        message=(
                            "Budget utilisation nearing limit; enforce guardrails, reprioritise workloads, or rebalance reservations."
                        ),
                        severity=severity,
                        metadata=metadata,
                        category="budget",
                    )
                )
            else:
                recommendations.append(
                    OptimizationRecommendation(
                        resource_id=status.budget.name,
                        message=(
                            "Budget usage within thresholds; keep monitoring with automated guardrails enabled."
                        ),
                        severity="low",
                        metadata=metadata,
                        category="budget",
                    )
                )

            if status.breached:
                recommendations.append(
                    OptimizationRecommendation(
                        resource_id=status.budget.name,
                        message=(
                            "Budget breached; trigger overspend playbook and notify accountable owners immediately."
                        ),
                        severity="critical",
                        metadata=metadata,
                        category="overspend_alert",
                    )
                )

        return recommendations

    def _build_weekly_review_schedule(
        self, reference: datetime, *, count: int = 4, weekday: int = 0, hour: int = 15
    ) -> tuple[datetime, ...]:
        tz = reference.tzinfo or timezone.utc
        baseline = reference.astimezone(tz)
        baseline = baseline.replace(hour=hour, minute=0, second=0, microsecond=0)
        days_ahead = (weekday - baseline.weekday()) % 7
        if days_ahead == 0 and baseline <= reference:
            days_ahead = 7
        first_review = baseline + timedelta(days=days_ahead)
        schedule = [first_review + timedelta(days=7 * idx) for idx in range(count)]
        return tuple(schedule)

    def _deduplicate_recommendations(
        self, recommendations: Sequence[OptimizationRecommendation]
    ) -> list[OptimizationRecommendation]:
        seen: set[tuple[str, str, str]] = set()
        unique: list[OptimizationRecommendation] = []
        for recommendation in recommendations:
            key = (
                recommendation.resource_id,
                recommendation.message,
                recommendation.category,
            )
            if key not in seen:
                unique.append(recommendation)
                seen.add(key)
        return unique

    @staticmethod
    def _most_common_metadata(
        samples: Sequence[ResourceUsageSample], keys: Sequence[str]
    ) -> str | None:
        candidates: Counter[str] = Counter()
        for sample in samples:
            for key in keys:
                value = sample.metadata.get(key)
                if value:
                    candidates[value] += 1
        if not candidates:
            return None
        return candidates.most_common(1)[0][0]

    @staticmethod
    def _parse_float_metadata(metadata: Mapping[str, str], key: str) -> float | None:
        value = metadata.get(key)
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_truthy_metadata(metadata: Mapping[str, str], keys: Sequence[str]) -> bool:
        truthy_values = {"1", "true", "yes", "y", "on", "enabled"}
        for key in keys:
            value = metadata.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                if value.lower() in truthy_values:
                    return True
            elif value:
                return True
        return False

    @staticmethod
    def _scope_matches_filter(
        scope: Mapping[str, str] | None, metadata_filter: Mapping[str, str] | None
    ) -> bool:
        if not metadata_filter:
            return True
        if not scope:
            return True
        for key, value in scope.items():
            if metadata_filter.get(key) != value:
                return False
        return True

    def _sample_matches_scope(
        self, sample: ResourceUsageSample, scope: Mapping[str, str] | None
    ) -> bool:
        if not scope:
            return True
        sample_meta = sample.metadata
        return all(sample_meta.get(key) == value for key, value in scope.items())

    def _insert_ledger_entry(
        self, ledger: list[tuple[datetime, float]], sample: ResourceUsageSample
    ) -> None:
        if not ledger or sample.timestamp >= ledger[-1][0]:
            ledger.append((sample.timestamp, sample.cost))
            return
        timestamps = [entry[0] for entry in ledger]
        index = bisect_left(timestamps, sample.timestamp)
        ledger.insert(index, (sample.timestamp, sample.cost))

    def _prune_and_sum(
        self,
        ledger: list[tuple[datetime, float]],
        budget: Budget,
        as_of: datetime,
    ) -> tuple[float, datetime]:
        cutoff = as_of - budget.period
        while ledger and ledger[0][0] < cutoff:
            ledger.pop(0)
        total_cost = sum(cost for _, cost in ledger)
        window_start = cutoff if ledger else as_of - budget.period
        return total_cost, window_start

    def _evaluate_budget(
        self,
        budget: Budget,
        total_cost: float,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[FinOpsAlert, ...]:
        limit = budget.limit
        utilisation = total_cost / limit if limit else 0.0
        remaining = max(limit - total_cost, 0.0)
        thresholds = budget.alert_thresholds
        current_state = self._budget_thresholds.get(budget.name, 0.0)
        triggered: list[FinOpsAlert] = []

        for threshold in thresholds:
            threshold_cost = limit * threshold
            if total_cost >= threshold_cost and threshold > current_state:
                triggered.append(
                    FinOpsAlert(
                        budget=budget,
                        threshold=threshold,
                        total_cost=total_cost,
                        remaining=remaining,
                        utilisation=utilisation,
                        window_start=window_start,
                        window_end=window_end,
                        breached=threshold >= 1.0 or total_cost >= limit,
                    )
                )
                current_state = max(current_state, threshold)

        if total_cost >= limit and current_state < 1.0:
            triggered.append(
                FinOpsAlert(
                    budget=budget,
                    threshold=1.0,
                    total_cost=total_cost,
                    remaining=remaining,
                    utilisation=utilisation,
                    window_start=window_start,
                    window_end=window_end,
                    breached=True,
                )
            )
            current_state = 1.0

        if triggered:
            self._budget_thresholds[budget.name] = current_state
            for alert in triggered:
                if self._alert_sink is not None:
                    self._alert_sink.handle_alert(alert)
            return tuple(triggered)

        lowest_threshold = thresholds[0] if thresholds else 1.0
        if total_cost < limit * lowest_threshold * 0.8:
            self._budget_thresholds[budget.name] = 0.0
        return ()

    def _slice_samples(
        self,
        samples: Sequence[ResourceUsageSample],
        start: datetime,
        end: datetime,
        metadata_filter: Mapping[str, str] | None,
    ) -> list[ResourceUsageSample]:
        result: list[ResourceUsageSample] = []
        for sample in samples:
            if sample.timestamp < start or sample.timestamp > end:
                continue
            if metadata_filter and not self._sample_matches_scope(
                sample, metadata_filter
            ):
                continue
            result.append(sample)
        return result
