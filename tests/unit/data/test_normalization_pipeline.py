from __future__ import annotations

import pandas as pd

from core.data.normalization_pipeline import MarketNormalizationConfig, normalize_market_data


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
