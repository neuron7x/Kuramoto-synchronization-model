"""Critical memory profiling tests for performance regression detection.

This module provides memory profiling tests for critical performance paths
used by the performance-regression-pr.yml workflow.
"""

from __future__ import annotations

import gc
import tracemalloc
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature
from core.indicators.kuramoto import KuramotoOrderFeature
from core.indicators.pipeline import IndicatorPipeline

pytestmark = [pytest.mark.slow, pytest.mark.performance]


def measure_memory(func: Callable[[], None]) -> tuple[float, float]:
    """Measure current and peak memory usage in MiB.
    
    Args:
        func: Function to measure memory for
        
    Returns:
        Tuple of (current_memory_mib, peak_memory_mib)
    """
    gc.collect()
    tracemalloc.start()
    try:
        func()
        current, peak = tracemalloc.get_traced_memory()
        return current / (1024 ** 2), peak / (1024 ** 2)
    finally:
        tracemalloc.stop()
        gc.collect()


@pytest.mark.memory_profiler
def test_indicator_pipeline_memory() -> None:
    """Memory profiling for indicator pipeline - critical path."""
    data = np.random.default_rng(42).normal(size=100_000).astype(np.float32)
    
    pipeline = IndicatorPipeline([
        EntropyFeature(name="entropy", bins=64, use_float32=True),
        HurstFeature(name="hurst", use_float32=True),
        KuramotoOrderFeature(name="kuramoto", use_float32=True),
    ])
    
    def run_pipeline():
        result = pipeline.run(data)
        result.release()
    
    current_mem, peak_mem = measure_memory(run_pipeline)
    print(f"Line #    Mem usage    Increment   Occurrences   Line Contents")
    print(f"{'='*70}")
    print(f"    1    {current_mem:.1f} MiB    0.0 MiB           1   # Indicator pipeline execution")
    print(f"    2    {peak_mem:.1f} MiB    {peak_mem-current_mem:.1f} MiB           1   # Peak memory usage")
    
    # Assert memory stays within acceptable bounds
    assert peak_mem < 100.0, f"Peak memory {peak_mem:.1f} MiB exceeds 100 MiB threshold"


@pytest.mark.memory_profiler
def test_large_dataframe_processing_memory() -> None:
    """Memory profiling for large DataFrame operations - critical path."""
    rows = 50_000
    index = pd.date_range("2024-01-01", periods=rows, freq="1min")
    rng = np.random.default_rng(2024)
    
    def create_and_process_dataframe():
        df = pd.DataFrame({
            "open": rng.normal(100, 5, rows),
            "high": rng.normal(105, 5, rows),
            "low": rng.normal(95, 5, rows),
            "close": rng.normal(100, 5, rows),
            "volume": rng.integers(1000, 10000, rows),
        }, index=index)
        
        # Typical operations
        df["returns"] = df["close"].pct_change()
        df["sma_20"] = df["close"].rolling(20).mean()
        df["std_20"] = df["close"].rolling(20).std()
        return df
    
    current_mem, peak_mem = measure_memory(create_and_process_dataframe)
    print(f"Line #    Mem usage    Increment   Occurrences   Line Contents")
    print(f"{'='*70}")
    print(f"    1    {current_mem:.1f} MiB    0.0 MiB           1   # DataFrame processing")
    print(f"    2    {peak_mem:.1f} MiB    {peak_mem-current_mem:.1f} MiB           1   # Peak memory usage")
    
    # Assert memory stays within acceptable bounds
    assert peak_mem < 50.0, f"Peak memory {peak_mem:.1f} MiB exceeds 50 MiB threshold"


@pytest.mark.memory_profiler
def test_numpy_array_operations_memory() -> None:
    """Memory profiling for NumPy operations - critical path."""
    size = 1_000_000
    
    def numpy_operations():
        arr = np.random.default_rng(123).normal(0, 1, size).astype(np.float32)
        result = np.fft.fft(arr)
        result = np.abs(result)
        return result
    
    current_mem, peak_mem = measure_memory(numpy_operations)
    print(f"Line #    Mem usage    Increment   Occurrences   Line Contents")
    print(f"{'='*70}")
    print(f"    1    {current_mem:.1f} MiB    0.0 MiB           1   # NumPy FFT operations")
    print(f"    2    {peak_mem:.1f} MiB    {peak_mem-current_mem:.1f} MiB           1   # Peak memory usage")
    
    # Assert memory stays within acceptable bounds
    assert peak_mem < 30.0, f"Peak memory {peak_mem:.1f} MiB exceeds 30 MiB threshold"


if __name__ == "__main__":
    # Allow running with memory_profiler directly
    print("Running memory profiling tests...")
    test_indicator_pipeline_memory()
    test_large_dataframe_processing_memory()
    test_numpy_array_operations_memory()
    print("All memory profiling tests completed.")
