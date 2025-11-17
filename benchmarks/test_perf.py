"""Basic performance benchmark tests.

This module provides foundational benchmark tests to ensure the CI
performance regression detection system works correctly.
"""


def work(n=10000):
    """Simple computation workload for benchmarking.

    Args:
        n: Number of iterations

    Returns:
        Sum of squares from 0 to n-1
    """
    s = 0
    for i in range(n):
        s += i * i
    return s


def test_work(benchmark):
    """Benchmark the work function.

    This test ensures pytest-benchmark is properly configured
    and provides a baseline benchmark for CI testing.
    """
    result = benchmark(work, 10000)
    assert result is not None
    assert result > 0  # Sum of squares should be positive
