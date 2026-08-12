# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pandas as pd

import numpy as np

from core.data.normalization_pipeline import (
    MarketNormalizationConfig,
    _ensure_ohlcv_columns,
    normalize_market_data,
)


def test_normalize_ticks_resamples_to_ohlcv() -> None:
    timestamps = pd.to_datetime(
        [
            "2024-02-01T09:30:00Z",
            "2024-02-01T09:30:30Z",
            "2024-02-01T09:31:00Z",
            "2024-02-01T09:33:00Z",
            "2024-02-01T09:33:00Z",  # duplicate entry should be removed
            "2024-02-01T09:34:30Z",
        ]
    )
    frame = pd.DataFrame(
        {
            "price": [100.0, 101.0, 102.0, 101.5, 101.5, 103.0],
            "volume": [5.0, 1.0, 1.5, 2.0, 2.0, 3.0],
            "symbol": "ETHUSD",
            "venue": "coinbase",
        },
        index=timestamps,
    )

    config = MarketNormalizationConfig(kind="tick", frequency="1min")
    result = normalize_market_data(frame, config=config)

    assert list(result.frame.columns) == ["open", "high", "low", "close", "volume"]
    expected_index = pd.date_range(
        "2024-02-01T09:30:00Z", "2024-02-01T09:34:00Z", freq="1min", tz="UTC"
    )
    pd.testing.assert_index_equal(result.frame.index, expected_index)

    # Missing intervals should be forward-filled for prices while volume defaults to 0.
    assert result.frame.loc["2024-02-01T09:32:00+00:00", "close"] == 102.0
    assert result.frame.loc["2024-02-01T09:32:00+00:00", "volume"] == 0.0

    metadata = result.metadata
    assert metadata.kind == "tick"
    assert metadata.frequency == "1min"
    assert metadata.duplicates_dropped == 1
    assert metadata.missing_intervals == 1
    assert metadata.filled_intervals == 1
    assert metadata.metadata["symbol"] == "ETHUSD"
    assert metadata.metadata["venue"] == "coinbase"


def test_normalize_ohlcv_interpolates_prices() -> None:
    index = pd.to_datetime(
        [
            "2024-02-01T10:00:00Z",
            "2024-02-01T10:01:00Z",
            "2024-02-01T10:03:00Z",
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [200.0, 201.0, 203.0],
            "high": [201.0, 202.0, 204.0],
            "low": [199.0, 200.5, 202.5],
            "close": [200.5, 201.5, 203.5],
            "volume": [10.0, 12.0, 14.0],
            "instrument_type": "spot",
        },
        index=index,
    )

    config = MarketNormalizationConfig(
        kind="ohlcv", frequency="1min", fill_method="interpolate"
    )
    result = normalize_market_data(frame, config=config)

    expected_index = pd.date_range(
        "2024-02-01T10:00:00Z", "2024-02-01T10:03:00Z", freq="1min", tz="UTC"
    )
    pd.testing.assert_index_equal(result.frame.index, expected_index)

    # Interpolated bar should linearly interpolate prices and reset volume to zero.
    interpolated = result.frame.loc["2024-02-01T10:02:00+00:00"]
    assert interpolated["volume"] == 0.0
    assert interpolated["close"] == 202.5

    metadata = result.metadata
    assert metadata.kind == "ohlcv"
    assert metadata.frequency == "1min"
    assert metadata.missing_intervals == 1
    assert metadata.metadata["instrument_type"] == "spot"


def test_normalize_allows_empty_when_configured() -> None:
    config = MarketNormalizationConfig(allow_empty=True)
    empty = pd.DataFrame()
    result = normalize_market_data(empty, config=config)
    assert result.frame.empty
    assert result.metadata.rows == 0


def test_ensure_ohlcv_columns_fills_volume_zero_and_prices_nan() -> None:
    """`0.0 if column == "volume" else np.nan` -- only the volume gap is zero-filled.

    A price column that is missing must be filled with NaN (an honest "no data"),
    never a fabricated 0.0. Under Eq->NotEq the fills swap: a missing OPEN would
    silently become 0.0 (a fake price) while volume routes through the NaN path.
    """
    idx = pd.date_range("2024-02-01T09:30:00Z", "2024-02-01T09:32:00Z", freq="1min", tz="UTC")
    frame = pd.DataFrame({"high": [1.0, 2.0, 3.0], "low": [0.5, 1.0, 1.5], "close": [0.8, 1.8, 2.8]}, index=idx)

    aligned = _ensure_ohlcv_columns(frame)

    assert aligned["open"].isna().all(), "a missing price column must be NaN, not a fabricated 0.0"
    assert (aligned["volume"] == 0.0).all(), "a missing volume column defaults to 0.0"


def test_tick_frame_in_non_utc_timezone_aligns_counts_to_l1() -> None:
    """`counts.tz is not None and l1.tz is not None and counts.tz != l1.tz` -> convert.

    A tick frame in a non-UTC zone forces the empty-bin counts (in the source
    zone) to be reconciled against the L1 index before they are indexed together.
    Under And->Or / NotEq->Eq the reconciliation is skipped and the mismatched
    indices misalign (KeyError or wrong empty bins). A correct UTC OHLCV result
    proves the branch fired.
    """
    ts = pd.to_datetime(
        ["2024-02-01T09:30:00", "2024-02-01T09:30:30", "2024-02-01T09:31:00",
         "2024-02-01T09:33:00", "2024-02-01T09:34:30"]
    ).tz_localize("America/New_York")
    frame = pd.DataFrame({"price": [100.0, 101.0, 102.0, 101.5, 103.0],
                          "volume": [5.0, 1.0, 1.5, 2.0, 3.0]}, index=ts)

    result = normalize_market_data(frame, config=MarketNormalizationConfig(kind="tick", frequency="1min"))

    assert str(result.frame.index.tz) == "UTC"
    assert list(result.frame.columns) == ["open", "high", "low", "close", "volume"]
    # The 09:32 bin (NY) has no ticks -> forward-filled price, zero volume, correctly aligned.
    assert result.frame["close"].notna().all()
