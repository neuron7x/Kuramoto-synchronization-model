# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for tradepulse.data.api module.

Tests for data access API functions:
- load_historical_bars
- get_historical_window
- get_latest_snapshot
- get_feature_window
- normalize_bars
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Add src to path for proper imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

# Now we can import properly
from tradepulse.data.api import (  # noqa: E402
    DataSourceConfig,
    get_feature_window,
    get_historical_window,
    get_latest_snapshot,
    load_historical_bars,
    normalize_bars,
)
from tradepulse.data.schema import Bar, FeatureVector, Timeframe  # noqa: E402


def make_bar(
    ts: datetime,
    symbol: str = "BTCUSDT",
    timeframe: Timeframe = Timeframe.M1,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
) -> Bar:
    """Helper to create test bars."""
    return Bar(
        timestamp=ts,
        symbol=symbol,
        timeframe=timeframe,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def make_bar_series(
    count: int,
    start_time: datetime,
    interval_seconds: int = 60,
    **kwargs,
) -> list[Bar]:
    """Create a series of bars with regular intervals."""
    return [
        make_bar(start_time + timedelta(seconds=i * interval_seconds), **kwargs)
        for i in range(count)
    ]


class TestNormalizeBars:
    """Tests for normalize_bars function."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty list should return empty list."""
        result = normalize_bars([])
        assert result == []

    def test_sorts_bars_by_timestamp(self) -> None:
        """Bars should be sorted by timestamp."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts + timedelta(minutes=2)),
            make_bar(ts),
            make_bar(ts + timedelta(minutes=1)),
        ]

        result = normalize_bars(bars)

        assert len(result) == 3
        assert result[0].timestamp < result[1].timestamp < result[2].timestamp

    def test_removes_duplicate_timestamps(self) -> None:
        """Duplicate timestamps should be removed (keep first)."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, close=100),
            make_bar(ts + timedelta(minutes=1), close=101),
            make_bar(ts, close=102),  # Duplicate of first
        ]

        result = normalize_bars(bars)

        assert len(result) == 2
        # First occurrence should be kept
        assert result[0].close == Decimal("100")

    def test_can_skip_sorting(self) -> None:
        """Should be able to skip sorting."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts + timedelta(minutes=1)),
            make_bar(ts),
        ]

        result = normalize_bars(bars, sort_by_time=False)

        # Should keep original order
        assert result[0].timestamp > result[1].timestamp

    def test_can_skip_deduplication(self) -> None:
        """Should be able to skip deduplication."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts),  # Duplicate
        ]

        result = normalize_bars(bars, remove_duplicates=False)

        assert len(result) == 2


class TestGetHistoricalWindow:
    """Tests for get_historical_window function."""

    def test_returns_all_bars_without_filters(self) -> None:
        """Without filters, should return all bars."""
        bars = make_bar_series(10, datetime.now(timezone.utc))

        result = get_historical_window(bars)

        assert len(result) == 10

    def test_filters_by_symbol(self) -> None:
        """Should filter bars by symbol."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, symbol="BTCUSDT"),
            make_bar(ts + timedelta(minutes=1), symbol="ETHUSDT"),
            make_bar(ts + timedelta(minutes=2), symbol="BTCUSDT"),
        ]

        result = get_historical_window(bars, symbol="BTCUSDT")

        assert len(result) == 2
        assert all(b.symbol == "BTCUSDT" for b in result)

    def test_filters_by_time_range(self) -> None:
        """Should filter bars by time range."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts + timedelta(hours=1)),
            make_bar(ts + timedelta(hours=2)),
            make_bar(ts + timedelta(hours=3)),
        ]

        start = ts + timedelta(minutes=30)
        end = ts + timedelta(hours=2, minutes=30)

        result = get_historical_window(bars, start=start, end=end)

        assert len(result) == 2  # Hours 1 and 2

    def test_filters_by_timeframe(self) -> None:
        """Should filter bars by timeframe."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, timeframe=Timeframe.M1),
            make_bar(ts + timedelta(minutes=1), timeframe=Timeframe.H1),
            make_bar(ts + timedelta(minutes=2), timeframe=Timeframe.M1),
        ]

        result = get_historical_window(bars, timeframe=Timeframe.M1)

        assert len(result) == 2
        assert all(b.timeframe == Timeframe.M1 for b in result)

    def test_returns_sorted_result(self) -> None:
        """Result should be sorted by timestamp."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts + timedelta(minutes=2)),
            make_bar(ts),
            make_bar(ts + timedelta(minutes=1)),
        ]

        result = get_historical_window(bars)

        assert result[0].timestamp < result[1].timestamp < result[2].timestamp


class TestGetLatestSnapshot:
    """Tests for get_latest_snapshot function."""

    def test_returns_none_for_empty_bars(self) -> None:
        """Empty bars should return None."""
        result = get_latest_snapshot([], "BTCUSDT")
        assert result is None

    def test_returns_none_for_unknown_symbol(self) -> None:
        """Unknown symbol should return None."""
        bars = make_bar_series(5, datetime.now(timezone.utc), symbol="ETHUSDT")

        result = get_latest_snapshot(bars, "BTCUSDT")

        assert result is None

    def test_returns_latest_bar_data(self) -> None:
        """Should return snapshot with latest bar data."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, close=100),
            make_bar(ts + timedelta(minutes=1), close=101),
            make_bar(ts + timedelta(minutes=2), close=102),
        ]

        result = get_latest_snapshot(bars, "BTCUSDT")

        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert result.last_price == Decimal("102")
        assert result.timestamp == ts + timedelta(minutes=2)

    def test_includes_last_bar_by_default(self) -> None:
        """Should include last bar by default."""
        bars = make_bar_series(5, datetime.now(timezone.utc))

        result = get_latest_snapshot(bars, "BTCUSDT")

        assert result is not None
        assert result.last_bar is not None

    def test_can_exclude_last_bar(self) -> None:
        """Should be able to exclude last bar."""
        bars = make_bar_series(5, datetime.now(timezone.utc))

        result = get_latest_snapshot(bars, "BTCUSDT", include_bar=False)

        assert result is not None
        assert result.last_bar is None


class TestGetFeatureWindow:
    """Tests for get_feature_window function."""

    def test_filters_by_symbol(self) -> None:
        """Should filter features by symbol."""
        ts = datetime.now(timezone.utc)
        features = [
            FeatureVector(timestamp=ts, symbol="BTCUSDT", features={"rsi": 50.0}),
            FeatureVector(
                timestamp=ts + timedelta(minutes=1),
                symbol="ETHUSDT",
                features={"rsi": 60.0},
            ),
        ]

        result = get_feature_window(features, symbol="BTCUSDT")

        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    def test_filters_by_time_range(self) -> None:
        """Should filter features by time range."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        features = [
            FeatureVector(timestamp=ts, symbol="BTCUSDT", features={"rsi": 50.0}),
            FeatureVector(
                timestamp=ts + timedelta(hours=1),
                symbol="BTCUSDT",
                features={"rsi": 55.0},
            ),
            FeatureVector(
                timestamp=ts + timedelta(hours=2),
                symbol="BTCUSDT",
                features={"rsi": 60.0},
            ),
        ]

        result = get_feature_window(
            features,
            start=ts + timedelta(minutes=30),
            end=ts + timedelta(hours=1, minutes=30),
        )

        assert len(result) == 1

    def test_filters_by_feature_names(self) -> None:
        """Should filter to only specified features."""
        ts = datetime.now(timezone.utc)
        features = [
            FeatureVector(
                timestamp=ts,
                symbol="BTCUSDT",
                features={"rsi": 50.0, "macd": 0.5, "momentum": 1.2},
            ),
        ]

        result = get_feature_window(features, feature_names=["rsi", "macd"])

        assert len(result) == 1
        assert "rsi" in result[0].features
        assert "macd" in result[0].features
        assert "momentum" not in result[0].features


class TestLoadHistoricalBars:
    """Tests for load_historical_bars function."""

    def test_loads_from_csv(self, tmp_path: Path) -> None:
        """Should load bars from CSV file."""
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-01 00:00:00,100,105,95,102,1000\n"
            "2024-01-01 00:01:00,102,107,100,105,1500\n"
        )

        bars = load_historical_bars(
            csv_file,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,  # Skip validation for simple test
        )

        assert len(bars) == 2
        assert bars[0].symbol == "BTCUSDT"
        assert bars[0].close == Decimal("102")

    def test_loads_from_parquet(self, tmp_path: Path) -> None:
        """Should load bars from Parquet file."""
        pd = pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")

        parquet_file = tmp_path / "test_data.parquet"
        df = pd.DataFrame(
            [
                {
                    "timestamp": "2024-01-01 00:00:00",
                    "open": 100,
                    "high": 105,
                    "low": 95,
                    "close": 102,
                    "volume": 1000,
                }
            ]
        )
        df.to_parquet(parquet_file)

        bars = load_historical_bars(
            parquet_file,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 1
        assert bars[0].symbol == "BTCUSDT"
        assert bars[0].close == Decimal("102")

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_historical_bars(tmp_path / "nonexistent.csv")

    def test_normalizes_data_by_default(self, tmp_path: Path) -> None:
        """Should normalize data by default."""
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-01 00:02:00,104,109,102,107,1200\n"
            "2024-01-01 00:00:00,100,105,95,102,1000\n"
            "2024-01-01 00:01:00,102,107,100,105,1500\n"
        )

        bars = load_historical_bars(
            csv_file,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        # Should be sorted by timestamp
        assert bars[0].timestamp < bars[1].timestamp < bars[2].timestamp

    def test_accepts_data_source_config(self, tmp_path: Path) -> None:
        """Should accept DataSourceConfig."""
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text(
            "ts,o,h,l,c,vol\n" "2024-01-01 00:00:00,100,105,95,102,1000\n"
        )

        config = DataSourceConfig(
            source_type="csv",
            path=csv_file,
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            timestamp_column="ts",
            ohlcv_columns={
                "open": "o",
                "high": "h",
                "low": "l",
                "close": "c",
                "volume": "vol",
            },
            skip_validation=True,
        )

        bars = load_historical_bars(config)

        assert len(bars) == 1
        assert bars[0].symbol == "ETHUSDT"
        assert bars[0].timeframe == Timeframe.H1
