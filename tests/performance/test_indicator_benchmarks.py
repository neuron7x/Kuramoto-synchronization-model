# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Micro-benchmarks for hot indicator paths to guard against regressions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.indicators.hierarchical_features import (
    FeatureBufferCache,
    compute_hierarchical_features,
)
from core.indicators.kuramoto import compute_phase, kuramoto_order

pytestmark = [pytest.mark.slow, pytest.mark.heavy_math]


def _build_multi_timeframe_ohlcv(rows: int = 4096) -> dict[str, pd.DataFrame]:
    base_index = pd.date_range("2024-01-01", periods=rows, freq="min")
    noise = np.random.default_rng(2025)
    base_price = 100 + noise.normal(scale=0.5, size=rows).cumsum()
    frame = pd.DataFrame(
        {
            "open": base_price,
            "high": base_price + noise.normal(scale=0.2, size=rows),
            "low": base_price - noise.normal(scale=0.2, size=rows),
            "close": base_price + noise.normal(scale=0.1, size=rows),
            "volume": noise.lognormal(mean=2.0, sigma=0.3, size=rows),
        },
        index=base_index,
    )

    return {
        "1m": frame,
        "5m": frame.resample("5min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .ffill(),
        "15m": frame.resample("15min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .ffill(),
    }


def test_compute_phase_hot_path(benchmark_guard) -> None:
    """Ensure the Hilbert transform implementation stays within latency budget."""

    samples = np.random.default_rng(1337).normal(scale=1.0, size=131_072).astype(np.float32)

    result = benchmark_guard(
        compute_phase,
        samples,
        baseline_key="kuramoto.compute_phase[128k]",
        threshold=0.12,
        rounds=10,
        warmup_rounds=2,
        use_float32=True,
    )

    phases = result  # ``benchmark.pedantic`` returns the function result from the last round.
    assert isinstance(phases, np.ndarray)
    assert phases.shape == samples.shape


def test_kuramoto_order_matrix(benchmark_guard) -> None:
    """Benchmark the vectorised Kuramoto order for batched phase matrices."""

    phases = np.random.default_rng(31415).uniform(-np.pi, np.pi, size=(4096, 12)).astype(np.float32)

    result = benchmark_guard(
        kuramoto_order,
        phases,
        baseline_key="kuramoto.order[4096x12]",
        threshold=0.10,
        rounds=12,
        warmup_rounds=2,
    )

    order = result
    assert isinstance(order, np.ndarray)
    assert order.shape == (12,)
    assert np.all(order >= 0.0)
    assert np.all(order <= 1.0)


def test_hierarchical_feature_stack(benchmark_guard) -> None:
    """Benchmark the multi-timeframe feature aggregation hot path."""

    ohlcv = _build_multi_timeframe_ohlcv(rows=2048)

    def _run():
        cache = FeatureBufferCache()
        return compute_hierarchical_features(ohlcv, cache=cache)

    result = benchmark_guard(
        _run,
        baseline_key="hierarchical.features[3x2048]",
        threshold=0.20,
        rounds=5,
        warmup_rounds=1,
    )

    features = result
    assert features.features
    assert features.multi_tf_phase_coherence >= 0.0
