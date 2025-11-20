"""Comprehensive data/model drift monitoring utilities."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

from core.altdata import DistributionDriftMonitor, DriftAssessment

from .notifications import NotificationDispatcher


@dataclass(frozen=True)
class FeatureSnapshot:
    """Reference and current samples for a feature."""

    name: str
    reference: Sequence[float]
    current: Sequence[float]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureDriftMetric:
    """Single drift metric result for a feature."""

    feature: str
    metric: str
    value: float
    threshold: float
    drifted: bool
    details: Mapping[str, float]

    @property
    def severity(self) -> str:
        """Classify severity relative to the configured threshold."""

        if self.threshold <= 0:
            return "unknown"
        ratio = self.value / self.threshold
        if ratio >= 2.0:
            return "critical"
        if ratio >= 1.0:
            return "major"
        if ratio >= 0.75:
            return "warning"
        return "info"


@dataclass(frozen=True)
class FeatureDriftSummary:
    """Aggregated drift metrics for a single feature."""

    feature: str
    metrics: tuple[FeatureDriftMetric, ...]
    drifted: bool
    metadata: Mapping[str, Any]

    @property
    def worst_severity(self) -> str:
        """Return the worst severity observed for the feature."""

        order = {"info": 0, "warning": 1, "major": 2, "critical": 3, "unknown": 4}
        worst = "info"
        for metric in self.metrics:
            current = metric.severity
            if order[current] > order[worst]:
                worst = current
        return worst


class DriftDetector:
    """Compute PSI and KS drift metrics for features."""

    def __init__(
        self,
        *,
        psi_threshold: float = 0.2,
        ks_confidence: float = 0.95,
        bins: int = 10,
    ) -> None:
        if not 0 < psi_threshold < 10:
            raise ValueError("psi_threshold must be within (0, 10)")
        if not 0 < ks_confidence < 1:
            raise ValueError("ks_confidence must be within (0, 1)")
        self._psi_monitor = DistributionDriftMonitor(
            method="psi", threshold=psi_threshold, bins=bins
        )
        self._ks_monitor = DistributionDriftMonitor(
            method="ks", threshold=ks_confidence, bins=bins
        )
        self._ks_alpha = 1.0 - ks_confidence

    def evaluate(self, snapshot: FeatureSnapshot) -> FeatureDriftSummary:
        psi_assessment = self._psi_monitor.assess(snapshot.reference, snapshot.current)
        ks_assessment = self._ks_monitor.assess(snapshot.reference, snapshot.current)
        metrics = (
            self._build_metric(snapshot.name, psi_assessment),
            self._build_metric(snapshot.name, ks_assessment, ks=True),
        )
        drifted = any(metric.drifted for metric in metrics)
        return FeatureDriftSummary(
            feature=snapshot.name,
            metrics=metrics,
            drifted=drifted,
            metadata=dict(snapshot.metadata),
        )

    def _build_metric(
        self, feature: str, assessment: DriftAssessment, *, ks: bool = False
    ) -> FeatureDriftMetric:
        threshold = assessment.threshold
        details: Mapping[str, float] = assessment.details
        value = assessment.value
        if ks:
            pvalue = float(assessment.details.get("pvalue", 1.0))
            value = max(0.0, min(1.0, 1.0 - pvalue))
            details = {
                **assessment.details,
                "statistic": assessment.value,
                "confidence": assessment.threshold,
                "alpha": self._ks_alpha,
            }
        return FeatureDriftMetric(
            feature=feature,
            metric=assessment.metric,
            value=value,
            threshold=threshold,
            drifted=assessment.drifted,
            details=details,
        )


@dataclass(frozen=True)
class QualityGuardrail:
    """Guardrail definitions for production quality metrics."""

    metric: str
    lower: float | None = None
    upper: float | None = None
    warning_margin: float = 0.1
    critical_margin: float = 0.25

    def validate(self) -> None:
        if self.lower is None and self.upper is None:
            raise ValueError("At least one of lower/upper must be specified")
        if self.warning_margin <= 0 or self.critical_margin <= 0:
            raise ValueError("Margins must be positive")
        if self.warning_margin >= self.critical_margin:
            raise ValueError("warning_margin must be less than critical_margin")


@dataclass(frozen=True)
class QualityDeviation:
    """Deviation of a live metric outside configured guardrails."""

    metric: str
    value: float
    lower: float | None
    upper: float | None
    severity: str


class QualityDegradationMonitor:
    """Monitor production metrics for quality degradation."""

    def __init__(self, guardrails: Sequence[QualityGuardrail]) -> None:
        if not guardrails:
            raise ValueError("At least one guardrail must be defined")
        for guardrail in guardrails:
            guardrail.validate()
        self._guardrails = {guardrail.metric: guardrail for guardrail in guardrails}

    def evaluate(self, metrics: Mapping[str, float]) -> tuple[QualityDeviation, ...]:
        deviations = []
        for metric, guardrail in self._guardrails.items():
            if metric not in metrics:
                continue
            value = metrics[metric]
            severity = self._classify(value, guardrail)
            if severity is None:
                continue
            deviations.append(
                QualityDeviation(
                    metric=metric,
                    value=float(value),
                    lower=guardrail.lower,
                    upper=guardrail.upper,
                    severity=severity,
                )
            )
        return tuple(deviations)

    def _classify(self, value: float, guardrail: QualityGuardrail) -> str | None:
        lower = guardrail.lower
        upper = guardrail.upper
        if lower is not None and value < lower:
            magnitude = self._relative_delta(value, lower, below=True)
            return self._severity(magnitude, guardrail)
        if upper is not None and value > upper:
            magnitude = self._relative_delta(value, upper, below=False)
            return self._severity(magnitude, guardrail)
        return None

    @staticmethod
    def _relative_delta(value: float, bound: float, *, below: bool) -> float:
        if bound == 0:
            return abs(value)
        delta = abs(bound - value)
        ratio = delta / abs(bound)
        return ratio if below else ratio

    @staticmethod
    def _severity(magnitude: float, guardrail: QualityGuardrail) -> str:
        if magnitude >= guardrail.critical_margin:
            return "critical"
        if magnitude >= guardrail.warning_margin:
            return "warning"
        return "info"


@dataclass(frozen=True)
class RemediationAction:
    """Concrete remediation action to mitigate drift."""

    action: str
    target: str
    severity: str
    rationale: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class RemediationPlan:
    """Collection of remediation actions."""

    actions: tuple[RemediationAction, ...]
    requires_ack: bool


class RemediationPlanner:
    """Construct remediation plans from drift and quality signals."""

    def plan(
        self,
        drift_summaries: Sequence[FeatureDriftSummary],
        quality_deviations: Sequence[QualityDeviation],
        retraining_triggered: bool,
    ) -> RemediationPlan:
        actions: list[RemediationAction] = []
        requires_ack = False

        for summary in drift_summaries:
            if not summary.drifted:
                continue
            severity = summary.worst_severity
            rationale = "distribution drift exceeds guardrails"
            metadata: MutableMapping[str, Any] = {
                metric.metric: metric.value for metric in summary.metrics
            }
            metadata.update(summary.metadata)
            actions.append(
                RemediationAction(
                    action="quarantine_feature",
                    target=summary.feature,
                    severity=severity,
                    rationale=rationale,
                    metadata=dict(metadata),
                )
            )
            if severity in {"major", "critical"}:
                requires_ack = True

        for deviation in quality_deviations:
            actions.append(
                RemediationAction(
                    action="quality_review",
                    target=deviation.metric,
                    severity=deviation.severity,
                    rationale="production metric outside guardrail",
                    metadata={
                        "value": deviation.value,
                        "lower": (
                            deviation.lower
                            if deviation.lower is not None
                            else float("nan")
                        ),
                        "upper": (
                            deviation.upper
                            if deviation.upper is not None
                            else float("nan")
                        ),
                    },
                )
            )
            if deviation.severity == "critical":
                requires_ack = True

        if retraining_triggered:
            actions.append(
                RemediationAction(
                    action="schedule_retraining",
                    target="model",
                    severity="major",
                    rationale="retraining trigger threshold exceeded",
                    metadata={},
                )
            )
            requires_ack = True

        return RemediationPlan(actions=tuple(actions), requires_ack=requires_ack)


@dataclass(frozen=True)
class IsolationDecision:
    """Decision describing whether to isolate a feature."""

    feature: str
    isolate: bool
    reason: str
    severity: str


@dataclass(frozen=True)
class IsolationPlan:
    """Plan describing feature isolation for drift containment."""

    decisions: tuple[IsolationDecision, ...]


class ImpactIsolationPlanner:
    """Recommend isolation of severely drifted features."""

    def __init__(self, *, quarantine_severities: Iterable[str] = ("critical",)) -> None:
        self._quarantine = set(quarantine_severities)

    def plan(self, summaries: Sequence[FeatureDriftSummary]) -> IsolationPlan:
        decisions = []
        for summary in summaries:
            severity = summary.worst_severity
            if severity in self._quarantine and summary.drifted:
                decisions.append(
                    IsolationDecision(
                        feature=summary.feature,
                        isolate=True,
                        reason="severity threshold exceeded",
                        severity=severity,
                    )
                )
            elif summary.drifted:
                decisions.append(
                    IsolationDecision(
                        feature=summary.feature,
                        isolate=False,
                        reason="monitor",
                        severity=severity,
                    )
                )
        return IsolationPlan(decisions=tuple(decisions))


@dataclass(frozen=True)
class FeatureChangeRecord:
    """Audit entry for feature changes."""

    timestamp: dt.datetime
    feature: str
    change_type: str
    author: str | None
    metadata: Mapping[str, Any]


class FeatureChangeLog:
    """In-memory log capturing feature changes relevant to drift."""

    def __init__(self, *, max_records: int = 500) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self._max_records = max_records
        self._records: Deque[FeatureChangeRecord] = deque()

    def record(
        self,
        feature: str,
        change_type: str,
        *,
        author: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        timestamp: dt.datetime | None = None,
    ) -> FeatureChangeRecord:
        ts = timestamp or dt.datetime.now(dt.timezone.utc)
        record = FeatureChangeRecord(
            timestamp=ts,
            feature=feature,
            change_type=change_type,
            author=author,
            metadata=dict(metadata or {}),
        )
        self._records.append(record)
        while len(self._records) > self._max_records:
            self._records.popleft()
        return record

    def history(
        self, feature: str | None = None, *, limit: int | None = None
    ) -> tuple[FeatureChangeRecord, ...]:
        records = (
            record
            for record in reversed(self._records)
            if feature is None or record.feature == feature
        )
        if limit is None:
            return tuple(records)
        result = []
        for record in records:
            result.append(record)
            if len(result) >= limit:
                break
        return tuple(result)


@dataclass(frozen=True)
class RetrainingDecision:
    """Result of evaluating whether retraining should be triggered."""

    triggered: bool
    reason: str | None
    features: tuple[str, ...]
    window: dt.timedelta


class RetrainingTrigger:
    """Trigger retraining when repeated drift occurs within a window."""

    def __init__(
        self,
        *,
        window: dt.timedelta = dt.timedelta(hours=1),
        min_events: int = 3,
        min_features: int = 2,
    ) -> None:
        if window.total_seconds() <= 0:
            raise ValueError("window must be positive")
        if min_events <= 0 or min_features <= 0:
            raise ValueError("Thresholds must be positive")
        self._window = window
        self._min_events = min_events
        self._min_features = min_features
        self._events: Deque[tuple[dt.datetime, tuple[str, ...]]] = deque()

    def evaluate(
        self, timestamp: dt.datetime, drifted_features: Sequence[str]
    ) -> RetrainingDecision:
        drifted = tuple(sorted(set(drifted_features)))
        if drifted:
            self._events.append((timestamp, drifted))
        self._prune(timestamp)
        if not drifted:
            return RetrainingDecision(False, None, tuple(), self._window)

        total_events = len(self._events)
        feature_counts = Counter()
        for _, features in self._events:
            feature_counts.update(features)
        if total_events < self._min_events:
            return RetrainingDecision(False, None, tuple(), self._window)
        active_features = [
            feature for feature, count in feature_counts.items() if count > 0
        ]
        if len(active_features) < self._min_features:
            return RetrainingDecision(False, None, tuple(), self._window)

        reason = (
            "drift persistence"
            if total_events >= self._min_events
            else "insufficient events"
        )
        return RetrainingDecision(
            True, reason, tuple(sorted(active_features)), self._window
        )

    def _prune(self, timestamp: dt.datetime) -> None:
        boundary = timestamp - self._window
        while self._events and self._events[0][0] < boundary:
            self._events.popleft()


@dataclass(frozen=True)
class DriftAlert:
    """Alert describing drift or quality degradation."""

    severity: str
    subject: str
    message: str
    metadata: Mapping[str, Any]


class DriftDashboard:
    """Render state snapshots for dashboards."""

    def render(
        self,
        timestamp: dt.datetime,
        summaries: Sequence[FeatureDriftSummary],
        quality_deviations: Sequence[QualityDeviation],
        isolation_plan: IsolationPlan,
        remediation_plan: RemediationPlan,
        change_log: FeatureChangeLog,
    ) -> Mapping[str, Any]:
        return {
            "timestamp": timestamp.isoformat(),
            "features": [
                {
                    "name": summary.feature,
                    "drifted": summary.drifted,
                    "severity": summary.worst_severity,
                    "metrics": [
                        {
                            "metric": metric.metric,
                            "value": metric.value,
                            "threshold": metric.threshold,
                            "drifted": metric.drifted,
                        }
                        for metric in summary.metrics
                    ],
                }
                for summary in summaries
            ],
            "quality": [
                {
                    "metric": deviation.metric,
                    "value": deviation.value,
                    "severity": deviation.severity,
                }
                for deviation in quality_deviations
            ],
            "isolation": [
                {
                    "feature": decision.feature,
                    "isolate": decision.isolate,
                    "severity": decision.severity,
                    "reason": decision.reason,
                }
                for decision in isolation_plan.decisions
            ],
            "remediation": [
                {
                    "action": action.action,
                    "target": action.target,
                    "severity": action.severity,
                }
                for action in remediation_plan.actions
            ],
            "feature_changes": [
                {
                    "timestamp": record.timestamp.isoformat(),
                    "feature": record.feature,
                    "change_type": record.change_type,
                    "author": record.author,
                }
                for record in change_log.history(limit=20)
            ],
        }


@dataclass(frozen=True)
class DriftMonitoringReport:
    """End-to-end report for a monitoring cycle."""

    timestamp: dt.datetime
    drift_summaries: tuple[FeatureDriftSummary, ...]
    quality_deviations: tuple[QualityDeviation, ...]
    isolation_plan: IsolationPlan
    remediation_plan: RemediationPlan
    retraining_decision: RetrainingDecision
    alerts: tuple[DriftAlert, ...]
    dashboard_snapshot: Mapping[str, Any]


class DriftMonitoringService:
    """Coordinate drift detection, remediation, and alerting."""

    def __init__(
        self,
        *,
        detector: DriftDetector,
        quality_monitor: QualityDegradationMonitor,
        remediation_planner: RemediationPlanner,
        retraining_trigger: RetrainingTrigger,
        isolation_planner: ImpactIsolationPlanner,
        change_log: FeatureChangeLog,
        dispatcher: NotificationDispatcher | None = None,
        dashboard: DriftDashboard | None = None,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._detector = detector
        self._quality_monitor = quality_monitor
        self._remediation_planner = remediation_planner
        self._retraining_trigger = retraining_trigger
        self._isolation_planner = isolation_planner
        self._change_log = change_log
        self._dispatcher = dispatcher
        self._dashboard = dashboard or DriftDashboard()
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def evaluate(
        self,
        snapshots: Sequence[FeatureSnapshot],
        live_metrics: Mapping[str, float],
    ) -> DriftMonitoringReport:
        timestamp = self._clock()
        summaries = tuple(self._detector.evaluate(snapshot) for snapshot in snapshots)
        quality = self._quality_monitor.evaluate(live_metrics)
        drifted_features = [summary.feature for summary in summaries if summary.drifted]
        retraining = self._retraining_trigger.evaluate(timestamp, drifted_features)
        isolation = self._isolation_planner.plan(summaries)
        remediation = self._remediation_planner.plan(
            summaries, quality, retraining.triggered
        )
        alerts = self._build_alerts(summaries, quality, remediation, retraining)
        dashboard = self._dashboard.render(
            timestamp, summaries, quality, isolation, remediation, self._change_log
        )
        report = DriftMonitoringReport(
            timestamp=timestamp,
            drift_summaries=summaries,
            quality_deviations=quality,
            isolation_plan=isolation,
            remediation_plan=remediation,
            retraining_decision=retraining,
            alerts=tuple(alerts),
            dashboard_snapshot=dashboard,
        )
        return report

    async def dispatch_alerts(self, report: DriftMonitoringReport) -> None:
        if self._dispatcher is None:
            return
        tasks = [
            self._dispatcher.dispatch(
                "drift.alert",
                subject=alert.subject,
                message=alert.message,
                metadata=alert.metadata,
            )
            for alert in report.alerts
        ]
        if tasks:
            await asyncio.gather(*tasks)

    def _build_alerts(
        self,
        summaries: Sequence[FeatureDriftSummary],
        quality: Sequence[QualityDeviation],
        remediation: RemediationPlan,
        retraining: RetrainingDecision,
    ) -> list[DriftAlert]:
        alerts: list[DriftAlert] = []
        for summary in summaries:
            if summary.drifted:
                metadata = {metric.metric: metric.value for metric in summary.metrics}
                metadata.update(summary.metadata)
                alerts.append(
                    DriftAlert(
                        severity=summary.worst_severity,
                        subject=f"Feature drift detected: {summary.feature}",
                        message="Distribution drift exceeds tolerance",
                        metadata=metadata,
                    )
                )
        for deviation in quality:
            alerts.append(
                DriftAlert(
                    severity=deviation.severity,
                    subject=f"Quality degradation: {deviation.metric}",
                    message="Live metric outside guardrail",
                    metadata={
                        "value": deviation.value,
                        "lower": deviation.lower,
                        "upper": deviation.upper,
                    },
                )
            )
        if retraining.triggered:
            alerts.append(
                DriftAlert(
                    severity="major",
                    subject="Retraining triggered",
                    message=retraining.reason or "Retraining conditions met",
                    metadata={"features": retraining.features},
                )
            )
        if remediation.requires_ack:
            alerts.append(
                DriftAlert(
                    severity="critical",
                    subject="Remediation approval required",
                    message="Manual acknowledgement required for remediation plan",
                    metadata={
                        "actions": [action.action for action in remediation.actions]
                    },
                )
            )
        return alerts


__all__ = [
    "DriftDetector",
    "FeatureSnapshot",
    "FeatureDriftMetric",
    "FeatureDriftSummary",
    "QualityGuardrail",
    "QualityDegradationMonitor",
    "QualityDeviation",
    "RemediationPlanner",
    "RemediationAction",
    "RemediationPlan",
    "ImpactIsolationPlanner",
    "IsolationPlan",
    "IsolationDecision",
    "FeatureChangeLog",
    "FeatureChangeRecord",
    "RetrainingTrigger",
    "RetrainingDecision",
    "DriftMonitoringService",
    "DriftMonitoringReport",
    "DriftDashboard",
    "DriftAlert",
]
