from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import CollectorRegistry

from core.utils import metrics as metrics_module
from observability.model_monitoring import (
    ModelObservabilityConfig,
    ModelObservabilityOrchestrator,
    ResourceSnapshot,
)

UTC = timezone.utc


class FakeClock:
    """Deterministic clock helper for orchestrator tests."""

    def __init__(self) -> None:
        self._time = 0.0
        self._start = datetime(2024, 1, 1, tzinfo=UTC)

    def advance(self, delta: float) -> None:
        self._time += delta

    def perf_counter(self) -> float:
        return self._time

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


def _sample(
    registry: CollectorRegistry, name: str, labels: dict[str, str]
) -> float | None:
    return registry.get_sample_value(name, labels)


def test_trace_inference_records_metrics(
    metrics_registry: CollectorRegistry, tmp_path
) -> None:
    clock = FakeClock()
    config = ModelObservabilityConfig(
        model_name="alpha",
        environment="prod",
        latency_sla_ms=80.0,
        error_rate_threshold=0.5,
        max_requests_per_second=100.0,
        incident_root=tmp_path,
        degradation_cooldown_seconds=0.0,
    )
    orchestrator = ModelObservabilityOrchestrator(
        config,
        perf_counter=clock.perf_counter,
        monotonic=clock.monotonic,
        now=clock.now,
    )

    resource_snapshot = ResourceSnapshot(
        cpu_percent=42.0,
        memory_percent=55.0,
        memory_bytes=1.2e9,
        saturation=0.7,
        cache_name="embeddings",
        cache_hit_ratio=0.91,
        cache_entries=2048,
        cache_evictions=2,
    )
    orchestrator.update_resource_usage(snapshot=resource_snapshot)

    with orchestrator.trace_inference("req-1"):
        clock.advance(0.05)

    latency_count = _sample(
        metrics_registry,
        "tradepulse_model_inference_latency_seconds_count",
        {"model_name": "alpha", "deployment": "prod"},
    )
    throughput = _sample(
        metrics_registry,
        "tradepulse_model_inference_throughput_per_second",
        {"model_name": "alpha", "deployment": "prod"},
    )
    error_ratio = _sample(
        metrics_registry,
        "tradepulse_model_inference_error_ratio",
        {"model_name": "alpha", "deployment": "prod"},
    )
    saturation = _sample(
        metrics_registry,
        "tradepulse_model_saturation",
        {"model_name": "alpha", "deployment": "prod"},
    )
    cpu_percent = _sample(
        metrics_registry,
        "tradepulse_model_cpu_percent",
        {"model_name": "alpha", "deployment": "prod"},
    )
    memory_percent = _sample(
        metrics_registry,
        "tradepulse_model_memory_percent",
        {"model_name": "alpha", "deployment": "prod"},
    )
    cache_hits = _sample(
        metrics_registry,
        "tradepulse_model_cache_hit_ratio",
        {"model_name": "alpha", "deployment": "prod", "cache_name": "embeddings"},
    )
    evictions = _sample(
        metrics_registry,
        "tradepulse_model_cache_evictions_total",
        {"model_name": "alpha", "deployment": "prod", "cache_name": "embeddings"},
    )

    assert latency_count == 1.0
    assert throughput is not None and throughput > 0.0
    assert error_ratio == 0.0
    assert saturation is not None and 0.0 <= saturation <= 1.0
    assert cpu_percent == pytest.approx(42.0)
    assert memory_percent == pytest.approx(55.0)
    assert cache_hits == pytest.approx(0.91)
    assert evictions == 2.0

    # Trigger a latency SLA breach to ensure degradations fire and incidents are created.
    clock.advance(1.0)
    with orchestrator.trace_inference("req-2"):
        clock.advance(0.2)

    degradations = orchestrator.latest_degradations
    assert degradations, "expected at least one degradation event"
    latency_event = degradations[-1]
    assert latency_event.metric == "latency"
    assert latency_event.incident is not None
    assert latency_event.incident.summary_path.exists()
    assert latency_event.severity == pytest.approx(1.5, rel=1e-6)


def test_quality_interval_and_degradation(
    metrics_registry: CollectorRegistry, tmp_path
) -> None:
    clock = FakeClock()
    config = ModelObservabilityConfig(
        model_name="beta",
        environment="prod",
        incident_root=tmp_path,
        degradation_cooldown_seconds=0.0,
    )
    orchestrator = ModelObservabilityOrchestrator(
        config,
        perf_counter=clock.perf_counter,
        monotonic=clock.monotonic,
        now=clock.now,
    )
    orchestrator.configure_quality_baseline(
        "accuracy", target=0.9, tolerance=0.02, min_samples=5
    )

    values = [0.91, 0.9, 0.86, 0.84, 0.83]
    interval = None
    for value in values:
        clock.advance(0.5)
        interval = orchestrator.record_quality_metric("accuracy", value)

    assert interval is not None
    assert interval.sample_size == len(values)
    assert interval.mean == pytest.approx(sum(values) / len(values))

    metric_labels = {
        "model_name": "beta",
        "deployment": "prod",
        "metric": "accuracy",
        "confidence": f"{config.confidence_level:.2f}",
    }
    mean_gauge = _sample(
        metrics_registry,
        "tradepulse_model_quality_interval_mean",
        metric_labels,
    )
    assert mean_gauge == pytest.approx(interval.mean)

    degradation_events = [
        event
        for event in orchestrator.latest_degradations
        if event.metric == "accuracy"
    ]
    assert degradation_events, "quality baseline breach should emit degradation"
    assert degradation_events[-1].incident is not None
    assert degradation_events[-1].severity == pytest.approx(0.6, rel=1e-6)


def test_error_rate_degradation_severity_handles_zero_threshold(
    metrics_registry: CollectorRegistry, tmp_path
) -> None:
    clock = FakeClock()
    config = ModelObservabilityConfig(
        model_name="delta",
        environment="prod",
        incident_root=tmp_path,
        degradation_cooldown_seconds=0.0,
        error_rate_threshold=0.0,
    )
    orchestrator = ModelObservabilityOrchestrator(
        config,
        perf_counter=clock.perf_counter,
        monotonic=clock.monotonic,
        now=clock.now,
    )

    with pytest.raises(RuntimeError):
        with orchestrator.trace_inference("req-error"):
            clock.advance(0.05)
            raise RuntimeError("boom")

    degradation_events = [
        event
        for event in orchestrator.latest_degradations
        if event.metric == "error_rate"
    ]
    assert degradation_events, "error threshold breach should emit degradation"
    assert degradation_events[-1].severity == pytest.approx(1.0, rel=1e-6)


def test_correlation_metrics(metrics_registry: CollectorRegistry, tmp_path) -> None:
    clock = FakeClock()
    config = ModelObservabilityConfig(
        model_name="gamma",
        environment="prod",
        incident_root=tmp_path,
    )
    orchestrator = ModelObservabilityOrchestrator(
        config,
        perf_counter=clock.perf_counter,
        monotonic=clock.monotonic,
        now=clock.now,
    )

    for idx in range(1, 8):
        snapshot = ResourceSnapshot(
            cpu_percent=10.0 * idx,
            memory_percent=40.0 + idx,
            memory_bytes=5e8 + idx * 1e7,
        )
        orchestrator.update_resource_usage(snapshot=snapshot)
        orchestrator.record_quality_metric("precision", 0.6 + 0.02 * idx)
        clock.advance(0.2)

    correlations = orchestrator.update_correlations(
        [("cpu_percent", "quality.precision")], window=5
    )
    assert ("cpu_percent", "quality.precision") in correlations
    coefficient = correlations[("cpu_percent", "quality.precision")]
    assert -1.0 <= coefficient <= 1.0

    gauge_value = _sample(
        metrics_registry,
        "tradepulse_model_metric_correlation",
        {
            "model_name": "gamma",
            "deployment": "prod",
            "metric_a": "cpu_percent",
            "metric_b": "quality.precision",
        },
    )
    assert gauge_value == pytest.approx(coefficient)


def test_postmortem_template_contains_timeline(
    metrics_registry: CollectorRegistry, tmp_path
) -> None:
    clock = FakeClock()
    config = ModelObservabilityConfig(
        model_name="delta",
        environment="prod",
        incident_root=tmp_path,
        degradation_cooldown_seconds=0.0,
    )
    orchestrator = ModelObservabilityOrchestrator(
        config,
        perf_counter=clock.perf_counter,
        monotonic=clock.monotonic,
        now=clock.now,
    )
    orchestrator.label_event("initialised", {"build": "2024.01"})
    orchestrator.configure_quality_baseline(
        "f1_score", target=0.7, tolerance=0.05, min_samples=3
    )

    for value in (0.71, 0.7, 0.5):
        clock.advance(0.3)
        orchestrator.record_quality_metric("f1_score", value)

    event = next(
        evt for evt in orchestrator.latest_degradations if evt.metric == "f1_score"
    )
    template = orchestrator.generate_postmortem_template(event)
    rendered = template.render()

    assert "Incident" in rendered
    assert "f1_score" in rendered
    assert "initialised" in rendered
    assert "confidence_interval" in template.contributing_metrics
