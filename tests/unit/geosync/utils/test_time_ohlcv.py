# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for OHLCV resampling utilities."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add src to path and import module directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

# Import directly from module file to avoid package __init__
import importlib.util

spec = importlib.util.spec_from_file_location(
    "time_utils",
    Path(__file__).parent.parent.parent.parent.parent / "src/geosync/utils/time.py",
)
time_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(time_utils)
resample_ohlcv = time_utils.resample_ohlcv


class TestResampleOHLCV:
    """Test OHLCV resampling functionality."""

    def test_resample_5min(self):
        """Test resampling 1-minute data to 5-minute bars."""
        # Create 10 minutes of 1-minute data starting at round 5-min boundary
        dates = pd.date_range("2024-01-01 09:00", periods=10, freq="1min")
        df = pd.DataFrame(
            {
                "open": np.arange(100.0, 110.0),
                "high": np.arange(101.0, 111.0),
                "low": np.arange(99.0, 109.0),
                "close": np.arange(100.5, 110.5),
                "volume": np.ones(10) * 1000,
            },
            index=dates,
        )

        result = resample_ohlcv(df, "5min")

        # Should have 2 bars
        assert len(result) == 2

        # First bar (09:00-09:05)
        assert result.iloc[0]["open"] == 100.0  # First open
        assert result.iloc[0]["high"] == 105.0  # Max high
        assert result.iloc[0]["low"] == 99.0  # Min low
        assert result.iloc[0]["close"] == 104.5  # Last close
        assert result.iloc[0]["volume"] == 5000.0  # Sum volume

        # Second bar (09:05-09:10)
        assert result.iloc[1]["open"] == 105.0
        assert result.iloc[1]["high"] == 110.0
        assert result.iloc[1]["low"] == 104.0
        assert result.iloc[1]["close"] == 109.5
        assert result.iloc[1]["volume"] == 5000.0

    def test_resample_1hour(self):
        """Test resampling 15-minute data to 1-hour bars."""
        dates = pd.date_range("2024-01-01 09:00", periods=8, freq="15min")
        df = pd.DataFrame(
            {
                "open": [100, 102, 101, 103, 105, 104, 106, 108],
                "high": [102, 104, 103, 105, 107, 106, 108, 110],
                "low": [99, 101, 100, 102, 104, 103, 105, 107],
                "close": [101, 103, 102, 104, 106, 105, 107, 109],
                "volume": [1000, 1200, 800, 1100, 1300, 900, 1000, 1400],
            },
            index=dates,
        )

        result = resample_ohlcv(df, "1h")

        # Should have 2 bars
        assert len(result) == 2

        # First hour (09:00-10:00)
        assert result.iloc[0]["open"] == 100
        assert result.iloc[0]["high"] == 105
        assert result.iloc[0]["low"] == 99
        assert result.iloc[0]["close"] == 104
        assert result.iloc[0]["volume"] == 4100

    def test_resample_custom_columns(self):
        """Test resampling with custom column names."""
        dates = pd.date_range("2024-01-01", periods=6, freq="1min")
        df = pd.DataFrame(
            {
                "Open": np.arange(100.0, 106.0),
                "High": np.arange(101.0, 107.0),
                "Low": np.arange(99.0, 105.0),
                "Close": np.arange(100.5, 106.5),
                "Volume": np.ones(6) * 500,
            },
            index=dates,
        )

        result = resample_ohlcv(
            df, "3min", price_cols=("Open", "High", "Low", "Close"), volume_col="Volume"
        )

        assert len(result) == 2
        assert result.iloc[0]["Open"] == 100.0
        assert result.iloc[0]["High"] == 103.0
        assert result.iloc[0]["Low"] == 99.0
        assert result.iloc[0]["Close"] == 102.5
        assert result.iloc[0]["Volume"] == 1500.0

    def test_resample_missing_columns(self):
        """Test resampling when some columns are missing."""
        dates = pd.date_range("2024-01-01", periods=4, freq="1min")
        df = pd.DataFrame(
            {
                "close": [100, 101, 102, 103],
                "volume": [1000, 1100, 900, 1200],
            },
            index=dates,
        )

        result = resample_ohlcv(df, "2min")

        assert len(result) == 2
        assert "close" in result.columns
        assert "volume" in result.columns
        assert result.iloc[0]["close"] == 101
        assert result.iloc[0]["volume"] == 2100

    def test_invalid_index_raises_error(self):
        """Test that non-DatetimeIndex raises ValueError."""
        df = pd.DataFrame(
            {
                "open": [100, 101, 102],
                "high": [101, 102, 103],
                "low": [99, 100, 101],
                "close": [100.5, 101.5, 102.5],
                "volume": [1000, 1100, 1200],
            }
        )

        with pytest.raises(ValueError, match="DatetimeIndex"):
            resample_ohlcv(df, "5min")

    def test_missing_ohlcv_columns_raise_error(self):
        """DataFrames without any OHLCV columns should error clearly."""

        df = pd.DataFrame(
            {
                "bid": [100, 101, 102],
                "ask": [100.5, 101.5, 102.5],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="1min"),
        )

        with pytest.raises(ValueError, match="No OHLCV columns"):
            resample_ohlcv(df, "5min")

    def test_unsorted_index_is_sorted_before_resample(self):
        """Resampling should handle out-of-order rows transparently."""

        dates = pd.date_range("2024-01-01 09:00", periods=4, freq="1min")
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "high": [101.0, 102.0, 103.0, 104.0],
                "low": [99.0, 100.0, 101.0, 102.0],
                "close": [100.5, 101.5, 102.5, 103.5],
                "volume": [1000, 1100, 1200, 1300],
            },
            index=dates,
        )
        df = df.sample(frac=1.0, random_state=42)  # deliberately shuffled

        result = resample_ohlcv(df, "2min")

        assert list(result.index) == list(pd.date_range(dates[0], dates[-1], freq="2min"))
        assert result.iloc[0]["open"] == 100.0
        assert result.iloc[0]["close"] == 101.5
        assert result.iloc[0]["volume"] == 2100

    def test_empty_result_handling(self):
        """Test handling of empty resampling results."""
        dates = pd.date_range("2024-01-01", periods=2, freq="1h")
        df = pd.DataFrame(
            {
                "open": [100, 101],
                "high": [101, 102],
                "low": [99, 100],
                "close": [100.5, 101.5],
                "volume": [1000, 1100],
            },
            index=dates,
        )

        # Resample to same frequency
        result = resample_ohlcv(df, "1h")

        assert len(result) == 2
        assert result.iloc[0]["close"] == 100.5
