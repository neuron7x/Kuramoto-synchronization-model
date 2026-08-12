# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pandas as pd

from core.indicators.multiscale_kuramoto import analyze_simple


def test_basic():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=600, freq="1min")
    df = pd.DataFrame({"close": 100 + np.cumsum(rng.normal(0, 0.5, 600))}, index=idx)
    res = analyze_simple(df)
    assert 0 <= res.consensus_R <= 1
