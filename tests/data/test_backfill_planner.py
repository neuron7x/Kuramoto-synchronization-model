# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pandas as pd
from pandas.tseries.frequencies import to_offset

from core.data.backfill import BackfillPlan, CacheKey, Gap, GapFillPlanner, LayerCache


def test_planner_infers_frequency_from_expected_index_without_freq() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="1h")._with_freq(None)

    planner = GapFillPlanner(LayerCache())
    key = CacheKey(layer="raw", symbol="BTC-USD", venue="coinbase", timeframe="1h")

    plan = planner.plan(key, expected_index=index)

    cadence = index.inferred_freq
    assert cadence is not None

    expected_end = index[-1] + to_offset(cadence)
    assert plan == BackfillPlan(gaps=[Gap(start=index[0], end=expected_end)])
