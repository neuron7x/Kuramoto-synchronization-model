"""Tests for OHLCV data generation and validation utilities.

This module tests the scripts/generate_sample_ohlcv.py module and validates
that generated data meets quality requirements for trading analysis.
"""

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.generate_sample_ohlcv import (
    generate_market_data,
    generate_multi_asset_data,
    generate_ohlcv_from_ticks,
    generate_price_series,
    write_ohlcv_csv,
)


class TestGeneratePriceSeries:
    """Tests for price series generation."""

    def test_basic_generation(self):
        """Test basic price series generation."""
        prices = generate_price_series(100, base_price=100.0, seed=42)
        assert len(prices) == 100
        assert prices[0] > 0
        assert not np.isnan(prices).any()

    def test_reproducibility_with_seed(self):
        """Test that same seed produces same results."""
        prices1 = generate_price_series(100, seed=42)
        prices2 = generate_price_series(100, seed=42)
        np.testing.assert_array_equal(prices1, prices2)

    def test_different_seeds_produce_different_results(self):
        """Test that different seeds produce different results."""
        prices1 = generate_price_series(100, seed=42)
        prices2 = generate_price_series(100, seed=43)
        assert not np.allclose(prices1, prices2)

    def test_volatility_affects_variance(self):
        """Test that higher volatility produces more variance."""
        prices_low = generate_price_series(1000, volatility=0.01, seed=42)
        prices_high = generate_price_series(1000, volatility=0.05, seed=42)

        returns_low = np.diff(np.log(prices_low))
        returns_high = np.diff(np.log(prices_high))

        assert returns_high.std() > returns_low.std()

    def test_base_price_affects_level(self):
        """Test that base_price affects the price level."""
        prices_100 = generate_price_series(100, base_price=100.0, seed=42)
        prices_1000 = generate_price_series(100, base_price=1000.0, seed=42)

        # First prices should be proportional to base_price
        assert prices_1000.mean() > prices_100.mean() * 5


class TestGenerateOHLCVFromTicks:
    """Tests for OHLCV generation from close prices."""

    def test_basic_ohlcv_generation(self):
        """Test basic OHLCV generation."""
        close_prices = np.array([100.0, 101.0, 102.0, 101.5, 103.0])
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert len(ohlcv) == 5
        assert set(ohlcv.columns) == {"open", "high", "low", "close", "volume"}

    def test_high_gte_low(self):
        """Test that high is always >= low."""
        close_prices = generate_price_series(1000, seed=42)
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert (ohlcv["high"] >= ohlcv["low"]).all()

    def test_high_gte_open_close(self):
        """Test that high is >= open and close."""
        close_prices = generate_price_series(1000, seed=42)
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert (ohlcv["high"] >= ohlcv["open"]).all()
        assert (ohlcv["high"] >= ohlcv["close"]).all()

    def test_low_lte_open_close(self):
        """Test that low is <= open and close."""
        close_prices = generate_price_series(1000, seed=42)
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert (ohlcv["low"] <= ohlcv["open"]).all()
        assert (ohlcv["low"] <= ohlcv["close"]).all()

    def test_volume_positive(self):
        """Test that volume is always positive."""
        close_prices = generate_price_series(100, seed=42)
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert (ohlcv["volume"] > 0).all()

    def test_no_nan_values(self):
        """Test that no NaN values are produced."""
        close_prices = generate_price_series(100, seed=42)
        ohlcv = generate_ohlcv_from_ticks(close_prices, seed=42)

        assert not ohlcv.isna().any().any()


class TestGenerateMarketData:
    """Tests for complete market data generation."""

    def test_basic_market_data_generation(self):
        """Test basic market data generation."""
        df = generate_market_data(symbol="TEST", days=1, timeframe="1h", seed=42)

        assert "timestamp" in df.columns
        assert "symbol" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns

    def test_correct_number_of_bars(self):
        """Test that correct number of bars are generated."""
        # 1 day with 1h bars = 24 bars
        df = generate_market_data(days=1, timeframe="1h", seed=42)
        assert len(df) == 24

        # 2 days with 4h bars = 12 bars
        df = generate_market_data(days=2, timeframe="4h", seed=42)
        assert len(df) == 12

        # 3 days with 1d bars = 3 bars
        df = generate_market_data(days=3, timeframe="1d", seed=42)
        assert len(df) == 3

    def test_symbol_column(self):
        """Test that symbol column is correctly set."""
        df = generate_market_data(symbol="BTC", days=1, seed=42)
        assert (df["symbol"] == "BTC").all()

    def test_timestamps_are_sequential(self):
        """Test that timestamps are sequential."""
        df = generate_market_data(days=1, timeframe="1h", seed=42)
        timestamps = pd.to_datetime(df["timestamp"])
        diffs = timestamps.diff().dropna()

        # All differences should be 1 hour
        assert (diffs == pd.Timedelta(hours=1)).all()

    def test_start_date_parameter(self):
        """Test that start_date parameter works correctly."""
        df = generate_market_data(days=1, start_date="2023-06-15", seed=42)
        first_ts = pd.to_datetime(df["timestamp"].iloc[0])
        assert first_ts.date().isoformat() == "2023-06-15"


class TestGenerateMultiAssetData:
    """Tests for multi-asset data generation."""

    def test_multi_asset_generation(self):
        """Test multi-asset data generation."""
        df = generate_multi_asset_data(
            symbols=["BTC", "ETH"], days=1, timeframe="1h", seed=42
        )

        # Should have data for both symbols
        assert set(df["symbol"].unique()) == {"BTC", "ETH"}

        # Each symbol should have 24 bars (1 day of hourly data)
        btc_count = len(df[df["symbol"] == "BTC"])
        eth_count = len(df[df["symbol"] == "ETH"])
        assert btc_count == 24
        assert eth_count == 24

    def test_different_base_prices(self):
        """Test that different assets have different price levels."""
        df = generate_multi_asset_data(symbols=["BTC", "ETH", "AAPL"], days=1, seed=42)

        btc_mean = df[df["symbol"] == "BTC"]["close"].mean()
        eth_mean = df[df["symbol"] == "ETH"]["close"].mean()
        aapl_mean = df[df["symbol"] == "AAPL"]["close"].mean()

        # BTC should be highest, then ETH, then AAPL
        assert btc_mean > eth_mean > aapl_mean

    def test_reproducibility(self):
        """Test that multi-asset generation is reproducible."""
        df1 = generate_multi_asset_data(symbols=["BTC", "ETH"], days=1, seed=42)
        df2 = generate_multi_asset_data(symbols=["BTC", "ETH"], days=1, seed=42)

        pd.testing.assert_frame_equal(df1, df2)


class TestWriteOHLCVCSV:
    """Tests for CSV writing functionality."""

    def test_write_and_read_csv(self):
        """Test that written CSV can be read back correctly."""
        df = generate_market_data(symbol="TEST", days=1, timeframe="1h", seed=42)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_output.csv"
            write_ohlcv_csv(df, output_path)

            # Read back and verify
            df_read = pd.read_csv(output_path)
            assert len(df_read) == len(df)
            assert set(df_read.columns) == set(df.columns)

    def test_creates_parent_directories(self):
        """Test that parent directories are created if needed."""
        df = generate_market_data(symbol="TEST", days=1, seed=42)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dirs" / "test.csv"
            write_ohlcv_csv(df, output_path)
            assert output_path.exists()


class TestDataValidation:
    """Tests to validate generated data meets trading requirements."""

    def test_ohlcv_relationships_long_series(self):
        """Test OHLCV relationships hold for longer series."""
        df = generate_market_data(days=30, timeframe="1h", seed=42)

        # High should be >= max(open, close)
        max_oc = df[["open", "close"]].max(axis=1)
        assert (df["high"] >= max_oc).all()

        # Low should be <= min(open, close)
        min_oc = df[["open", "close"]].min(axis=1)
        assert (df["low"] <= min_oc).all()

    def test_no_zero_prices(self):
        """Test that no zero prices are generated."""
        df = generate_market_data(days=30, seed=42)

        for col in ["open", "high", "low", "close"]:
            assert (df[col] > 0).all()

    def test_no_extreme_returns(self):
        """Test that returns are within reasonable bounds."""
        df = generate_market_data(days=30, timeframe="1h", seed=42)

        # Calculate returns
        returns = df["close"].pct_change().dropna()

        # No returns should exceed 50% (way too extreme for hourly data)
        assert (returns.abs() < 0.5).all()

    def test_volume_distribution(self):
        """Test that volume follows expected distribution."""
        df = generate_market_data(days=30, timeframe="1h", seed=42)

        # Volume should have reasonable variation
        assert df["volume"].std() > 0
        assert df["volume"].mean() > 0

        # Coefficient of variation should be reasonable
        cv = df["volume"].std() / df["volume"].mean()
        assert 0.1 < cv < 10  # Wide but reasonable bounds
