# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import (
    GeoSyncCompositeEngine,
    MarketPhase,
)


def synthetic_df(n=1200):
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    # multi-regime
    r1 = np.cumsum(np.random.normal(0, 0.5, n // 3))
    r2 = r1[-1] + 0.03 * np.arange(n // 3) + 2 * np.sin(2 * np.pi * np.arange(n // 3) / 80.0)
    r3 = r2[-1] + np.cumsum(np.random.normal(0, 1.0, n - 2 * (n // 3)))
    price = 100 + np.concatenate([r1, r2, r3])
    vol = np.random.lognormal(10, 1, n)
    return pd.DataFrame({"close": price, "volume": vol}, index=idx)


def test_end_to_end_runs():
    df = synthetic_df(900)
    eng = GeoSyncCompositeEngine()
    sig = eng.analyze_market(df)
    assert sig.phase in MarketPhase
    assert np.isfinite(sig.kuramoto_R)
    assert np.isfinite(sig.temporal_ricci)
