# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pandas.testing as tm
import pytest

try:  # pragma: no cover - optional dependency boundary
    from hypothesis import assume, event, given, seed, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.data import resampling

from .utils import property_seed, property_settings, regression_note


def _timezone_strategy() -> st.SearchStrategy[timezone | None]:
    offsets = st.integers(min_value=-11, max_value=12)
    return st.one_of(
        st.just(None), offsets.map(lambda hours: timezone(timedelta(hours=int(hours))))
    )


@st.composite
def _tick_frames(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 60) -> pd.DataFrame:
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    base = datetime(2024, 1, 1, 9, 30, 0)
    offsets = draw(
        st.lists(st.integers(min_value=-3_600, max_value=3_600), min_size=size, max_size=size)
    )
    tzinfo = draw(_timezone_strategy())
    index = [base + timedelta(seconds=offset) for offset in offsets]
    if tzinfo is not None:
        index = [dt.replace(tzinfo=tzinfo) for dt in index]

    price_values = draw(
        st.lists(
            st.floats(min_value=1e-9, max_value=1e7, allow_nan=False, allow_infinity=False),
            min_size=size,
            max_size=size,
        )
    )
    size_values = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=5e6, allow_nan=False, allow_infinity=False),
            min_size=size,
            max_size=size,
        )
    )
    frame = pd.DataFrame(
        {
            "price": np.asarray(price_values, dtype=float),
            "size": np.asarray(size_values, dtype=float),
        },
        index=pd.DatetimeIndex(index),
    )
    return frame


@st.composite
def _l1_frames(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 60) -> pd.DataFrame:
    ticks = draw(_tick_frames(min_size=min_size, max_size=max_size))
    normalised = resampling._ensure_datetime_index(ticks)
    frame = pd.DataFrame(
        {
            "mid_price": normalised["price"].values,
            "last_size": normalised["size"].values,
        },
        index=normalised.index,
    )
    return frame


_FREQS = ["1s", "5s", "15s", "30s", "1min", "5min"]


@seed(property_seed("test_resample_ticks_to_l1_matches_reference"))
@settings(**property_settings("test_resample_ticks_to_l1_matches_reference", max_examples=80))
@given(_tick_frames(min_size=1, max_size=40), st.sampled_from(_FREQS))
def test_resample_ticks_to_l1_matches_reference(ticks: pd.DataFrame, frequency: str) -> None:
    event(f"tick-count={ticks.shape[0]}")
    normalised = resampling._ensure_datetime_index(ticks)
    result = resampling.resample_ticks_to_l1(ticks, freq=frequency)
    reference = normalised[["price", "size"]].resample(frequency).last().ffill()
    reference.columns = pd.Index(["mid_price", "last_size"])

    regression_note(
        "ticks_to_l1",
        {
            "input_rows": ticks.shape[0],
            "result_rows": result.shape[0],
            "frequency": frequency,
            "tzinfo": (
                str(ticks.index.tzinfo) if isinstance(ticks.index, pd.DatetimeIndex) else None
            ),
        },
    )

    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.index.tz is not None
    assert result.index.is_monotonic_increasing
    tm.assert_frame_equal(result, reference, check_freq=False)


@seed(property_seed("test_resample_l1_to_ohlcv_preserves_volume"))
@settings(**property_settings("test_resample_l1_to_ohlcv_preserves_volume", max_examples=70))
@given(_l1_frames(min_size=2, max_size=60), st.sampled_from(_FREQS))
def test_resample_l1_to_ohlcv_preserves_volume(l1: pd.DataFrame, frequency: str) -> None:
    assume(l1.index.size > 1)
    result = resampling.resample_l1_to_ohlcv(l1, freq=frequency)
    normalised = resampling._ensure_datetime_index(l1)
    grouped = normalised.resample(frequency)
    expected = grouped["mid_price"].ohlc()
    expected["volume"] = grouped["last_size"].sum(min_count=1)
    expected = expected.dropna(how="all")

    regression_note(
        "l1_to_ohlcv",
        {
            "input_rows": l1.shape[0],
            "result_rows": result.shape[0],
            "frequency": frequency,
        },
    )

    assert result.index.tz is not None
    assert result.index.is_monotonic_increasing
    tm.assert_frame_equal(result, expected, check_freq=False)


@seed(property_seed("test_align_timeframes_ffill_consistency"))
@settings(**property_settings("test_align_timeframes_ffill_consistency", max_examples=60))
@given(_tick_frames(min_size=3, max_size=40), st.data())
def test_align_timeframes_ffill_consistency(base: pd.DataFrame, data: st.DataObject) -> None:
    normalised = resampling._ensure_datetime_index(base)
    reference = pd.DataFrame({"ref_price": normalised["price"].values}, index=normalised.index)
    frame_count = data.draw(st.integers(min_value=1, max_value=4))
    names = [f"frame_{idx}" for idx in range(frame_count)]
    frames: dict[str, pd.DataFrame] = {"reference": reference}

    for name in names:
        chosen_positions = sorted(
            data.draw(
                st.sets(
                    st.integers(min_value=0, max_value=normalised.index.size - 1),
                    min_size=1,
                    max_size=normalised.index.size,
                )
            )
        )
        index = normalised.index[chosen_positions]
        values = data.draw(
            st.lists(
                st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
                min_size=len(index),
                max_size=len(index),
            )
        )
        frame = pd.DataFrame({f"value_{name}": np.asarray(values, dtype=float)}, index=index)
        if data.draw(st.booleans()):
            frame = frame.sort_index(ascending=False)
        frames[name] = frame

    aligned = resampling.align_timeframes(frames, reference="reference")
    ref_index = resampling._ensure_datetime_index(frames["reference"]).index

    for key, frame in aligned.items():
        event(f"aligned-{key}-rows={frame.shape[0]}")
        regression_note(
            "aligned_frame",
            {
                "name": key,
                "rows": frame.shape[0],
            },
        )
        assert frame.index.equals(ref_index)
        expected = resampling._ensure_datetime_index(frames[key]).reindex(ref_index, method="pad")
        tm.assert_frame_equal(frame, expected, check_freq=False)


@seed(property_seed("test_resample_order_book_invariants"))
@settings(**property_settings("test_resample_order_book_invariants", max_examples=70))
@given(
    st.integers(min_value=1, max_value=4),
    _tick_frames(min_size=5, max_size=60),
    st.sampled_from(_FREQS),
)
def test_resample_order_book_invariants(levels: int, base: pd.DataFrame, frequency: str) -> None:
    normalised = resampling._ensure_datetime_index(base)
    prices = normalised["price"].abs() + 1.0
    spreads = np.linspace(0.01, 0.5, levels)

    bid_cols = [f"bid_{idx}" for idx in range(levels)]
    ask_cols = [f"ask_{idx}" for idx in range(levels)]

    bids = pd.DataFrame(index=normalised.index)
    asks = pd.DataFrame(index=normalised.index)

    for idx, spread in enumerate(spreads):
        bids[bid_cols[idx]] = prices - spread - idx * 0.01
        asks[ask_cols[idx]] = prices + spread + idx * 0.01

    book = pd.concat([bids, asks], axis=1)

    result = resampling.resample_order_book(
        book, freq=frequency, bid_cols=bid_cols, ask_cols=ask_cols
    )

    regression_note(
        "order_book",
        {
            "levels": levels,
            "rows": book.shape[0],
            "resampled_rows": result.shape[0],
            "frequency": frequency,
        },
    )

    assert result.index.tz is not None
    assert result.index.is_monotonic_increasing

    grouped = resampling._ensure_datetime_index(book).resample(frequency)
    expected_bids = grouped[bid_cols].mean()
    expected_asks = grouped[ask_cols].mean()
    tm.assert_frame_equal(result["bids"], expected_bids, check_freq=False)
    tm.assert_frame_equal(result["asks"], expected_asks, check_freq=False)

    best_bid = result["bids"][bid_cols[0]]
    best_ask = result["asks"][ask_cols[0]]
    microprice = result["microprice"]
    imbalance = result["imbalance"]

    micro_vals = microprice.values
    bid_vals = best_bid.values
    ask_vals = best_ask.values
    valid = (~np.isnan(micro_vals)) & (~np.isnan(bid_vals)) & (~np.isnan(ask_vals))

    assert np.all(np.isfinite(micro_vals[valid]))
    assert np.all(np.isfinite(imbalance.values))
    assert np.all(bid_vals[valid] <= ask_vals[valid] + 1e-9)
    assert np.all(micro_vals[valid] >= bid_vals[valid] - 1e-9)
    assert np.all(micro_vals[valid] <= ask_vals[valid] + 1e-9)
    assert np.all(np.abs(imbalance.values) <= 1.0 + 1e-9)
