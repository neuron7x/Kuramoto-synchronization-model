 # SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for parquet loading in tradepulse.data.api."""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal

import pandas as pd
import pytest

from tradepulse.data.api import DataSourceConfig, load_historical_bars
from tradepulse.data.schema import Timeframe


def _write_parquet(
    path, timestamps, *, include_volume: bool = True, tz=None, symbol: str = "BTCUSDT"
) -> None:
    idx = pd.DatetimeIndex(timestamps)
    if tz is not None:
        idx = idx.tz_localize(tz) if idx.tz is None else idx.tz_convert(tz)

    count = len(idx)
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": list(range(100, 100 + count)),
            "high": list(range(101, 101 + count)),
            "low": list(range(99, 99 + count)),
            "close": [100.5 + i for i in range(count)],
        }
    )
    if include_volume:
        df["volume"] = [10 + i for i in range(count)]
    df["symbol"] = symbol
    df["timeframe"] = "1m"
    df.to_parquet(path, index=False)


def test_parquet_roundtrip(tmp_path) -> None:
    """Bars saved to parquet can be loaded back faithfully."""
    path = tmp_path / "bars.parquet"
    timestamps = pd.date_range("2024-01-01", periods=4, freq="1min", tz="UTC")
    _write_parquet(path, timestamps)

    bars = load_historical_bars(
        DataSourceConfig(source_type="parquet", path=path), normalize=False
    )

    assert len(bars) == 4
    for idx, bar in enumerate(bars):
        assert bar.symbol == "BTCUSDT"
        assert bar.timeframe == Timeframe.M1
        assert bar.timestamp == timestamps[idx].to_pydatetime()
        assert bar.open == Decimal("100") + Decimal(idx)
        assert bar.close == Decimal("100.5") + Decimal(idx)
        assert bar.volume == Decimal("10") + Decimal(idx)


def test_parquet_missing_required_column(tmp_path) -> None:
    """Loader fails fast when required columns are absent."""
    path = tmp_path / "bars_missing.parquet"
    timestamps = pd.date_range("2024-01-01", periods=2, freq="1min", tz="UTC")
    _write_parquet(path, timestamps, include_volume=False)

    with pytest.raises(ValueError) as excinfo:
        load_historical_bars(DataSourceConfig(source_type="parquet", path=path))

    assert "volume" in str(excinfo.value)


def test_parquet_invalid_timestamp_dtype(tmp_path) -> None:
    """Non-datetime timestamp columns raise a clear error."""
    path = tmp_path / "bars_bad_ts.parquet"
    df = pd.DataFrame(
        {
            "timestamp": [1, 2, 3],
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [10, 10, 10],
            "symbol": ["BTCUSDT"] * 3,
            "timeframe": ["1m"] * 3,
        }
    )
    df.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="Timestamp column must be datetime-like"):
        load_historical_bars(DataSourceConfig(source_type="parquet", path=path))


def test_parquet_naive_timestamps_assume_utc(tmp_path) -> None:
    """Naive timestamps are treated as UTC."""
    path = tmp_path / "bars_naive.parquet"
    timestamps = [
        pd.Timestamp("2024-02-01 12:00:00"),
        pd.Timestamp("2024-02-01 12:01:00"),
    ]
    _write_parquet(path, timestamps, tz=None)

    bars = load_historical_bars(DataSourceConfig(source_type="parquet", path=path))

    assert all(bar.timestamp.tzinfo is timezone.utc for bar in bars)
    assert bars[0].timestamp == timestamps[0].replace(tzinfo=timezone.utc)


def test_parquet_timezone_normalization(tmp_path) -> None:
    """Aware timestamps are converted to UTC deterministically."""
    path = tmp_path / "bars_tz.parquet"
    timestamps = pd.date_range("2024-03-01", periods=2, freq="1min", tz="Europe/Kyiv")
    _write_parquet(path, timestamps)

    bars = load_historical_bars(DataSourceConfig(source_type="parquet", path=path))

    expected = timestamps.tz_convert("UTC")
    assert [bar.timestamp for bar in bars] == [
        ts.to_pydatetime() for ts in expected
    ]
