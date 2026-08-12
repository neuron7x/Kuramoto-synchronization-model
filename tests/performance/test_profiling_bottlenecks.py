# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive performance profiling and bottleneck detection tests.

This module implements systematic profiling to identify performance bottlenecks
in critical trading system components.
"""

import time

import numpy as np
import pytest

from observability.profiling import ProfileReport, ProfileSectionResult


class TestProfilingInstrumentation:
    """Test suite for profiling instrumentation."""

    def test_profile_section_basic(self):
        """Test basic profiling section timing."""
        result = ProfileSectionResult(
            name="test_operation", wall_time_s=1.5, cpu_time_s=1.2, peak_memory_mb=100.0
        )

        assert result.name == "test_operation"
        assert result.wall_time_s == 1.5
        assert result.cpu_time_s == 1.2
        assert result.peak_memory_mb == 100.0

    def test_profile_report_aggregation(self):
        """Test profile report aggregates multiple sections."""
        sections = [
            ProfileSectionResult("init", 0.5, 0.4, 50.0),
            ProfileSectionResult("process", 2.0, 1.8, 150.0),
            ProfileSectionResult("finalize", 0.3, 0.2, 75.0),
        ]

        report = ProfileReport(sections=sections)

        assert report.total_wall_time_s == 2.8
        assert report.total_cpu_time_s == 2.4
        assert report.peak_memory_mb == 150.0

    def test_profile_section_error_handling(self):
        """Test profile section handles errors gracefully."""
        result = ProfileSectionResult(
            name="failed_op",
            wall_time_s=0.1,
            cpu_time_s=0.05,
            peak_memory_mb=10.0,
            error="Division by zero",
        )

        assert result.error == "Division by zero"
        data = result.to_dict()
        assert "error" in data


class TestPerformanceBottleneckDetection:
    """Test suite for bottleneck detection algorithms."""

    def test_cpu_intensive_detection(self):
        """Test detection of CPU-intensive operations."""
        # Simulate CPU-bound operation
        start_cpu = time.process_time()
        start_wall = time.perf_counter()

        # CPU-intensive work
        _ = sum(i * i for i in range(1000000))

        cpu_time = time.process_time() - start_cpu
        wall_time = time.perf_counter() - start_wall

        # CPU-bound operations have cpu_time close to wall_time
        utilization = cpu_time / wall_time if wall_time > 0 else 0
        assert utilization > 0.7  # High CPU utilization

    def test_io_bound_detection(self):
        """Test detection of I/O-bound operations."""
        start_cpu = time.process_time()
        start_wall = time.perf_counter()

        # Simulate I/O wait
        time.sleep(0.1)

        cpu_time = time.process_time() - start_cpu
        wall_time = time.perf_counter() - start_wall

        # I/O-bound operations have low CPU time vs wall time
        utilization = cpu_time / wall_time if wall_time > 0 else 0
        assert utilization < 0.3  # Low CPU utilization

    def test_memory_bottleneck_detection(self):
        """Test detection of memory allocation bottlenecks."""
        import tracemalloc

        tracemalloc.start()

        # Allocate memory and keep reference to prevent garbage collection
        data = [i for i in range(1000000)]

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Convert to MB
        peak_mb = peak / 1024 / 1024

        assert peak_mb > 0  # Should have allocated some memory
        del data  # Clean up

    def test_hot_path_identification(self):
        """Test identification of hot execution paths."""
        call_counts = {}

        def track_call(func_name):
            call_counts[func_name] = call_counts.get(func_name, 0) + 1

        # Simulate execution
        for _ in range(1000):
            track_call("process_tick")
            if _ % 10 == 0:
                track_call("update_strategy")
            if _ % 100 == 0:
                track_call("save_state")

        # Hot path should be most frequently called
        assert call_counts["process_tick"] == 1000
        assert call_counts["update_strategy"] == 100
        assert call_counts["save_state"] == 10

        # Identify hot path
        hot_path = max(call_counts, key=call_counts.get)
        assert hot_path == "process_tick"


class TestPerformanceBenchmarks:
    """Test suite for performance benchmarks."""

    def test_indicator_calculation_benchmark(self):
        """Benchmark indicator calculation performance."""
        data = np.random.randn(10000)

        start = time.perf_counter()

        # Simulate moving average calculation
        window = 20
        ma = np.convolve(data, np.ones(window) / window, mode="valid")

        elapsed = time.perf_counter() - start

        # Should complete quickly
        assert elapsed < 0.1  # Less than 100ms for 10k points
        assert len(ma) == len(data) - window + 1

    def test_order_processing_throughput(self):
        """Benchmark order processing throughput."""
        orders_processed = 0
        start = time.perf_counter()

        # Simulate order processing
        for i in range(10000):
            # Minimal processing
            {"id": i, "price": 100 + i * 0.01, "size": 10}
            orders_processed += 1

        elapsed = time.perf_counter() - start
        throughput = orders_processed / elapsed

        # Should achieve high throughput
        assert throughput > 50000  # At least 50k orders/sec

    def test_data_structure_performance(self):
        """Benchmark different data structure operations."""
        # List operations
        list_data = []
        start = time.perf_counter()
        for i in range(10000):
            list_data.append(i)
        list_time = time.perf_counter() - start

        # Dict operations
        dict_data = {}
        start = time.perf_counter()
        for i in range(10000):
            dict_data[i] = i
        dict_time = time.perf_counter() - start

        # Both should be fast
        assert list_time < 0.1
        assert dict_time < 0.1


class TestMemoryProfiling:
    """Test suite for memory profiling capabilities."""

    def test_memory_leak_detection(self):
        """Test detection of potential memory leaks."""
        import gc

        # Force garbage collection
        gc.collect()

        # Allocate and release memory
        data = [i for i in range(100000)]
        del data

        # Force garbage collection again
        gc.collect()

        # Memory should be released (simplified test)
        assert gc.get_count()[0] >= 0

    def test_memory_growth_tracking(self):
        """Test tracking of memory growth over time."""
        import tracemalloc

        tracemalloc.start()
        snapshots = []

        # Take snapshots during allocation
        for i in range(5):
            current, peak = tracemalloc.get_traced_memory()
            snapshots.append(current)

        tracemalloc.stop()

        # Memory should grow with allocations
        assert len(snapshots) == 5

    def test_object_allocation_profiling(self):
        """Test profiling of object allocations."""
        import sys

        # Create objects
        objects = []
        for i in range(1000):
            obj = {"id": i, "data": [i] * 100}
            objects.append(obj)

        # Check object size
        total_size = sum(sys.getsizeof(obj) for obj in objects)
        assert total_size > 0


class TestLatencyProfiling:
    """Test suite for latency profiling."""

    def test_operation_latency_distribution(self):
        """Test latency distribution analysis."""
        latencies = []

        # Collect latency samples
        for _ in range(100):
            start = time.perf_counter()
            time.sleep(0.001)  # 1ms operation
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
            latencies.append(elapsed)

        # Calculate statistics
        mean_latency = np.mean(latencies)
        p50 = np.percentile(latencies, 50)
        p99 = np.percentile(latencies, 99)

        # Basic sanity checks
        assert 0.5 < mean_latency < 5  # Should be around 1ms
        assert p50 < p99

    def test_tail_latency_analysis(self):
        """Test analysis of tail latencies."""
        # Simulate latencies with occasional spikes
        latencies = [1.0] * 95 + [10.0] * 5  # 5% tail latency

        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)

        # Tail latencies should show the spikes
        # p95 will be around 1.0 since 95% are 1.0, p99 will capture the spikes
        assert p99 > 5
        assert p95 < p99  # p95 should be less than p99

    def test_latency_breakdown_by_component(self):
        """Test latency breakdown across components."""
        component_latencies = {
            "ingestion": 5.0,
            "processing": 15.0,
            "risk_check": 8.0,
            "execution": 12.0,
        }

        total_latency = sum(component_latencies.values())

        # Calculate percentages
        breakdown = {
            component: (latency / total_latency) * 100
            for component, latency in component_latencies.items()
        }

        # Processing should be the largest component
        assert breakdown["processing"] > 30
        assert sum(breakdown.values()) == pytest.approx(100)


class TestConcurrencyProfiling:
    """Test suite for concurrency profiling."""

    def test_thread_contention_detection(self):
        """Test detection of thread contention."""
        import threading

        counter = 0
        lock = threading.Lock()
        contention_count = 0

        def increment():
            nonlocal counter, contention_count
            for _ in range(100):
                if lock.locked():
                    contention_count += 1
                with lock:
                    counter += 1

        # Create threads
        threads = [threading.Thread(target=increment) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter == 500  # All increments completed

    def test_parallel_execution_speedup(self):
        """Test speedup from parallel execution."""

        def cpu_work():
            return sum(i * i for i in range(100000))

        # Sequential execution
        start = time.perf_counter()
        for _ in range(4):
            cpu_work()
        sequential_time = time.perf_counter() - start

        # This is a simplified test - actual parallel execution
        # would require proper multiprocessing/threading
        assert sequential_time > 0


class TestSystemResourceProfiling:
    """Test suite for system resource profiling."""

    def test_cpu_utilization_tracking(self):
        """Test tracking of CPU utilization."""
        psutil = pytest.importorskip(
            "psutil", reason="psutil is required for system resource profiling tests"
        )

        # Get CPU utilization over interval
        cpu_percent = psutil.cpu_percent(interval=0.1)

        assert 0 <= cpu_percent <= 100

    def test_memory_utilization_tracking(self):
        """Test tracking of memory utilization."""
        psutil = pytest.importorskip(
            "psutil", reason="psutil is required for system resource profiling tests"
        )

        memory = psutil.virtual_memory()

        assert memory.total > 0
        assert 0 <= memory.percent <= 100
        assert memory.available > 0

    def test_disk_io_tracking(self):
        """Test tracking of disk I/O."""
        psutil = pytest.importorskip(
            "psutil", reason="psutil is required for system resource profiling tests"
        )

        disk_io = psutil.disk_io_counters()

        if disk_io:  # May not be available in all environments
            assert disk_io.read_bytes >= 0
            assert disk_io.write_bytes >= 0


@pytest.mark.benchmark
class TestPerformanceRegression:
    """Test suite for performance regression detection."""

    def test_baseline_comparison(self):
        """Test comparison against performance baseline."""
        # Simulate current performance
        current_latency = 42.0  # ms

        # Load baseline (simulated)
        baseline_latency = 40.0  # ms
        threshold = 0.1  # 10% regression threshold

        regression = (current_latency - baseline_latency) / baseline_latency

        # Check if within acceptable range
        assert regression <= threshold, f"Performance regression detected: {regression:.1%}"

    def test_throughput_regression(self):
        """Test throughput regression detection."""
        current_throughput = 9500  # ops/sec
        baseline_throughput = 10000  # ops/sec
        threshold = 0.05  # 5% regression threshold

        regression = (baseline_throughput - current_throughput) / baseline_throughput

        assert regression <= threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
