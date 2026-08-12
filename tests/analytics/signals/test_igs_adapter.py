# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.signals.irreversibility_adapter import IGSFeatureProvider


def test_provider_compute_from_frame() -> None:
    rng = np.random.default_rng(42)
    log_price = np.cumsum(rng.standard_normal(1200))
    price = 100.0 * np.exp(log_price / 100.0)
    index = pd.date_range("2024-01-01", periods=1200, freq="min")
    frame = pd.DataFrame({"close": price}, index=index)
    provider = IGSFeatureProvider({"window": 200, "n_states": 5, "min_counts": 60})
    features = provider.compute_from_frame(frame)
    assert set(["epr", "flux_index", "tra", "pe", "regime_score"]).issubset(features.columns)
    assert features.index.equals(frame.index)


def test_streaming_update_emits_after_min_counts() -> None:
    rng = np.random.default_rng(7)
    log_price = np.cumsum(0.01 + 0.5 * rng.standard_normal(800))
    price = 100.0 * np.exp(log_price / 100.0)
    index = pd.date_range("2024-01-01", periods=800, freq="min")
    provider = IGSFeatureProvider({"window": 200, "n_states": 5, "min_counts": 50})
    metric = None
    for timestamp, value in zip(index, price):
        metric = provider.streaming_update("TEST", timestamp, float(value))
    assert metric is not None
    assert metric.regime_score >= 0.0
