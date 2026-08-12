# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd

from core.data.resampling import resample_order_book
from core.indicators.hierarchical_features import (
    FeatureBufferCache,
    HierarchicalFeatureResult,
    _shannon_entropy,
    compute_hierarchical_features,
)


def _ohlcv(freq: str) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=10, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": np.linspace(100, 101, len(index)),
            "high": np.linspace(101, 102, len(index)),
            "low": np.linspace(99, 100, len(index)),
            "close": np.linspace(100, 101, len(index)),
            "volume": np.random.default_rng(1).uniform(1, 5, size=len(index)),
        },
        index=index,
    )


def _order_book(freq: str) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=10, freq=freq, tz="UTC")
    levels = pd.DataFrame(
        {
            "bid_1": 99 + np.random.default_rng(2).uniform(0, 0.1, size=len(index)),
            "bid_2": 98 + np.random.default_rng(3).uniform(0, 0.1, size=len(index)),
            "ask_1": 101 + np.random.default_rng(4).uniform(0, 0.1, size=len(index)),
            "ask_2": 102 + np.random.default_rng(5).uniform(0, 0.1, size=len(index)),
        },
        index=index,
    )
    return resample_order_book(
        levels, freq=freq, bid_cols=["bid_1", "bid_2"], ask_cols=["ask_1", "ask_2"]
    )


def test_hierarchical_features_with_benchmarks():
    ohlcv = {"1min": _ohlcv("1min"), "5min": _ohlcv("5min")}
    book = {"1min": _order_book("1min")}
    cache = FeatureBufferCache()
    result = compute_hierarchical_features(ohlcv, book_by_tf=book, cache=cache)
    assert isinstance(result, HierarchicalFeatureResult)
    assert result.multi_tf_phase_coherence >= 0.0
    flat = {k: v for tf in result.features.values() for k, v in tf.items()}
    assert "entropy" in result.features["1min"]
    assert any(key.startswith("microprice") for key in flat)


def test_shannon_entropy_float32_precision():
    rng = np.random.default_rng(42)
    samples = rng.normal(loc=0.0, scale=1.0, size=256).astype(np.float32)
    entropy = _shannon_entropy(samples)
    assert isinstance(entropy, float)
    assert entropy >= 0.0
