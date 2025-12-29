"""Example: Using thermodynamics optimizations in TradePulse.

This example demonstrates how to integrate the new optimization modules
(caching, memory management, performance monitoring) with the existing
ThermoController for improved performance.
"""

import time
from pathlib import Path

import networkx as nx
import numpy as np

from core.utils.determinism import DEFAULT_SEED, seed_numpy
from runtime.thermo_cache import ThermoCache, VectorizedOperations
from runtime.thermo_controller import ThermoController
from runtime.thermo_memory_manager import OptimizedTelemetryManager
from runtime.thermo_performance import (
    Benchmark,
    get_performance_monitor,
    timed,
    timing_context,
)

SEED = DEFAULT_SEED


def create_sample_graph() -> nx.DiGraph:
    """Create a sample network graph for testing."""
    graph = nx.DiGraph()

    # Add nodes
    nodes = ["OrderRouter", "RiskEngine", "ExecutionGateway", "MarketData"]
    for node in nodes:
        graph.add_node(node, cpu_norm=0.15)

    # Add edges with latency and coherency
    edges = [
        (
            "OrderRouter",
            "RiskEngine",
            {"latency_norm": 0.5, "coherency": 0.85, "type": "covalent"},
        ),
        (
            "RiskEngine",
            "ExecutionGateway",
            {"latency_norm": 0.6, "coherency": 0.80, "type": "ionic"},
        ),
        (
            "ExecutionGateway",
            "MarketData",
            {"latency_norm": 0.4, "coherency": 0.90, "type": "covalent"},
        ),
        (
            "MarketData",
            "OrderRouter",
            {"latency_norm": 0.3, "coherency": 0.95, "type": "metallic"},
        ),
    ]

    for src, dst, data in edges:
        graph.add_edge(src, dst, **data)

    return graph


def example_1_basic_caching():
    """Example 1: Basic caching for energy computations."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Caching")
    print("=" * 60)

    cache = ThermoCache(max_size=100, ttl_seconds=5.0)

    # Simulate topology and metrics
    topology = ["bond1", "bond2", "bond3"]
    latencies = {("A", "B"): 0.5, ("B", "C"): 0.6}
    coherency = {("A", "B"): 0.8, ("B", "C"): 0.85}

    # First computation - cache miss
    print("\nFirst computation (cache miss)...")
    start = time.perf_counter()
    energy = cache.get_energy(topology, latencies, coherency, 0.3, 0.5)
    if energy is None:
        # Simulate expensive computation
        time.sleep(0.001)  # 1ms computation
        energy = 1.234
        cache.set_energy(topology, latencies, coherency, 0.3, 0.5, energy)
    duration1 = (time.perf_counter() - start) * 1000
    print(f"Duration: {duration1:.3f} ms")
    print(f"Energy: {energy:.4f}")

    # Second computation - cache hit
    print("\nSecond computation (cache hit)...")
    start = time.perf_counter()
    energy = cache.get_energy(topology, latencies, coherency, 0.3, 0.5)
    duration2 = (time.perf_counter() - start) * 1000
    print(f"Duration: {duration2:.3f} ms")
    print(f"Energy: {energy:.4f}")
    print(f"Speedup: {duration1 / duration2:.1f}x")

    # Cache statistics
    print("\nCache Statistics:")
    stats = cache.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


def example_2_vectorized_operations():
    """Example 2: Vectorized operations for batch processing."""
    print("\n" + "=" * 60)
    print("Example 2: Vectorized Operations")
    print("=" * 60)

    # Generate sample data
    n_samples = 100
    coherency_values = np.random.uniform(0.7, 0.95, n_samples)

    print(f"\nProcessing {n_samples} coherency values...")

    # Method 1: Standard Python
    start = time.perf_counter()
    mean_python = sum(coherency_values) / len(coherency_values)
    duration_python = (time.perf_counter() - start) * 1000

    # Method 2: Vectorized
    start = time.perf_counter()
    mean_vectorized = VectorizedOperations.compute_coherency_mean_vectorized(
        coherency_values
    )
    duration_vectorized = (time.perf_counter() - start) * 1000

    print(f"\nPython mean: {mean_python:.6f} ({duration_python:.3f} ms)")
    print(f"Vectorized mean: {mean_vectorized:.6f} ({duration_vectorized:.3f} ms)")
    print(f"Speedup: {duration_python / duration_vectorized:.1f}x")

    # Anomaly detection
    print("\nAnomaly Detection:")
    time_series = np.concatenate(
        [
            np.random.normal(1.0, 0.1, 50),
            [5.0],  # Anomaly
            np.random.normal(1.0, 0.1, 49),
        ]
    )

    anomalies = VectorizedOperations.detect_anomalies_vectorized(
        time_series, window_size=10, threshold=3.0
    )

    print(f"Time series length: {len(time_series)}")
    print(f"Anomalies detected: {np.sum(anomalies)}")
    print(f"Anomaly indices: {np.where(anomalies)[0].tolist()}")


def example_3_telemetry_management():
    """Example 3: Memory-efficient telemetry management."""
    print("\n" + "=" * 60)
    print("Example 3: Telemetry Management")
    print("=" * 60)

    manager = OptimizedTelemetryManager(
        window_size=100,
        max_archives=5,
        export_dir=Path("/tmp/thermo_telemetry"),
    )

    print("\nRecording telemetry events...")

    # Record normal operation
    for i in range(50):
        manager.record(
            {
                "F": 1.0 + i * 0.001,
                "dF_dt": 0.001,
                "crisis_mode": "NORMAL",
                "circuit_breaker_active": False,
                "topology_changes": [],
            }
        )

    # Record crisis period
    for i in range(10):
        manager.record(
            {
                "F": 1.2 + i * 0.01,
                "dF_dt": 0.02,
                "crisis_mode": "ELEVATED",
                "circuit_breaker_active": False,
                "topology_changes": [{"change": i}],
            }
        )

    # Back to normal
    for i in range(40):
        manager.record(
            {
                "F": 1.1 - i * 0.001,
                "dF_dt": -0.001,
                "crisis_mode": "NORMAL",
                "circuit_breaker_active": False,
                "topology_changes": [],
            }
        )

    # Get statistics
    print("\nTelemetry Statistics:")
    stats = manager.compute_statistics()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # Identify crisis periods
    print("\nCrisis Periods:")
    crisis_periods = manager.get_crisis_periods()
    for i, period in enumerate(crisis_periods, 1):
        print(f"  Period {i}:")
        print(f"    Duration: {period['duration']:.2f}s")
        print(f"    Max F: {period['max_F']:.4f}")
        print(f"    Severity: {period['severity']}")

    # Memory usage
    print("\nMemory Usage:")
    usage = manager.get_memory_usage()
    for key, value in usage.items():
        if isinstance(value, int):
            print(f"  {key}: {value:,}")
        else:
            print(f"  {key}: {value:.2f}")


def example_4_performance_monitoring():
    """Example 4: Performance monitoring and profiling."""
    print("\n" + "=" * 60)
    print("Example 4: Performance Monitoring")
    print("=" * 60)

    # Define sample functions
    @timed("compute_energy")
    def compute_energy():
        time.sleep(0.01)  # Simulate computation
        return 1.234

    @timed("detect_crisis")
    def detect_crisis():
        time.sleep(0.005)  # Simulate detection
        return "NORMAL"

    print("\nExecuting monitored functions...")

    # Run functions multiple times
    for _ in range(10):
        compute_energy()
        detect_crisis()

    # Get performance metrics
    monitor = get_performance_monitor()

    print("\nPerformance Metrics:")
    for operation in ["compute_energy", "detect_crisis"]:
        metrics = monitor.get_metrics(operation)
        print(f"\n  {operation}:")
        print(f"    Call count: {metrics['call_count']}")
        print(f"    Avg time: {metrics['avg_time_ms']:.2f} ms")
        print(f"    P95 time: {metrics['p95_time_ms']:.2f} ms")
        print(f"    P99 time: {metrics['p99_time_ms']:.2f} ms")

    # Get summary
    print("\nPerformance Summary:")
    summary = monitor.get_summary()
    print(f"  Total operations: {summary['operations']}")
    print(f"  Total calls: {summary['total_calls']}")
    print(f"  Total time: {summary['total_time_ms']:.2f} ms")

    print("\n  Slowest operations:")
    for op in summary["slowest_operations"][:3]:
        print(f"    {op['name']}: {op['avg_time_ms']:.2f} ms")


def example_5_benchmarking():
    """Example 5: Benchmarking implementations."""
    print("\n" + "=" * 60)
    print("Example 5: Benchmarking")
    print("=" * 60)

    # Define implementations to compare
    def compute_v1(n):
        """Original implementation."""
        result = 0.0
        for i in range(n):
            result += i**2
        return result

    def compute_v2(n):
        """Optimized implementation."""
        return sum(i**2 for i in range(n))

    def compute_v3(n):
        """Vectorized implementation."""
        return np.sum(np.arange(n) ** 2)

    print("\nBenchmarking 3 implementations...")

    results = Benchmark.compare_implementations(
        {
            "v1_loop": compute_v1,
            "v2_comprehension": compute_v2,
            "v3_vectorized": compute_v3,
        },
        1000,  # n parameter
        iterations=100,
    )

    print(f"\nFastest implementation: {results['fastest']}")
    print(f"Fastest time: {results['fastest_time_ms']:.3f} ms")

    print("\nDetailed Results:")
    for name, metrics in results["results"].items():
        print(f"\n  {name}:")
        print(f"    Avg time: {metrics['avg_time_ms']:.3f} ms")
        print(f"    Throughput: {metrics['throughput_ops_per_sec']:.0f} ops/sec")
        print(f"    Speedup vs fastest: {metrics['speedup_vs_fastest']:.2f}x")


def example_6_integrated_usage():
    """Example 6: Integrated usage with ThermoController."""
    print("\n" + "=" * 60)
    print("Example 6: Integrated Usage")
    print("=" * 60)

    print("\nCreating ThermoController with optimizations...")

    # Create graph
    graph = create_sample_graph()

    # Create controller
    controller = ThermoController(graph)

    # Add optimization modules (in real integration, this would be in __init__)
    controller.cache = ThermoCache(max_size=500, ttl_seconds=5.0)
    controller.telemetry_manager = OptimizedTelemetryManager(
        window_size=1000,
        export_dir=Path("/tmp/thermo_telemetry"),
    )

    print("\nRunning control steps with monitoring...")

    # Run control steps with timing
    for i in range(5):
        with timing_context("control_step"):
            controller.control_step()

        # Record to telemetry manager
        controller.telemetry_manager.record(
            {
                "F": controller.previous_F or 0.0,
                "dF_dt": controller.dF_dt,
                "crisis_mode": controller.controller_state,
                "circuit_breaker_active": controller.circuit_breaker_active,
            }
        )

    # Get performance metrics
    print("\nControl Step Performance:")
    monitor = get_performance_monitor()
    metrics = monitor.get_metrics("control_step")
    if metrics:
        print(f"  Call count: {metrics['call_count']}")
        print(f"  Avg time: {metrics['avg_time_ms']:.2f} ms")
        print(f"  P95 time: {metrics['p95_time_ms']:.2f} ms")

    # Get cache statistics
    print("\nCache Statistics:")
    cache_stats = controller.cache.get_stats()
    print(f"  Hit rate: {cache_stats['hit_rate']:.2%}")
    print(f"  Cache size: {cache_stats['cache_size']}")

    # Get telemetry statistics
    print("\nTelemetry Statistics:")
    telem_stats = controller.telemetry_manager.compute_statistics()
    print(f"  Record count: {telem_stats['count']}")
    print(f"  Avg F: {telem_stats['avg_F']:.4f}")


def main():
    """Run all examples."""
    seed_numpy(SEED)
    print("\n" + "=" * 60)
    print("THERMODYNAMICS OPTIMIZATION EXAMPLES")
    print("=" * 60)

    examples = [
        ("Basic Caching", example_1_basic_caching),
        ("Vectorized Operations", example_2_vectorized_operations),
        ("Telemetry Management", example_3_telemetry_management),
        ("Performance Monitoring", example_4_performance_monitoring),
        ("Benchmarking", example_5_benchmarking),
        ("Integrated Usage", example_6_integrated_usage),
    ]

    for name, func in examples:
        try:
            func()
        except Exception as e:
            print(f"\nError in {name}: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
