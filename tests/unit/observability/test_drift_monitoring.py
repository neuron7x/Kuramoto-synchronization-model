from __future__ import annotations

import asyncio
import datetime as dt

import numpy as np

from observability.drift import (
    DriftDetector,
    DriftMonitoringService,
    FeatureChangeLog,
    FeatureDriftMetric,
    FeatureDriftSummary,
    FeatureSnapshot,
    ImpactIsolationPlanner,
    IsolationPlan,
    QualityDegradationMonitor,
    QualityDeviation,
    QualityGuardrail,
    RemediationPlanner,
    RetrainingTrigger,
)


def _utc(minutes: int = 0) -> dt.datetime:
    return dt.datetime(2024, 1, 1, 12, minutes, tzinfo=dt.timezone.utc)


def test_drift_detector_evaluates_metrics() -> None:
    reference = np.linspace(0.0, 1.0, 128)
    current = reference + 0.3
    snapshot = FeatureSnapshot("feature_a", reference, current)
    detector = DriftDetector(psi_threshold=0.05, ks_confidence=0.9, bins=8)
    summary = detector.evaluate(snapshot)
    assert summary.feature == "feature_a"
    assert len(summary.metrics) == 2
    assert {metric.metric for metric in summary.metrics} == {"psi", "ks"}


def test_quality_monitor_detects_deviation() -> None:
    monitor = QualityDegradationMonitor(
        [
            QualityGuardrail(
                metric="accuracy", lower=0.8, warning_margin=0.05, critical_margin=0.1
            )
        ]
    )
    deviations = monitor.evaluate({"accuracy": 0.69})
    assert len(deviations) == 1
    deviation = deviations[0]
    assert deviation.metric == "accuracy"
    assert deviation.severity == "critical"


def test_retraining_trigger_requires_multiple_events() -> None:
    trigger = RetrainingTrigger(
        window=dt.timedelta(minutes=10), min_events=2, min_features=1
    )
    first = trigger.evaluate(_utc(0), ["feature_a"])
    assert not first.triggered
    second = trigger.evaluate(_utc(5), ["feature_a"])
    assert second.triggered
    assert second.features == ("feature_a",)


def test_remediation_planner_builds_actions() -> None:
    summary = FeatureDriftSummary(
        feature="feature_a",
        metrics=(
            FeatureDriftMetric(
                feature="feature_a",
                metric="psi",
                value=0.6,
                threshold=0.2,
                drifted=True,
                details={},
            ),
        ),
        drifted=True,
        metadata={"domain": "alpha"},
    )
    deviation = QualityDeviation(
        metric="latency",
        value=350.0,
        lower=None,
        upper=300.0,
        severity="critical",
    )
    planner = RemediationPlanner()
    plan = planner.plan([summary], [deviation], retraining_triggered=True)
    assert plan.requires_ack
    actions = {action.action for action in plan.actions}
    assert "quarantine_feature" in actions
    assert "quality_review" in actions
    assert "schedule_retraining" in actions


class _StubDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def dispatch(
        self,
        event: str,
        *,
        subject: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        self.calls.append((event, subject, message))


def test_monitoring_service_generates_alerts_and_dashboard() -> None:
    detector = DriftDetector(psi_threshold=0.05, ks_confidence=0.9, bins=6)
    quality_monitor = QualityDegradationMonitor(
        [
            QualityGuardrail(
                metric="latency",
                upper=300.0,
                warning_margin=0.05,
                critical_margin=0.1,
            )
        ]
    )
    remediation_planner = RemediationPlanner()
    retraining_trigger = RetrainingTrigger(
        window=dt.timedelta(minutes=30), min_events=1, min_features=1
    )
    isolation_planner = ImpactIsolationPlanner(
        quarantine_severities=("major", "critical")
    )
    change_log = FeatureChangeLog(max_records=10)
    change_log.record("feature_a", "backfill", author="alice")
    dispatcher = _StubDispatcher()

    service = DriftMonitoringService(
        detector=detector,
        quality_monitor=quality_monitor,
        remediation_planner=remediation_planner,
        retraining_trigger=retraining_trigger,
        isolation_planner=isolation_planner,
        change_log=change_log,
        dispatcher=dispatcher,
        clock=lambda: _utc(0),
    )

    reference = np.linspace(0.0, 1.0, 256)
    current = reference + 0.5
    snapshot = FeatureSnapshot("feature_a", reference, current)
    report = service.evaluate([snapshot], {"latency": 330.0})

    assert report.drift_summaries[0].feature == "feature_a"
    assert report.quality_deviations[0].metric == "latency"
    assert report.retraining_decision.triggered
    assert report.isolation_plan.decisions
    assert report.remediation_plan.actions
    assert report.alerts
    assert "features" in report.dashboard_snapshot

    asyncio.run(service.dispatch_alerts(report))
    assert dispatcher.calls


def test_isolation_plan_reports_monitor_state() -> None:
    summary = FeatureDriftSummary(
        feature="feature_a",
        metrics=(
            FeatureDriftMetric(
                feature="feature_a",
                metric="psi",
                value=0.3,
                threshold=0.1,
                drifted=True,
                details={},
            ),
        ),
        drifted=True,
        metadata={},
    )
    planner = ImpactIsolationPlanner(quarantine_severities=("critical",))
    plan = planner.plan([summary])
    assert isinstance(plan, IsolationPlan)
    assert plan.decisions[0].isolate
