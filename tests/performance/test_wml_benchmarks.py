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

pytestmark = [pytest.mark.performance]


def test_wml_step_performance(benchmark):
    """Benchmark WML step execution time."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)
    wml = WML(cfg, detector)
    probe = CanaryProbe(mode="synthetic")
    
    # Create telemetry
    latencies = [10.0, 12.0, 15.0, 18.0]
    t = Telemetry(latencies, 1.0, 0.1, 0.4, is_bp=5.0)
    
    # Benchmark the step function
    result = benchmark(wml.step, "test_path", t, probe)
    
    # Verify it runs
    assert isinstance(result, bool)


def test_percentile_calculation_performance(benchmark):
    """Benchmark percentile calculation for large datasets."""
    from core.adaptive_optimization.tacl_wml.metrics import percentile
    
    # Generate large dataset
    data = np.random.randn(10000).tolist()
    
    # Benchmark percentile calculation
    result = benchmark(percentile, data, 99.0)
    
    assert 0 <= result


def test_telemetry_creation_performance(benchmark):
    """Benchmark Telemetry object creation and validation."""
    latencies = np.random.randn(1000).tolist()
    
    result = benchmark(
        Telemetry,
        latencies,
        1.0,
        0.1,
        0.4,
        is_bp=5.0
    )
    
    assert result.p99 > 0


def test_regime_detection_performance(benchmark):
    """Benchmark regime detection."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)
    
    latencies = [10.0, 12.0, 15.0, 18.0]
    t = Telemetry(latencies, 1.0, 0.1, 0.4, is_bp=5.0)
    
    result = benchmark(detector.detect, t)
    
    assert result is not None
