"""Tests for thermodynamics optimization modules.

This test suite validates the caching, memory management, and performance
monitoring features of the optimized thermodynamics system.
"""

import time

import numpy as np
import pytest

from runtime.thermo_cache import ThermoCache, VectorizedOperations
from runtime.thermo_memory_manager import OptimizedTelemetryManager, TelemetryWindow
from runtime.thermo_performance import (
    Benchmark,
    PerformanceMonitor,
    get_performance_monitor,
    reset_performance_metrics,
    timed,
    timing_context,
)


class TestThermoCache:
    """Test suite for ThermoCache."""

    def test_cache_initialization(self):
        """Test cache initialization with default parameters."""
        cache = ThermoCache()
        assert cache.max_size == 1000
        assert cache.ttl_seconds == 5.0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_cache_hit(self):
        """Test cache hit for energy computation."""
        cache = ThermoCache()

        topology = ["bond1", "bond2"]
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        resource = 0.3
        entropy = 0.5

        # First access - cache miss
        result = cache.get_energy(topology, latencies, coherency, resource, entropy)
        assert result is None
        assert cache.misses == 1

        # Set value
        cache.set_energy(topology, latencies, coherency, resource, entropy, 1.234)

        # Second access - cache hit
        result = cache.get_energy(topology, latencies, coherency, resource, entropy)
        assert result == 1.234
        assert cache.hits == 1

    def test_cache_expiration(self):
        """Test cache expiration based on TTL."""
        cache = ThermoCache(ttl_seconds=0.1)

        topology = ["bond1"]
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        resource = 0.3
        entropy = 0.5

        # Set value
        cache.set_energy(topology, latencies, coherency, resource, entropy, 1.5)

        # Immediate access - should hit
        result = cache.get_energy(topology, latencies, coherency, resource, entropy)
        assert result == 1.5

        # Wait for expiration
        time.sleep(0.15)

        # Access after expiration - should miss
        result = cache.get_energy(topology, latencies, coherency, resource, entropy)
        assert result is None

    def test_cache_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = ThermoCache(max_size=2, ttl_seconds=10.0)

        # Fill cache beyond capacity
        for i in range(5):
            topology = [f"bond{i}"]
            latencies = {("A", "B"): float(i)}
            coherency = {("A", "B"): 0.8}
            cache.set_energy(topology, latencies, coherency, 0.3, 0.5, float(i))

        # Should have triggered eviction (cache size should be limited)
        assert len(cache._energy_cache) <= cache.max_size
        assert cache.evictions >= 1

    def test_cache_statistics(self):
        """Test cache statistics."""
        cache = ThermoCache()

        topology = ["bond1"]
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}

        # Generate some hits and misses
        cache.get_energy(topology, latencies, coherency, 0.3, 0.5)  # miss
        cache.set_energy(topology, latencies, coherency, 0.3, 0.5, 1.0)
        cache.get_energy(topology, latencies, coherency, 0.3, 0.5)  # hit
        cache.get_energy(topology, latencies, coherency, 0.3, 0.5)  # hit

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2.0 / 3.0
        assert stats["cache_size"] >= 1

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = ThermoCache()

        topology = ["bond1"]
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}

        cache.set_energy(topology, latencies, coherency, 0.3, 0.5, 1.0)
        assert cache.get_energy(topology, latencies, coherency, 0.3, 0.5) == 1.0

        cache.clear()
        # After clear, cache should be empty
        assert len(cache._energy_cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

        # Next access should be a miss
        assert cache.get_energy(topology, latencies, coherency, 0.3, 0.5) is None
        assert cache.misses == 1


class TestVectorizedOperations:
    """Test suite for vectorized operations."""

    def test_vectorized_coherency_mean(self):
        """Test vectorized coherency mean computation."""
        values = np.array([0.5, 0.6, 0.7, 0.8])
        result = VectorizedOperations.compute_coherency_mean_vectorized(values)
        assert abs(result - 0.65) < 1e-6

    def test_vectorized_coherency_mean_empty(self):
        """Test vectorized coherency mean with empty array."""
        values = np.array([])
        result = VectorizedOperations.compute_coherency_mean_vectorized(values)
        assert result == 0.0

    def test_anomaly_detection(self):
        """Test vectorized anomaly detection."""
        # Create signal with anomaly
        values = np.array([1.0] * 20 + [10.0] + [1.0] * 20)
        anomalies = VectorizedOperations.detect_anomalies_vectorized(
            values, window_size=10, threshold=3.0
        )

        # Should detect the spike at index 20
        assert bool(anomalies[20]) is True
        assert np.sum(anomalies) >= 1


class TestTelemetryWindow:
    """Test suite for TelemetryWindow."""

    def test_window_initialization(self):
        """Test window initialization."""
        window = TelemetryWindow(max_size=100)
        assert window.max_size == 100
        assert len(window.data) == 0
        assert len(window.compressed_archives) == 0

    def test_window_append(self):
        """Test appending records to window."""
        window = TelemetryWindow(max_size=10)

        for i in range(5):
            window.append({"id": i, "value": i * 10})

        assert len(window.data) == 5

    def test_window_compression(self):
        """Test automatic compression when window is full."""
        window = TelemetryWindow(max_size=10)

        # Fill window beyond capacity
        for i in range(15):
            window.append({"id": i, "value": i * 10})

        # Should have triggered compression
        assert len(window.compressed_archives) >= 1

    def test_get_recent(self):
        """Test getting recent records."""
        window = TelemetryWindow(max_size=100)

        for i in range(20):
            window.append({"id": i})

        recent = window.get_recent(n=5)
        assert len(recent) == 5
        assert recent[-1]["id"] == 19

    def test_decompress_archive(self):
        """Test decompressing archived data."""
        window = TelemetryWindow(max_size=10)

        # Fill window to trigger compression
        for i in range(15):
            window.append({"id": i})

        if window.compressed_archives:
            decompressed = window.decompress_archive(0)
            assert len(decompressed) > 0
            assert isinstance(decompressed[0], dict)

    def test_memory_usage(self):
        """Test memory usage reporting."""
        window = TelemetryWindow(max_size=100)

        for i in range(20):
            window.append({"id": i, "data": "x" * 100})

        usage = window.get_memory_usage()
        assert "uncompressed_bytes" in usage
        assert "compressed_bytes" in usage
        assert usage["uncompressed_records"] == 20


class TestOptimizedTelemetryManager:
    """Test suite for OptimizedTelemetryManager."""

    def test_manager_initialization(self, tmp_path):
        """Test manager initialization."""
        manager = OptimizedTelemetryManager(
            window_size=100,
            export_dir=tmp_path,
        )
        assert manager.window.max_size == 100
        assert manager.export_dir == tmp_path

    def test_record_telemetry(self):
        """Test recording telemetry events."""
        manager = OptimizedTelemetryManager()

        manager.record({"F": 1.0, "dF_dt": 0.01})
        manager.record({"F": 1.1, "dF_dt": 0.02})

        recent = manager.get_recent(10)
        assert len(recent) == 2
        assert "timestamp" in recent[0]

    def test_get_time_range(self):
        """Test getting telemetry within time range."""
        manager = OptimizedTelemetryManager()

        start_time = time.time()
        manager.record({"F": 1.0})
        time.sleep(0.01)
        manager.record({"F": 1.1})
        time.sleep(0.01)
        manager.record({"F": 1.2})
        end_time = time.time()

        records = manager.get_time_range(start_time, end_time)
        assert len(records) == 3

    def test_get_time_range_includes_archived_records(self):
        """Ensure archived telemetry is included in time range queries."""
        manager = OptimizedTelemetryManager(window_size=4)

        base_time = time.time()
        for i in range(4):
            manager.record({"F": float(i), "timestamp": base_time + i})

        assert manager.window.compressed_archives, "Expected some data to be archived"

        records = manager.get_time_range(base_time, base_time + 3)
        assert len(records) == 4
        assert {record["F"] for record in records} == {0.0, 1.0, 2.0, 3.0}

    def test_compute_statistics(self):
        """Test computing aggregated statistics."""
        manager = OptimizedTelemetryManager()

        for i in range(10):
            manager.record(
                {
                    "F": 1.0 + i * 0.1,
                    "dF_dt": 0.01,
                    "circuit_breaker_active": i > 5,
                    "topology_changes": [{"change": i}],
                }
            )

        stats = manager.compute_statistics()
        assert stats["count"] == 10
        assert "avg_F" in stats
        assert "max_F" in stats
        assert "circuit_breaker_activations" in stats

    def test_compute_statistics_includes_archived_records(self):
        """Aggregated stats should consider both uncompressed and archived data."""
        manager = OptimizedTelemetryManager(window_size=4)

        base_time = time.time()
        for i in range(4):
            manager.record(
                {
                    "F": float(i),
                    "dF_dt": 0.1 * i,
                    "timestamp": base_time + i,
                }
            )

        stats = manager.compute_statistics(force=True)

        assert stats["count"] == 4
        assert stats["max_F"] == 3.0
        assert pytest.approx(stats["avg_F"], rel=1e-9) == 1.5

    def test_get_crisis_periods(self):
        """Test identifying crisis periods."""
        manager = OptimizedTelemetryManager()

        # Normal period
        for _ in range(5):
            manager.record({"crisis_mode": "NORMAL", "F": 1.0})

        # Crisis period
        for _ in range(3):
            manager.record({"crisis_mode": "ELEVATED", "F": 1.2})

        # Back to normal
        for _ in range(2):
            manager.record({"crisis_mode": "NORMAL", "F": 1.0})

        crisis_periods = manager.get_crisis_periods()
        assert len(crisis_periods) >= 1
        assert crisis_periods[0]["severity"] in ["elevated", "critical"]

    def test_export_to_json(self, tmp_path):
        """Test exporting telemetry to JSON."""
        manager = OptimizedTelemetryManager(export_dir=tmp_path)

        for i in range(5):
            manager.record({"F": 1.0 + i * 0.1})

        filepath = manager.export_to_json()
        assert filepath.exists()
        assert filepath.suffix == ".json"

    def test_export_to_compressed_json(self, tmp_path):
        """Test exporting telemetry to compressed JSON."""
        manager = OptimizedTelemetryManager(export_dir=tmp_path)

        for i in range(5):
            manager.record({"F": 1.0 + i * 0.1})

        filepath = manager.export_to_compressed_json()
        assert filepath.exists()
        assert filepath.suffix == ".gz"


class TestPerformanceMonitor:
    """Test suite for PerformanceMonitor."""

    def setup_method(self):
        """Reset performance metrics before each test."""
        reset_performance_metrics()

    def test_monitor_singleton(self):
        """Test that monitor is a singleton."""
        monitor1 = PerformanceMonitor()
        monitor2 = PerformanceMonitor()
        assert monitor1 is monitor2

    def test_record_timing(self):
        """Test recording timing measurements."""
        monitor = get_performance_monitor()

        monitor.record_timing("test_op", 0.001)
        monitor.record_timing("test_op", 0.002)

        metrics = monitor.get_metrics("test_op")
        assert metrics["call_count"] == 2
        assert abs(metrics["avg_time_ms"] - 1.5) < 0.1

    def test_timed_decorator(self):
        """Test timed decorator."""

        @timed("test_function")
        def slow_function():
            time.sleep(0.01)
            return 42

        result = slow_function()
        assert result == 42

        monitor = get_performance_monitor()
        metrics = monitor.get_metrics("test_function")
        assert metrics["call_count"] == 1
        assert metrics["avg_time_ms"] >= 10.0

    def test_timing_context(self):
        """Test timing context manager."""
        with timing_context("test_context"):
            time.sleep(0.01)

        monitor = get_performance_monitor()
        metrics = monitor.get_metrics("test_context")
        assert metrics["call_count"] == 1
        assert metrics["avg_time_ms"] >= 10.0

    def test_performance_summary(self):
        """Test getting performance summary."""
        monitor = get_performance_monitor()

        monitor.record_timing("op1", 0.001)
        monitor.record_timing("op1", 0.002)
        monitor.record_timing("op2", 0.005)

        summary = monitor.get_summary()
        assert summary["operations"] == 2
        assert summary["total_calls"] == 3
        assert len(summary["slowest_operations"]) >= 1

    def test_monitor_disable(self):
        """Test disabling performance monitoring."""
        monitor = get_performance_monitor()
        monitor.enable()

        monitor.record_timing("enabled_op", 0.001)
        assert "enabled_op" in monitor.metrics

        monitor.disable()
        monitor.record_timing("disabled_op", 0.001)
        assert "disabled_op" not in monitor.metrics

        # Re-enable for other tests
        monitor.enable()


class TestBenchmark:
    """Test suite for Benchmark utilities."""

    def test_benchmark_function(self):
        """Test benchmarking a function."""

        def test_func(x):
            return x * 2

        results = Benchmark.benchmark_function(
            test_func,
            5,
            iterations=100,
            warmup=10,
        )

        assert results["iterations"] == 100
        assert "avg_time_ms" in results
        assert "p95_time_ms" in results
        assert "throughput_ops_per_sec" in results

    def test_compare_implementations(self):
        """Test comparing multiple implementations."""

        def impl1(n):
            return sum(range(n))

        def impl2(n):
            return n * (n - 1) // 2

        results = Benchmark.compare_implementations(
            {"loop": impl1, "formula": impl2},
            100,
            iterations=100,
        )

        assert "results" in results
        assert "fastest" in results
        assert len(results["results"]) == 2
        assert results["results"]["loop"]["speedup_vs_fastest"] >= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
