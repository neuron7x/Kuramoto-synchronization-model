"""Performance benchmarks for WML adaptive optimization."""

import pytest
import numpy as np
from core.adaptive_optimization.tacl_wml import (
    WMLConfig,
    RegimeDetector,
    WML,
    Telemetry,
)
from core.adaptive_optimization.tacl_wml.adapters.canary_probe import CanaryProbe

pytestmark = [pytest.mark.performance, pytest.mark.slow]


def test_wml_step_performance(benchmark_guard):
    """Benchmark WML step execution time."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)
    wml = WML(cfg, detector)
    probe = CanaryProbe(mode="synthetic")

    # Create telemetry
    latencies = [10.0, 12.0, 15.0, 18.0]
    t = Telemetry(latencies, 1.0, 0.1, 0.4, is_bp=5.0)

    # Benchmark the step function with baseline enforcement
    result = benchmark_guard(
        wml.step,
        "test_path",
        t,
        probe,
        baseline_key="wml.step",
        threshold=0.20,
        rounds=8,
        warmup_rounds=2,
    )

    # Verify it runs
    assert isinstance(result, bool)


def test_percentile_calculation_performance(benchmark_guard):
    """Benchmark percentile calculation for large datasets."""
    from core.adaptive_optimization.tacl_wml.metrics import percentile

    # Generate large dataset
    data = np.random.randn(10000).tolist()

    # Benchmark percentile calculation with baseline enforcement
    result = benchmark_guard(
        percentile,
        data,
        99.0,
        baseline_key="wml.percentile[10k]",
        threshold=0.20,
        rounds=8,
        warmup_rounds=2,
    )

    assert result >= 0


def test_telemetry_creation_performance(benchmark_guard):
    """Benchmark Telemetry object creation and validation."""
    latencies = [float(x) for x in np.random.randn(1000)]

    # Benchmark with baseline enforcement
    result = benchmark_guard(
        Telemetry,
        latencies,
        1.0,
        0.1,
        0.4,
        is_bp=5.0,
        baseline_key="wml.telemetry_creation[1k]",
        threshold=0.20,
        rounds=8,
        warmup_rounds=2,
    )

    assert result.p99 > 0


def test_regime_detection_performance(benchmark_guard):
    """Benchmark regime detection."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)

    latencies = [10.0, 12.0, 15.0, 18.0]
    t = Telemetry(latencies, 1.0, 0.1, 0.4, is_bp=5.0)

    # Benchmark with baseline enforcement
    result = benchmark_guard(
        detector.detect,
        t,
        baseline_key="wml.regime_detection",
        threshold=0.20,
        rounds=10,
        warmup_rounds=2,
    )

    assert result is not None
