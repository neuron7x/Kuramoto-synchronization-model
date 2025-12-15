"""Tests for compare_performance.py absolute threshold fix.

These tests verify that the absolute threshold mechanism prevents false positives
from measurement noise when comparing performance metrics.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.performance.compare_performance import (
    BenchmarkResult,
    ResourceMetric,
    _compare_benchmarks,
    _compare_resources,
)


class TestAbsoluteThreshold:
    """Test that absolute threshold prevents false positives from measurement noise."""

    def test_high_relative_but_low_absolute_passes(self) -> None:
        """A 50% regression of 1ms -> 1.5ms should pass with default 5ms threshold."""
        baseline = {
            "test::fast_op": BenchmarkResult(
                name="test::fast_op",
                display_name="fast_op",
                median=0.001,  # 1ms
                mean=0.001,
                ops=1000,
            )
        }
        current = {
            "test::fast_op": BenchmarkResult(
                name="test::fast_op",
                display_name="fast_op",
                median=0.0015,  # 1.5ms - 50% regression
                mean=0.0015,
                ops=667,
            )
        }

        results = _compare_benchmarks(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        # 50% regression but only 0.5ms absolute - should PASS
        assert results[0].status == "pass", (
            f"50% regression of 0.5ms should pass with 5ms abs threshold, "
            f"got status={results[0].status}"
        )

    def test_high_relative_and_high_absolute_fails(self) -> None:
        """A 50% regression of 20ms -> 30ms should fail."""
        baseline = {
            "test::slow_op": BenchmarkResult(
                name="test::slow_op",
                display_name="slow_op",
                median=0.020,  # 20ms
                mean=0.020,
                ops=50,
            )
        }
        current = {
            "test::slow_op": BenchmarkResult(
                name="test::slow_op",
                display_name="slow_op",
                median=0.030,  # 30ms - 50% regression
                mean=0.030,
                ops=33,
            )
        }

        results = _compare_benchmarks(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        # 50% regression with 10ms absolute - should FAIL
        assert results[0].status == "fail", (
            f"50% regression of 10ms should fail with 5ms abs threshold, "
            f"got status={results[0].status}"
        )

    def test_exactly_at_threshold_passes(self) -> None:
        """A regression exactly at the threshold boundary should pass (uses strict >)."""
        baseline = {
            "test::boundary": BenchmarkResult(
                name="test::boundary",
                display_name="boundary",
                median=0.010,  # 10ms
                mean=0.010,
                ops=100,
            )
        }
        current = {
            "test::boundary": BenchmarkResult(
                name="test::boundary",
                display_name="boundary",
                median=0.015,  # 15ms - exactly 5ms absolute delta
                mean=0.015,
                ops=67,
            )
        }

        results = _compare_benchmarks(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        # 50% regression with exactly 5ms absolute - should PASS (uses > not >=)
        assert results[0].status == "pass"

    def test_resource_seconds_uses_absolute_threshold(self) -> None:
        """Resource metrics in seconds should use absolute threshold."""
        baseline = {
            "response.time": ResourceMetric(
                name="response.time",
                category="response",
                value=0.002,  # 2ms
                unit="seconds",
                budget=1.0,
            )
        }
        current = {
            "response.time": ResourceMetric(
                name="response.time",
                category="response",
                value=0.004,  # 4ms - 100% regression
                unit="seconds",
                budget=1.0,
            )
        }

        results = _compare_resources(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        # 100% regression but only 2ms absolute - should PASS
        assert results[0].status == "pass", (
            f"100% regression of 2ms should pass with 5ms abs threshold, "
            f"got status={results[0].status}"
        )

    def test_resource_bytes_ignores_absolute_threshold(self) -> None:
        """Memory metrics (bytes) should fail on relative threshold alone."""
        baseline = {
            "memory.peak": ResourceMetric(
                name="memory.peak",
                category="memory",
                value=1024,  # 1KB
                unit="bytes",
                budget=None,
            )
        }
        current = {
            "memory.peak": ResourceMetric(
                name="memory.peak",
                category="memory",
                value=2048,  # 2KB - 100% regression
                unit="bytes",
                budget=None,
            )
        }

        results = _compare_resources(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        # 100% regression - should FAIL (bytes doesn't use abs threshold)
        assert results[0].status == "fail", (
            f"100% memory regression should fail regardless of abs threshold, "
            f"got status={results[0].status}"
        )

    def test_absolute_delta_included_in_extra(self) -> None:
        """Verify that absolute_delta is included in the extra dict."""
        baseline = {
            "test::op": BenchmarkResult(
                name="test::op",
                display_name="op",
                median=0.010,
                mean=0.010,
                ops=100,
            )
        }
        current = {
            "test::op": BenchmarkResult(
                name="test::op",
                display_name="op",
                median=0.012,
                mean=0.012,
                ops=83,
            )
        }

        results = _compare_benchmarks(
            baseline, current, threshold=0.20, abs_min_seconds=0.005
        )

        assert len(results) == 1
        assert "absolute_delta" in results[0].extra
        assert abs(results[0].extra["absolute_delta"] - 0.002) < 1e-9
