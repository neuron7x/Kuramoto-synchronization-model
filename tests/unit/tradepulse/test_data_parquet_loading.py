# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for Parquet loading in tradepulse.data.api module."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.tradepulse.data.api import (
    DataSourceConfig,
    load_historical_bars,
)
from src.tradepulse.data.schema import Bar, Timeframe


class TestParquetLoading:
    """Tests for Parquet file loading functionality."""

    def test_load_parquet_basic(self, tmp_path: Path) -> None:
        """Test basic Parquet loading with standard columns."""
        # Create test Parquet file
        parquet_path = tmp_path / "test_data.parquet"

        # Create test data with proper timestamp format
        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=timezone.utc),
        ]

        table = pa.table({
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000.0, 1100.0, 1200.0],
        })
        pq.write_table(table, parquet_path)

        # Load the bars
        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,  # Skip validation for test
        )

        assert len(bars) == 3
        assert all(isinstance(bar, Bar) for bar in bars)
        assert bars[0].symbol == "BTCUSDT"
        assert bars[0].open == Decimal("100.0")
        assert bars[0].close == Decimal("104.0")
        assert bars[0].volume == Decimal("1000.0")

    def test_load_parquet_with_epoch_timestamps(self, tmp_path: Path) -> None:
        """Test Parquet loading with epoch second timestamps."""
        parquet_path = tmp_path / "epoch_data.parquet"

        # Create with epoch timestamps
        base_ts = 1704067200.0  # 2024-01-01 00:00:00 UTC
        table = pa.table({
            "timestamp": [base_ts, base_ts + 60, base_ts + 120],
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000.0, 1100.0, 1200.0],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="ETHUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 3
        assert bars[0].timestamp.year == 2024

    def test_load_parquet_with_millisecond_timestamps(self, tmp_path: Path) -> None:
        """Test Parquet loading with epoch millisecond timestamps."""
        parquet_path = tmp_path / "ms_data.parquet"

        # Create with millisecond timestamps
        base_ts = 1704067200000.0  # 2024-01-01 00:00:00 UTC in ms
        table = pa.table({
            "timestamp": [base_ts, base_ts + 60000, base_ts + 120000],
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000.0, 1100.0, 1200.0],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 3
        # Should be correctly parsed to 2024
        assert bars[0].timestamp.year == 2024

    def test_load_parquet_custom_columns(self, tmp_path: Path) -> None:
        """Test Parquet loading with custom column names."""
        parquet_path = tmp_path / "custom_cols.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
        ]

        table = pa.table({
            "time": timestamps,
            "open_price": [100.0, 101.0],
            "high_price": [105.0, 106.0],
            "low_price": [99.0, 100.0],
            "close_price": [104.0, 105.0],
            "qty": [1000.0, 1100.0],
        })
        pq.write_table(table, parquet_path)

        config = DataSourceConfig(
            source_type="parquet",
            path=parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            timestamp_column="time",
            ohlcv_columns={
                "open": "open_price",
                "high": "high_price",
                "low": "low_price",
                "close": "close_price",
                "volume": "qty",
            },
        )

        bars = load_historical_bars(config, validate=False)

        assert len(bars) == 2
        assert bars[0].open == Decimal("100.0")

    def test_load_unsupported_file_extension(self, tmp_path: Path) -> None:
        """Test that unsupported file extension raises ValueError."""
        unsupported_path = tmp_path / "data.json"

        with pytest.raises(ValueError, match="Unsupported file extension"):
            load_historical_bars(
                unsupported_path,
                symbol="BTCUSDT",
                validate=False,
            )

    def test_load_parquet_missing_file(self, tmp_path: Path) -> None:
        """Test that loading a missing Parquet file raises FileNotFoundError."""
        missing_path = tmp_path / "nonexistent.parquet"

        with pytest.raises(FileNotFoundError, match="Parquet file not found"):
            load_historical_bars(
                missing_path,
                symbol="BTCUSDT",
                validate=False,
            )

    def test_load_parquet_missing_required_columns(self, tmp_path: Path) -> None:
        """Test that missing required columns raises ValueError."""
        parquet_path = tmp_path / "incomplete.parquet"

        # Missing 'close' column
        table = pa.table({
            "timestamp": [1704067200.0, 1704067260.0],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            # 'close' is missing
            "volume": [1000.0, 1100.0],
        })
        pq.write_table(table, parquet_path)

        with pytest.raises(ValueError, match="Missing required columns"):
            load_historical_bars(
                parquet_path,
                symbol="BTCUSDT",
                validate=False,
            )

    def test_load_parquet_with_symbol_column(self, tmp_path: Path) -> None:
        """Test Parquet loading with symbol column in the data."""
        parquet_path = tmp_path / "with_symbol.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
        ]

        table = pa.table({
            "timestamp": timestamps,
            "symbol": ["ETHUSDT", "ETHUSDT"],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [104.0, 105.0],
            "volume": [1000.0, 1100.0],
        })
        pq.write_table(table, parquet_path)

        # Load without specifying symbol - should use column
        bars = load_historical_bars(parquet_path, timeframe=Timeframe.M1, validate=False)

        assert len(bars) == 2
        assert bars[0].symbol == "ETHUSDT"

    def test_load_parquet_string_values(self, tmp_path: Path) -> None:
        """Test Parquet loading with string numeric values."""
        parquet_path = tmp_path / "string_values.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ]

        # Some exchanges might store prices as strings
        table = pa.table({
            "timestamp": timestamps,
            "open": ["100.50"],
            "high": ["105.75"],
            "low": ["99.25"],
            "close": ["104.00"],
            "volume": ["1000"],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 1
        assert bars[0].open == Decimal("100.50")

    def test_load_parquet_auto_detect_source_type(self, tmp_path: Path) -> None:
        """Test that .parquet extension auto-detects source type."""
        parquet_path = tmp_path / "auto_detect.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ]

        table = pa.table({
            "timestamp": timestamps,
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [104.0],
            "volume": [1000.0],
        })
        pq.write_table(table, parquet_path)

        # Pass as string path - should auto-detect parquet
        bars = load_historical_bars(
            str(parquet_path),
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 1

    def test_load_parquet_skips_invalid_rows(self, tmp_path: Path) -> None:
        """Test that invalid rows are skipped with warnings."""
        parquet_path = tmp_path / "mixed_validity.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=timezone.utc),
        ]

        table = pa.table({
            "timestamp": timestamps,
            "open": [100.0, None, 102.0],  # Middle row has None
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000.0, 1100.0, 1200.0],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        # Should have 2 valid bars, skipping the None row
        assert len(bars) == 2

    def test_load_parquet_default_volume_zero(self, tmp_path: Path) -> None:
        """Test that missing volume defaults to zero."""
        parquet_path = tmp_path / "no_volume.parquet"

        timestamps = [
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ]

        # No volume column
        table = pa.table({
            "timestamp": timestamps,
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [104.0],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            validate=False,
        )

        assert len(bars) == 1
        assert bars[0].volume == Decimal("0")


class TestParquetLoadingIntegration:
    """Integration tests for Parquet loading with the full data pipeline."""

    def test_parquet_loading_with_normalization(self, tmp_path: Path) -> None:
        """Test Parquet loading with normalization enabled."""
        parquet_path = tmp_path / "normalize_test.parquet"

        # Create out-of-order data with duplicates
        timestamps = [
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=timezone.utc),  # Out of order
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=timezone.utc),  # Duplicate
        ]

        table = pa.table({
            "timestamp": timestamps,
            "open": [102.0, 100.0, 101.0, 101.5],
            "high": [107.0, 105.0, 106.0, 106.5],
            "low": [101.0, 99.0, 100.0, 100.5],
            "close": [106.0, 104.0, 105.0, 105.5],
            "volume": [1200.0, 1000.0, 1100.0, 1150.0],
        })
        pq.write_table(table, parquet_path)

        bars = load_historical_bars(
            parquet_path,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            normalize=True,
            validate=False,
        )

        # Should be sorted and deduplicated
        assert len(bars) == 3
        # First bar should be the earliest timestamp
        assert bars[0].open == Decimal("100.0")
        # Should be sorted by timestamp
        assert bars[0].timestamp < bars[1].timestamp < bars[2].timestamp
