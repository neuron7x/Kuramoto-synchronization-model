# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd

from core.data.backfill import CacheKey, GapFillPlanner, LayerCache, detect_gaps
from core.data.resampling import (
    align_timeframes,
    resample_l1_to_ohlcv,
    resample_ticks_to_l1,
)


def make_index(start: str, periods: int, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")


def test_detect_gaps_handles_sparse_segments():
    expected = make_index("2024-01-01", 5, "1min")
    existing = expected.delete([1, 3])
    gaps = detect_gaps(expected, existing)
    assert [(gap.start, gap.end) for gap in gaps] == [
        (expected[1], expected[2]),
        (expected[3], expected[4]),
    ]


def test_gap_planner_combines_frames():
    cache = LayerCache()
    key = CacheKey("ohlcv", "BTCUSDT", "BINANCE", "1m")
    index = make_index("2024-01-01", 3, "1min")
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=index)
    cache.put(key, frame)
    planner = GapFillPlanner(cache)
    expected_index = make_index("2024-01-01", 5, "1min")
    plan = planner.plan(key, expected_index=expected_index)
    assert len(plan.gaps) == 1
    assert plan.gaps[0].start == expected_index[3]

    new_frame = pd.DataFrame({"close": [4.0, 5.0]}, index=expected_index[-2:])
    planner.apply(key, new_frame)
    combined = cache.get(key)
    assert combined.index.equals(expected_index)


def test_resampling_tick_to_ohlcv_roundtrip():
    tick_index = make_index("2024-01-01", 120, "10s")
    ticks = pd.DataFrame(
        {"price": np.linspace(100, 101, len(tick_index)), "size": 1}, index=tick_index
    )
    l1 = resample_ticks_to_l1(ticks, freq="1min")
    ohlcv = resample_l1_to_ohlcv(l1, freq="1min")
    assert set(ohlcv.columns) == {"open", "high", "low", "close", "volume"}
    assert len(ohlcv) == 20


def test_align_timeframes_pad_missing_values():
    ref = pd.DataFrame({"close": [1, 2]}, index=make_index("2024-01-01", 2, "1min"))
    slow = pd.DataFrame({"close": [1]}, index=make_index("2024-01-01", 1, "2min"))
    aligned = align_timeframes({"fast": ref, "slow": slow}, reference="fast")
    assert aligned["slow"].iloc[-1]["close"] == 1
