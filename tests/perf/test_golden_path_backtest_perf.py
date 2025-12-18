"""Performance tests for golden path backtest workflow.

This module validates that the performance measurement system works correctly
and that results meet basic quality standards.
"""

import math

import pytest

# Import with fallback for CI/testing
try:
    from tradepulse.perf.golden_path import run_golden_path_bench
    from tradepulse.perf.io import format_summary, write_perf_report
    PERF_MODULE_AVAILABLE = True
except ImportError:
    PERF_MODULE_AVAILABLE = False


@pytest.mark.skipif(not PERF_MODULE_AVAILABLE, reason="Performance module not available")
def test_golden_path_bench_produces_valid_results():
    """Test that golden path benchmark produces valid, structured results."""
    # Run with minimal iterations for testing
    results = run_golden_path_bench(n_bars=100, n_iterations=5, seed=42)

    # Validate structure
    assert "env" in results
    assert "latency_ms" in results
    assert "throughput" in results
    assert "config" in results

    # Validate env
    assert "python_version" in results["env"]
    assert "os" in results["env"]
    assert "commit_hash" in results["env"]

    # Validate latency_ms
    latency = results["latency_ms"]
    assert "p50" in latency
    assert "p95" in latency
    assert "p99" in latency
    assert "mean" in latency
    assert "min" in latency
    assert "max" in latency

    # All latency values must be positive numbers
    for key, value in latency.items():
        assert isinstance(value, (int, float)), f"{key} is not a number: {value}"
        assert math.isfinite(value), f"{key} is not finite: {value}"
        assert value > 0, f"{key} is not positive: {value}"

    # Validate latency ordering
    assert latency["min"] <= latency["p50"]
    assert latency["p50"] <= latency["p95"]
    assert latency["p95"] <= latency["p99"]
    assert latency["p99"] <= latency["max"]

    # Validate throughput
    throughput = results["throughput"]
    assert "bars_per_second" in throughput
    assert throughput["bars_per_second"] > 0
    assert math.isfinite(throughput["bars_per_second"])

    # Validate config
    config = results["config"]
    assert config["n_bars"] == 100
    assert config["n_iterations"] == 5
    assert config["seed"] == 42


@pytest.mark.skipif(not PERF_MODULE_AVAILABLE, reason="Performance module not available")
def test_write_perf_report_creates_json(tmp_path):
    """Test that write_perf_report creates a valid JSON file."""
    # Run minimal benchmark
    results = run_golden_path_bench(n_bars=50, n_iterations=3, seed=42)

    # Write to temporary file
    output_path = tmp_path / "test_perf.json"
    write_perf_report(results, output_path)

    # Verify file exists
    assert output_path.exists()

    # Verify file can be read back
    import json
    with open(output_path, 'r') as f:
        loaded = json.load(f)

    # Verify structure preserved
    assert "env" in loaded
    assert "latency_ms" in loaded
    assert "throughput" in loaded
    assert loaded["latency_ms"]["p50"] == results["latency_ms"]["p50"]


@pytest.mark.skipif(not PERF_MODULE_AVAILABLE, reason="Performance module not available")
def test_format_summary_produces_readable_output():
    """Test that format_summary produces human-readable text."""
    results = run_golden_path_bench(n_bars=50, n_iterations=3, seed=42)
    summary = format_summary(results)

    # Check for expected sections
    assert "Performance Summary" in summary
    assert "Environment:" in summary
    assert "Latency (ms):" in summary
    assert "Throughput:" in summary
    assert "p50:" in summary
    assert "p95:" in summary
    assert "p99:" in summary
    assert "bars/second" in summary


@pytest.mark.skipif(not PERF_MODULE_AVAILABLE, reason="Performance module not available")
def test_golden_path_bench_is_deterministic():
    """Test that benchmark produces consistent results with same seed."""
    results1 = run_golden_path_bench(n_bars=50, n_iterations=3, seed=42)
    results2 = run_golden_path_bench(n_bars=50, n_iterations=3, seed=42)

    # Results should be similar (allowing for some timing variation)
    # Check that p50 latencies are within 50% of each other
    ratio = results1["latency_ms"]["p50"] / results2["latency_ms"]["p50"]
    assert 0.5 <= ratio <= 2.0, "Results vary too much between runs with same seed"
