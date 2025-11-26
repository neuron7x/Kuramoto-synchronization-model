from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import pytest
from prometheus_client import CollectorRegistry

from core.utils import metrics as metrics_module
from observability.response_quality import (
    GoldenDataset,
    GoldenRecord,
    QualityContract,
    QualityContractViolation,
    ResponseQualityConfig,
    ResponseQualityOrchestrator,
)

UTC = timezone.utc


def _sample(
    registry: CollectorRegistry, name: str, labels: Mapping[str, str]
) -> float | None:
    return registry.get_sample_value(name, labels)


class FakeClock:
    def __init__(self) -> None:
        self._time = 0.0
        self._start = datetime(2024, 1, 1, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self._time += seconds

    def monotonic(self) -> float:
        return self._time

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._time)


@pytest.fixture()
def metrics_registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    registry = CollectorRegistry()
    collector = metrics_module.MetricsCollector(registry)
    monkeypatch.setattr(metrics_module, "_collector", collector, raising=False)
    yield registry
    monkeypatch.setattr(metrics_module, "_collector", None, raising=False)


def test_run_golden_checks_detects_regression(
    metrics_registry: CollectorRegistry, tmp_path: Path
) -> None:
    clock = FakeClock()
    config = ResponseQualityConfig(
        model_name="qa-model",
        environment="prod",
        baseline_tolerance=0.05,
        incident_root=tmp_path,
        degradation_cooldown_seconds=0.0,
    )

    records = (
        GoldenRecord(
            identifier="rec-1",
            request={"value": 1},
            expected={"output": 2},
            tags=("critical",),
        ),
        GoldenRecord(
            identifier="rec-2",
            request={"value": 2},
            expected={"output": 4},
            tags=("shadow",),
        ),
    )
    dataset = GoldenDataset(name="golden-alpha", version="1.0.0", records=records)

    def responder(payload: Mapping[str, object]) -> Mapping[str, object]:
        clock.advance(0.05)
        value = int(payload["value"]) * 2
        if payload["value"] == 2:
            value -= 1
        return {"output": value}

    orchestrator = ResponseQualityOrchestrator(
        config,
        responder=responder,
        monotonic=clock.monotonic,
        now=clock.now,
    )
    orchestrator.register_golden_dataset(dataset)
    orchestrator.configure_dataset_baseline("golden-alpha", score=1.0, tolerance=0.01)

    results = orchestrator.run_golden_checks()
    summary = results["golden-alpha"]
    assert summary.total == 2
    assert summary.mismatches == 1
    assert summary.score == pytest.approx(0.5)
    assert summary.partial is False
    assert summary.latency_avg_ms > 0.0

    degradations = orchestrator.latest_degradations()
    assert degradations, "expected degradation when score drops below baseline"
    degradation = degradations[-1]
    assert degradation.metric == "golden-alpha.score"
    assert degradation.severity > 0.0
    assert degradation.reason in orchestrator.reason_map()

    reviews = orchestrator.pending_reviews()
    assert reviews and reviews[0].reason == "mismatch"

    run_count = _sample(
        metrics_registry,
        "tradepulse_response_quality_run_total",
        {
            "model_name": "qa-model",
            "deployment": "prod",
            "dataset": "golden-alpha",
            "mode": "full",
            "status": "fail",
        },
    )
    assert run_count == 1.0

    degradation_counter = _sample(
        metrics_registry,
        "tradepulse_response_quality_degradation_events_total",
        {
            "model_name": "qa-model",
            "deployment": "prod",
            "dataset": "golden-alpha",
            "reason": degradation.reason,
        },
    )
    assert degradation_counter == 1.0

    pending_gauge = _sample(
        metrics_registry,
        "tradepulse_response_quality_pending_reviews",
        {"model_name": "qa-model", "deployment": "prod"},
    )
    assert pending_gauge == len(reviews)


def test_partial_checks_and_contract_enforcement(
    metrics_registry: CollectorRegistry,
) -> None:
    clock = FakeClock()
    config = ResponseQualityConfig(
        model_name="qa-model",
        environment="prod",
        degradation_cooldown_seconds=0.0,
    )

    records = (
        GoldenRecord(
            identifier="rec-1",
            request={"value": 1},
            expected={"value": 2, "confidence": 0.3},
            tags=("critical",),
        ),
        GoldenRecord(
            identifier="rec-2",
            request={"value": 2},
            expected={"value": 4, "confidence": 0.9},
            tags=("optional",),
        ),
    )
    dataset = GoldenDataset(name="golden-beta", version="2.0.0", records=records)

    def responder(payload: Mapping[str, object]) -> Mapping[str, object]:
        clock.advance(0.02)
        value = int(payload["value"]) * 2
        confidence = 0.3 if payload["value"] == 1 else 0.9
        return {"value": value, "confidence": confidence}

    def validator(response: Mapping[str, object]) -> QualityContractViolation | None:
        confidence = float(response.get("confidence", 0.0))
        if confidence < 0.5:
            return QualityContractViolation(
                contract="confidence_floor",
                message="confidence below threshold",
                details={"confidence": confidence},
            )
        return None

    orchestrator = ResponseQualityOrchestrator(
        config,
        responder=responder,
        monotonic=clock.monotonic,
        now=clock.now,
    )
    orchestrator.register_golden_dataset(dataset)
    orchestrator.register_contract(
        QualityContract(
            name="confidence_floor",
            description="Ensure inference confidence stays above 0.5",
            validator=validator,
        )
    )

    results = orchestrator.run_golden_checks(tags={"critical"})
    summary = results["golden-beta"]
    assert summary.total == 1
    assert summary.partial is True
    assert summary.contract_failures == 1
    assert summary.mismatches == 0

    reviews = orchestrator.pending_reviews()
    assert any(review.reason.startswith("contract:") for review in reviews)

    violations = _sample(
        metrics_registry,
        "tradepulse_response_quality_contract_violations_total",
        {
            "model_name": "qa-model",
            "deployment": "prod",
            "dataset": "golden-beta",
            "contract": "confidence_floor",
        },
    )
    assert violations == 1.0

    degradations = orchestrator.latest_degradations()
    assert degradations, "contract violation should trigger degradation"
    contract_degradation = degradations[-1]
    assert contract_degradation.metric == "golden-beta.contracts"
    assert "confidence_floor" in contract_degradation.reason

    run_count = _sample(
        metrics_registry,
        "tradepulse_response_quality_run_total",
        {
            "model_name": "qa-model",
            "deployment": "prod",
            "dataset": "golden-beta",
            "mode": "partial",
            "status": "fail",
        },
    )
    assert run_count == 1.0


def test_active_sampling_complaints_and_improvements(
    metrics_registry: CollectorRegistry,
) -> None:
    clock = FakeClock()
    config = ResponseQualityConfig(model_name="qa-model", environment="prod")

    orchestrator = ResponseQualityOrchestrator(
        config,
        responder=lambda payload: payload,
        monotonic=clock.monotonic,
        now=clock.now,
    )

    orchestrator.record_live_response(
        {"feature": 1}, {"prediction": 0.2, "confidence": 0.8}
    )
    sample = orchestrator.record_live_response(
        {"feature": 2},
        {"prediction": 0.1, "confidence": 0.05},
    )
    assert sample is not None
    next_sample = orchestrator.next_active_sample()
    assert next_sample is not None and next_sample.identifier == sample.identifier

    orchestrator.register_complaint_route("bias", lambda category, metadata: "ethics")
    complaint = orchestrator.route_complaint(
        "bias", "potential drift", metadata={"ticket": 42}
    )
    assert complaint.route == "ethics"
    assert complaint in orchestrator.complaints()

    improvement = orchestrator.record_improvement(
        "Audit recent degradation",
        owner="quality-team",
        metadata={"origin": "automated"},
    )
    assert improvement in orchestrator.improvements()

    complaint_metric = _sample(
        metrics_registry,
        "tradepulse_response_quality_complaints_total",
        {
            "model_name": "qa-model",
            "deployment": "prod",
            "category": "bias",
            "route": "ethics",
        },
    )
    assert complaint_metric == 1.0

    reason_map = orchestrator.reason_map()
    assert "complaint:bias" in reason_map
