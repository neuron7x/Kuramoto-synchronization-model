# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration checks for resampling ticks into OHLCV bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.data.resampling import (
    align_timeframes,
    resample_l1_to_ohlcv,
    resample_ticks_to_l1,
)


def _build_ticks() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T09:30:00Z",
            "2024-01-02T09:30:30Z",
            "2024-01-02T09:31:00Z",
            "2024-01-02T09:33:30Z",
            "2024-01-02T09:34:45Z",
            "2024-01-02T09:36:00Z",
        ],
        tz="UTC",
    )
    ticks = pd.DataFrame(
        {
            "price": [100.0, 101.0, 102.0, 101.5, 103.0, 102.5],
            "size": [10.0, 5.0, 8.0, 4.0, 7.0, 6.0],
        },
        index=index,
    )
    return ticks


def test_tick_to_ohlcv_alignment() -> None:
    ticks = _build_ticks()
    l1 = resample_ticks_to_l1(ticks, freq="1min")
    bars = resample_l1_to_ohlcv(l1, freq="5min")

    expected_index = pd.date_range("2024-01-02T09:30:00Z", periods=2, freq="5min", tz="UTC")
    expected = pd.DataFrame(
        {
            "open": [101.0, 103.0],
            "high": [103.0, 103.0],
            "low": [101.0, 102.5],
            "close": [103.0, 102.5],
            "volume": [32.0, 13.0],
        },
        index=expected_index,
    )

    pd.testing.assert_index_equal(bars.index, expected.index)
    pd.testing.assert_frame_equal(bars, expected)


def test_multi_timeframe_alignment_preserves_reference_calendar() -> None:
    ticks = _build_ticks()
    l1 = resample_ticks_to_l1(ticks, freq="1min")
    bars = resample_l1_to_ohlcv(l1, freq="5min")

    frames = {
        "ticks": ticks,
        "l1": l1,
        "bars": bars,
    }
    aligned = align_timeframes(frames, reference="bars")

    ref_index = bars.index
    for name, frame in aligned.items():
        assert frame.index.equals(ref_index), name

    # Forward-filled values must agree with the latest known observation at the reference timestamps.
    assert np.isclose(aligned["l1"].loc[ref_index[-1], "mid_price"], 103.0)
    assert np.isclose(aligned["ticks"].loc[ref_index[-1], "price"], 103.0)
