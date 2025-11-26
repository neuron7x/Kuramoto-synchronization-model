from __future__ import annotations

from datetime import datetime, timezone

import pytest

from observability.cache_warmup import (
    CacheWarmupController,
    CacheWarmupSpec,
)

UTC = timezone.utc


def test_warmup_success_marks_cache_ready() -> None:
    def clock() -> datetime:
        return datetime(2024, 1, 1, tzinfo=UTC)

    spec = CacheWarmupSpec(
        name="feature-cache",
        warmup=lambda: [1, 2, 3],
        readiness_probe=lambda: True,
        target_hit_rate=0.75,
        description="pre-computed features",
    )
    controller = CacheWarmupController([spec], clock=clock, min_samples_for_hit_rate=1)

    result = controller.warmup("feature-cache", strategy="release")
    assert result.warmed
    assert result.rows == 3
    status = controller.status("feature-cache")
    assert status.ready
    assert status.last_error is None
    assert controller.overall_ready()
    summary = controller.summary()[0]
    assert summary["name"] == "feature-cache"
    assert summary["last_strategy"] == "release"


def test_warmup_failure_tracks_degradation() -> None:
    def clock() -> datetime:
        return datetime(2024, 1, 1, tzinfo=UTC)

    def _boom() -> None:
        raise RuntimeError("failed to hydrate cache")

    spec = CacheWarmupSpec(name="raw-cache", warmup=_boom)
    controller = CacheWarmupController([spec], clock=clock)

    result = controller.warmup("raw-cache")
    assert not result.warmed
    assert "failed" in (result.detail or "")
    status = controller.status("raw-cache")
    assert not status.ready
    assert status.last_error is not None
    report = controller.degradation_report()
    assert set(report["raw-cache"]) == {"not_ready", "warmup_failed"}


def test_cold_request_limits_enforced_until_ready() -> None:
    spec = CacheWarmupSpec(
        name="ohlcv-cache",
        warmup=lambda: [],
        readiness_probe=lambda: False,
        max_cold_requests=1,
    )
    controller = CacheWarmupController([spec])

    assert controller.allow_cold_request("ohlcv-cache") is True
    assert controller.allow_cold_request("ohlcv-cache") is False
    status = controller.status("ohlcv-cache")
    assert status.stats.cold_allowed == 1
    assert status.stats.cold_blocked == 1
    report = controller.degradation_report()
    assert "cold_requests_blocked" in report["ohlcv-cache"]


def test_cold_latency_percentile_and_degradation_threshold() -> None:
    spec = CacheWarmupSpec(
        name="feature-cache",
        warmup=lambda: [],
        readiness_probe=lambda: False,
        max_cold_requests=10,
        max_cold_latency_seconds=0.5,
    )
    controller = CacheWarmupController([spec])

    latencies = (0.1, 0.2, 0.4, 0.5, 0.6)
    for latency in latencies:
        assert controller.allow_cold_request("feature-cache")
        controller.record_cold_latency("feature-cache", latency)

    status = controller.status("feature-cache")
    assert status.cold_latency_p95 == pytest.approx(0.58, rel=1e-2)
    report = controller.degradation_report()
    assert "cold_latency" in report["feature-cache"]


def test_hit_rate_degradation_and_recovery() -> None:
    spec = CacheWarmupSpec(
        name="analytics-cache",
        warmup=lambda: [1],
        readiness_probe=lambda: True,
        target_hit_rate=0.75,
    )
    controller = CacheWarmupController([spec], min_samples_for_hit_rate=5)
    controller.warmup("analytics-cache")

    for _ in range(5):
        controller.record_access("analytics-cache", hit=False)

    status = controller.status("analytics-cache")
    assert pytest.approx(status.hit_rate, rel=1e-6) == 0.0
    report = controller.degradation_report()
    assert "hit_rate" in report["analytics-cache"]

    for _ in range(20):
        controller.record_access("analytics-cache", hit=True)

    status = controller.status("analytics-cache")
    assert status.hit_rate > 0.75
    report = controller.degradation_report()
    assert "hit_rate" not in report.get("analytics-cache", ())


def test_snapshot_respects_configuration_order() -> None:
    specs = (
        CacheWarmupSpec(name="a", warmup=lambda: [1], readiness_probe=lambda: True),
        CacheWarmupSpec(name="b", warmup=lambda: [1], readiness_probe=lambda: True),
    )
    controller = CacheWarmupController(specs)
    controller.warm_all()

    names = [status.spec.name for status in controller.snapshot()]
    assert names == ["a", "b"]
