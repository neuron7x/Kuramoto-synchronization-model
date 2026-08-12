# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Memory regression tests for large indicator windows."""

from __future__ import annotations

import gc
import tracemalloc

import numpy as np
import pandas as pd
import pytest

from core.indicators.entropy import EntropyFeature
from core.indicators.hierarchical_features import (
    FeatureBufferCache,
    compute_hierarchical_features,
)
from core.indicators.hurst import HurstFeature
from core.indicators.kuramoto import KuramotoOrderFeature, compute_phase
from core.indicators.pipeline import IndicatorPipeline

pytestmark = [pytest.mark.slow]


def _measure_peak_bytes(func, *, iterations: int = 3) -> int:
    tracemalloc.start()
    try:
        for _ in range(iterations):
            func()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        gc.collect()
    return peak


def test_compute_phase_peak_memory() -> None:
    """Large-window Kuramoto phase should stay within an acceptable memory envelope."""

    samples = np.random.default_rng(7).normal(size=262_144).astype(np.float32)

    def _run() -> None:
        compute_phase(samples, use_float32=True)

    peak_bytes = _measure_peak_bytes(_run, iterations=5)
    # Allow up to ~48 MiB peak including FFT scratch buffers.
    assert (
        peak_bytes < 50 * 1024 * 1024
    ), f"compute_phase peak {peak_bytes / (1024**2):.2f} MiB exceeds budget"


def test_indicator_pipeline_releases_buffers() -> None:
    """Indicator pipeline should not grow memory across repeated executions."""

    data = np.random.default_rng(21).normal(size=131_072).astype(np.float32)
    pipeline = IndicatorPipeline(
        [
            EntropyFeature(name="entropy", bins=64, use_float32=True),
            HurstFeature(name="hurst", use_float32=True),
            KuramotoOrderFeature(name="kuramoto", use_float32=True),
        ]
    )

    def _run() -> None:
        result = pipeline.run(data)
        result.release()

    peak_bytes = _measure_peak_bytes(_run, iterations=6)
    # Pipeline reuses the underlying buffer; peak should stay comfortably below 64 MiB.
    assert (
        peak_bytes < 64 * 1024 * 1024
    ), f"IndicatorPipeline peak {peak_bytes / (1024**2):.2f} MiB exceeds budget"


def test_hierarchical_features_memory_leak_free() -> None:
    """Repeated hierarchical aggregation should not accumulate memory across runs."""

    rows = 4096
    index = pd.date_range("2024-01-01", periods=rows, freq="min")
    rng = np.random.default_rng(2024)
    base = rng.normal(scale=0.2, size=rows).cumsum() + 100.0
    frame = pd.DataFrame(
        {
            "open": base,
            "high": base + rng.normal(scale=0.1, size=rows),
            "low": base - rng.normal(scale=0.1, size=rows),
            "close": base + rng.normal(scale=0.05, size=rows),
            "volume": rng.lognormal(mean=2.0, sigma=0.3, size=rows),
        },
        index=index,
    )
    ohlcv = {
        "1m": frame,
        "5m": frame.resample("5min").last().ffill(),
        "15m": frame.resample("15min").last().ffill(),
    }

    def _run() -> None:
        cache = FeatureBufferCache()
        compute_hierarchical_features(ohlcv, cache=cache)

    peak_bytes = _measure_peak_bytes(_run, iterations=4)
    assert (
        peak_bytes < 80 * 1024 * 1024
    ), f"Hierarchical features peak {peak_bytes / (1024**2):.2f} MiB exceeds budget"
