# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage battery for :mod:`observability.performance_monitor`.

Every metric-recording, bottleneck-detection, percentile, regression and
anomaly path is driven with real calls and the recorded state asserted.
No time mocking is needed: window arithmetic is exercised with explicit
window bounds (a negative window pushes the cutoff into the future and
deterministically yields the "no recent data" branch).
"""

from __future__ import annotations

from observability.performance_monitor import (
    AnomalyDetector,
    PerformanceBaseline,
    PerformanceMetrics,
    PerformanceMonitor,
)


def _baseline(
    *,
    p95: float = 10.0,
    p99: float = 20.0,
    throughput: float = 100.0,
    max_cpu: float = 80.0,
    max_mem: float = 1024.0,
) -> PerformanceBaseline:
    return PerformanceBaseline(
        avg_latency_ms=5.0,
        p50_latency_ms=5.0,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        avg_throughput=throughput,
        max_cpu_percent=max_cpu,
        max_memory_mb=max_mem,
    )


class TestPerformanceMetrics:
    def test_dataclass_fields(self) -> None:
        metric = PerformanceMetrics(
            timestamp=1.0,
            latency_ms=2.0,
            throughput=3.0,
            cpu_percent=4.0,
            memory_mb=5.0,
            error_rate=0.5,
        )
        assert metric.tags == {}
        assert metric.error_rate == 0.5


class TestRecordAndBottlenecks:
    def test_record_without_baseline_skips_detection(self) -> None:
        monitor = PerformanceMonitor()
        monitor.record_metric(latency_ms=1000.0, tags={"op": "read"})
        assert len(monitor.metrics_history) == 1
        assert monitor.metrics_history[0].tags == {"op": "read"}
        # No baseline => _detect_bottleneck returns early, no bottlenecks.
        assert monitor.bottlenecks == []

    def test_record_default_tags_is_empty_dict(self) -> None:
        monitor = PerformanceMonitor()
        monitor.record_metric(latency_ms=1.0)
        assert monitor.metrics_history[0].tags == {}

    def test_latency_spike_bottleneck(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p99=20.0))
        # 100 > 20 * 1.5 => latency spike.
        monitor.record_metric(latency_ms=100.0, throughput=200.0, cpu_percent=1.0)
        types = {b["type"] for b in monitor.bottlenecks}
        assert "latency_spike" in types
        spike = next(b for b in monitor.bottlenecks if b["type"] == "latency_spike")
        assert spike["severity"] == "high"

    def test_throughput_drop_bottleneck(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(throughput=100.0))
        # 10 < 100 * 0.5 => throughput drop; latency small, cpu small.
        monitor.record_metric(latency_ms=1.0, throughput=10.0, cpu_percent=1.0)
        types = {b["type"] for b in monitor.bottlenecks}
        assert types == {"throughput_drop"}

    def test_cpu_overload_bottleneck(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(max_cpu=50.0, throughput=100.0))
        # High throughput avoids the drop branch; cpu 90 > 50 => overload.
        monitor.record_metric(latency_ms=1.0, throughput=200.0, cpu_percent=90.0)
        types = {b["type"] for b in monitor.bottlenecks}
        assert types == {"cpu_overload"}

    def test_no_bottleneck_when_within_baseline(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline())
        monitor.record_metric(latency_ms=1.0, throughput=200.0, cpu_percent=1.0)
        assert monitor.bottlenecks == []


class TestRecentAndPercentiles:
    def test_get_recent_metrics_includes_recent(self) -> None:
        monitor = PerformanceMonitor()
        monitor.record_metric(latency_ms=1.0)
        recent = monitor.get_recent_metrics(window_seconds=3600.0)
        assert len(recent) == 1

    def test_get_recent_metrics_excludes_with_negative_window(self) -> None:
        monitor = PerformanceMonitor()
        monitor.record_metric(latency_ms=1.0)
        # Negative window pushes cutoff into the future -> nothing qualifies.
        assert monitor.get_recent_metrics(window_seconds=-3600.0) == []

    def test_calculate_percentiles_empty(self) -> None:
        monitor = PerformanceMonitor()
        assert monitor.calculate_percentiles() == {}

    def test_calculate_percentiles_populated(self) -> None:
        monitor = PerformanceMonitor()
        for value in (10.0, 20.0, 30.0, 40.0, 50.0):
            monitor.record_metric(latency_ms=value)
        pct = monitor.calculate_percentiles(window_seconds=3600.0)
        assert set(pct) == {"p50", "p75", "p95", "p99", "max", "avg"}
        assert pct["max"] == 50.0
        assert pct["p50"] == 30.0


class TestRegression:
    def test_check_regression_no_baseline(self) -> None:
        assert PerformanceMonitor().check_regression() == {}

    def test_check_regression_no_recent(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline())
        # No metrics recorded => empty recent window => {}.
        assert monitor.check_regression() == {}

    def test_check_regression_flags_latency_and_throughput(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p95=10.0, throughput=100.0))
        for _ in range(5):
            monitor.record_metric(latency_ms=100.0, throughput=10.0)
        result = monitor.check_regression()
        assert result["latency_regression"] is True
        assert result["throughput_regression"] is True

    def test_check_regression_throughput_zero_branch(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p95=1000.0, throughput=100.0))
        # All throughputs zero -> avg_throughput 0 -> throughput_regression False;
        # low latency vs high baseline p95 -> latency_regression False.
        for _ in range(3):
            monitor.record_metric(latency_ms=1.0, throughput=0.0)
        result = monitor.check_regression()
        assert result["latency_regression"] is False
        assert result["throughput_regression"] is False


class TestBottleneckAccess:
    def test_get_bottlenecks_filter_and_limit(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p99=20.0, max_cpu=50.0, throughput=100.0))
        # Trigger latency_spike (high) + cpu_overload (high) each record.
        monitor.record_metric(latency_ms=100.0, throughput=200.0, cpu_percent=90.0)
        high = monitor.get_bottlenecks(severity="high")
        assert all(b["severity"] == "high" for b in high)
        assert monitor.get_bottlenecks(severity="medium") == []
        assert len(monitor.get_bottlenecks(limit=1)) == 1

    def test_get_bottlenecks_no_filter(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p99=20.0))
        monitor.record_metric(latency_ms=100.0, throughput=200.0, cpu_percent=1.0)
        assert len(monitor.get_bottlenecks()) == len(monitor.bottlenecks)


class TestSummary:
    def test_summary_no_data(self) -> None:
        summary = PerformanceMonitor().get_summary()
        assert summary["status"] == "no_data"
        assert "uptime_seconds" in summary

    def test_summary_healthy_with_throughput_and_errors(self) -> None:
        monitor = PerformanceMonitor()
        for _ in range(3):
            monitor.record_metric(latency_ms=5.0, throughput=100.0, error_rate=0.01)
        summary = monitor.get_summary()
        assert summary["status"] == "healthy"
        assert "avg_throughput" in summary
        assert "avg_error_rate" in summary
        assert summary["metrics_count"] == 3

    def test_summary_without_throughput_or_errors(self) -> None:
        monitor = PerformanceMonitor()
        # Latency-only metrics: throughput and error_rate stay zero, so the
        # optional 'avg_throughput'/'avg_error_rate' keys are omitted.
        for _ in range(3):
            monitor.record_metric(latency_ms=5.0, throughput=0.0, error_rate=0.0)
        summary = monitor.get_summary()
        assert summary["status"] == "healthy"
        assert "avg_throughput" not in summary
        assert "avg_error_rate" not in summary

    def test_summary_degraded_on_regression(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p95=10.0, throughput=100.0, p99=1000.0))
        # High latency vs baseline p95 triggers latency regression, but keep
        # bottleneck count <= 10 so status is 'degraded', not 'critical'.
        for _ in range(3):
            monitor.record_metric(latency_ms=50.0, throughput=200.0, cpu_percent=1.0)
        summary = monitor.get_summary()
        assert summary["status"] == "degraded"
        assert summary["regressions"]["latency_regression"] is True

    def test_summary_critical_on_many_bottlenecks(self) -> None:
        monitor = PerformanceMonitor(baseline=_baseline(p99=20.0))
        for _ in range(11):
            monitor.record_metric(latency_ms=100.0, throughput=200.0, cpu_percent=1.0)
        summary = monitor.get_summary()
        assert summary["status"] == "critical"
        assert summary["bottlenecks_count"] > 10


class TestAnomalyDetector:
    def test_insufficient_history_returns_false(self) -> None:
        detector = AnomalyDetector()
        assert detector.add_value(1.0) is False
        assert detector.is_anomaly(1.0) is False

    def test_zero_std_returns_false(self) -> None:
        detector = AnomalyDetector()
        for _ in range(15):
            detector.add_value(5.0)
        # All identical -> std == 0 -> not anomalous.
        assert detector.is_anomaly(5.0) is False

    def test_detects_anomaly(self) -> None:
        detector = AnomalyDetector()
        # A spread history (mean 9.5, std ~5.77) so a value near the mean is
        # NOT flagged while a far outlier is.
        for value in range(20):
            detector.add_value(float(value))
        assert detector.is_anomaly(1000.0) is True
        assert detector.is_anomaly(10.0) is False

    def test_window_trim(self) -> None:
        detector = AnomalyDetector(window_size=5)
        for value in range(10):
            detector.add_value(float(value))
        assert len(detector.history) == 5
        assert detector.history == [5.0, 6.0, 7.0, 8.0, 9.0]

    def test_get_statistics_empty(self) -> None:
        assert AnomalyDetector().get_statistics() == {}

    def test_get_statistics_populated(self) -> None:
        detector = AnomalyDetector()
        for value in (2.0, 4.0, 6.0):
            detector.add_value(value)
        stats = detector.get_statistics()
        assert stats["min"] == 2.0
        assert stats["max"] == 6.0
        assert stats["mean"] == 4.0
        assert stats["count"] == 3
