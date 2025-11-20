"""Performance monitoring and optimization tools for thermodynamics system.

This module provides comprehensive performance profiling, benchmarking,
and optimization utilities for the TACL thermodynamics system.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

import numpy as np


@dataclass
class PerformanceMetrics:
    """Performance metrics for a specific operation."""

    operation_name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    times: List[float] = field(default_factory=list)

    def record(self, duration: float) -> None:
        """Record a new timing measurement."""
        self.call_count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.times.append(duration)

        # Keep only recent times to avoid memory growth
        if len(self.times) > 1000:
            self.times = self.times[-1000:]

    @property
    def avg_time(self) -> float:
        """Calculate average time."""
        return self.total_time / self.call_count if self.call_count > 0 else 0.0

    @property
    def std_time(self) -> float:
        """Calculate standard deviation of times."""
        if len(self.times) < 2:
            return 0.0
        return float(np.std(self.times))

    @property
    def p95_time(self) -> float:
        """Calculate 95th percentile time."""
        if not self.times:
            return 0.0
        return float(np.percentile(self.times, 95))

    @property
    def p99_time(self) -> float:
        """Calculate 99th percentile time."""
        if not self.times:
            return 0.0
        return float(np.percentile(self.times, 99))

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "operation": self.operation_name,
            "call_count": self.call_count,
            "total_time_ms": self.total_time * 1000,
            "avg_time_ms": self.avg_time * 1000,
            "min_time_ms": (
                self.min_time * 1000 if self.min_time != float("inf") else 0.0
            ),
            "max_time_ms": self.max_time * 1000,
            "std_time_ms": self.std_time * 1000,
            "p95_time_ms": self.p95_time * 1000,
            "p99_time_ms": self.p99_time * 1000,
        }


class PerformanceMonitor:
    """Global performance monitor for thermodynamics operations.

    This singleton class tracks performance metrics across all
    thermodynamic operations for analysis and optimization.
    """

    _instance: Optional["PerformanceMonitor"] = None

    def __new__(cls) -> "PerformanceMonitor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.metrics: Dict[str, PerformanceMetrics] = {}
        self.enabled = True
        self._initialized = True

    def record_timing(self, operation: str, duration: float) -> None:
        """Record timing for an operation."""
        if not self.enabled:
            return

        if operation not in self.metrics:
            self.metrics[operation] = PerformanceMetrics(operation_name=operation)

        self.metrics[operation].record(duration)

    def get_metrics(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get performance metrics.

        Args:
            operation: Specific operation name, or None for all operations

        Returns:
            Dictionary of performance metrics
        """
        if operation:
            if operation in self.metrics:
                return self.metrics[operation].to_dict()
            return {}

        return {name: metrics.to_dict() for name, metrics in self.metrics.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all performance metrics."""
        if not self.metrics:
            return {"operations": 0, "total_calls": 0, "total_time_ms": 0.0}

        total_calls = sum(m.call_count for m in self.metrics.values())
        total_time = sum(m.total_time for m in self.metrics.values())

        # Find slowest operations
        slowest_ops = sorted(
            [(name, m.avg_time) for name, m in self.metrics.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        # Find most called operations
        most_called_ops = sorted(
            [(name, m.call_count) for name, m in self.metrics.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        return {
            "operations": len(self.metrics),
            "total_calls": total_calls,
            "total_time_ms": total_time * 1000,
            "slowest_operations": [
                {"name": name, "avg_time_ms": time * 1000} for name, time in slowest_ops
            ],
            "most_called_operations": [
                {"name": name, "call_count": count} for name, count in most_called_ops
            ],
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.metrics.clear()

    def disable(self) -> None:
        """Disable performance monitoring."""
        self.enabled = False

    def enable(self) -> None:
        """Enable performance monitoring."""
        self.enabled = True


# Global performance monitor instance
_monitor = PerformanceMonitor()


def timed(operation_name: Optional[str] = None):
    """Decorator to time function execution.

    Args:
        operation_name: Name for the operation (defaults to function name)

    Example:
        @timed("energy_computation")
        def compute_energy():
            # ... computation ...
            pass
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                _monitor.record_timing(op_name, duration)

        return wrapper

    return decorator


@contextmanager
def timing_context(operation_name: str):
    """Context manager for timing code blocks.

    Example:
        with timing_context("complex_computation"):
            # ... code to time ...
            pass
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        _monitor.record_timing(operation_name, duration)


class PerformanceProfiler:
    """Detailed profiler for thermodynamics operations.

    This class provides cProfile-based profiling for detailed
    performance analysis.
    """

    def __init__(self) -> None:
        self.profiler: Optional[cProfile.Profile] = None
        self.is_active = False

    def start(self) -> None:
        """Start profiling."""
        if self.is_active:
            return

        self.profiler = cProfile.Profile()
        self.profiler.enable()
        self.is_active = True

    def stop(self) -> None:
        """Stop profiling."""
        if not self.is_active or self.profiler is None:
            return

        self.profiler.disable()
        self.is_active = False

    def get_stats(self, sort_by: str = "cumulative", top_n: int = 20) -> str:
        """Get profiling statistics.

        Args:
            sort_by: Sort criterion ('cumulative', 'time', 'calls')
            top_n: Number of top entries to show

        Returns:
            Formatted statistics string
        """
        if self.profiler is None:
            return "No profiling data available"

        stream = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats(sort_by)
        stats.print_stats(top_n)

        return stream.getvalue()

    def reset(self) -> None:
        """Reset profiler."""
        self.stop()
        self.profiler = None


class Benchmark:
    """Benchmark utilities for thermodynamics operations."""

    @staticmethod
    def benchmark_function(
        func: Callable,
        *args,
        iterations: int = 1000,
        warmup: int = 10,
        **kwargs,
    ) -> Dict[str, float]:
        """Benchmark a function.

        Args:
            func: Function to benchmark
            *args: Positional arguments for function
            iterations: Number of iterations to run
            warmup: Number of warmup iterations
            **kwargs: Keyword arguments for function

        Returns:
            Dictionary of benchmark results
        """
        # Warmup
        for _ in range(warmup):
            func(*args, **kwargs)

        # Benchmark
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            func(*args, **kwargs)
            duration = time.perf_counter() - start
            times.append(duration)

        times_array = np.array(times)

        return {
            "iterations": iterations,
            "total_time_ms": float(np.sum(times_array)) * 1000,
            "avg_time_ms": float(np.mean(times_array)) * 1000,
            "min_time_ms": float(np.min(times_array)) * 1000,
            "max_time_ms": float(np.max(times_array)) * 1000,
            "std_time_ms": float(np.std(times_array)) * 1000,
            "median_time_ms": float(np.median(times_array)) * 1000,
            "p95_time_ms": float(np.percentile(times_array, 95)) * 1000,
            "p99_time_ms": float(np.percentile(times_array, 99)) * 1000,
            "throughput_ops_per_sec": iterations / float(np.sum(times_array)),
        }

    @staticmethod
    def compare_implementations(
        implementations: Dict[str, Callable],
        *args,
        iterations: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Compare multiple implementations of the same operation.

        Args:
            implementations: Dictionary of name -> function
            *args: Positional arguments for functions
            iterations: Number of iterations per implementation
            **kwargs: Keyword arguments for functions

        Returns:
            Comparison results
        """
        results = {}

        for name, func in implementations.items():
            results[name] = Benchmark.benchmark_function(
                func,
                *args,
                iterations=iterations,
                **kwargs,
            )

        # Find fastest implementation
        fastest_name = min(
            results.keys(),
            key=lambda k: results[k]["avg_time_ms"],
        )
        fastest_time = results[fastest_name]["avg_time_ms"]

        # Calculate speedup relative to fastest
        for name in results:
            if name != fastest_name:
                results[name]["speedup_vs_fastest"] = (
                    results[name]["avg_time_ms"] / fastest_time
                )
            else:
                results[name]["speedup_vs_fastest"] = 1.0

        return {
            "results": results,
            "fastest": fastest_name,
            "fastest_time_ms": fastest_time,
        }


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _monitor


def reset_performance_metrics() -> None:
    """Reset all performance metrics."""
    _monitor.reset()


def get_performance_summary() -> Dict[str, Any]:
    """Get summary of performance metrics."""
    return _monitor.get_summary()
