# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for generate_sample_ohlcv.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import generate_sample_ohlcv


def test_generate_price_series_length() -> None:
    """Test that generate_price_series returns correct length."""
    n = 100
    prices = generate_sample_ohlcv.generate_price_series(n=n)
    assert len(prices) == n


def test_generate_price_series_base_price() -> None:
    """Test that generate_price_series respects base price."""
    base_price = 50.0
    prices = generate_sample_ohlcv.generate_price_series(n=10, base_price=base_price, seed=42)
    # First price should be close to base price
    assert abs(prices[0] - base_price) < base_price * 0.5


def test_generate_price_series_deterministic() -> None:
    """Test that generate_price_series is deterministic with seed."""
    prices1 = generate_sample_ohlcv.generate_price_series(n=100, seed=42)
    prices2 = generate_sample_ohlcv.generate_price_series(n=100, seed=42)
    np.testing.assert_array_equal(prices1, prices2)


def test_generate_price_series_positive() -> None:
    """Test that generate_price_series produces positive prices."""
    prices = generate_sample_ohlcv.generate_price_series(n=1000, seed=42)
    assert np.all(prices > 0)


def test_generate_ohlcv_from_ticks_columns() -> None:
    """Test that generate_ohlcv_from_ticks returns correct columns."""
    close_prices = np.array([100.0, 102.0, 105.0, 103.0])
    df = generate_sample_ohlcv.generate_ohlcv_from_ticks(close_prices, seed=42)

    expected_cols = ["open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols


def test_generate_ohlcv_from_ticks_length() -> None:
    """Test that generate_ohlcv_from_ticks returns correct length."""
    close_prices = np.array([100.0, 102.0, 105.0])
    df = generate_sample_ohlcv.generate_ohlcv_from_ticks(close_prices, seed=42)

    assert len(df) == 3


def test_generate_ohlcv_from_ticks_ohlc_relationships() -> None:
    """Test OHLC relationships in generated data."""
    close_prices = np.array([100.0, 102.0, 105.0, 103.0, 101.0])
    df = generate_sample_ohlcv.generate_ohlcv_from_ticks(close_prices, seed=42)

    # High should be >= max(open, close)
    max_oc = np.maximum(df["open"].values, df["close"].values)
    assert np.all(df["high"].values >= max_oc - 0.0001)  # small tolerance

    # Low should be <= min(open, close)
    min_oc = np.minimum(df["open"].values, df["close"].values)
    assert np.all(df["low"].values <= min_oc + 0.0001)

    # High >= Low
    assert np.all(df["high"].values >= df["low"].values)


def test_generate_ohlcv_from_ticks_positive_volume() -> None:
    """Test that generated volume is positive."""
    close_prices = np.array([100.0, 102.0, 105.0])
    df = generate_sample_ohlcv.generate_ohlcv_from_ticks(close_prices, seed=42)

    assert np.all(df["volume"].values > 0)


def test_generate_market_data_columns() -> None:
    """Test that generate_market_data returns correct columns."""
    df = generate_sample_ohlcv.generate_market_data(symbol="BTC", days=1, timeframe="1h", seed=42)

    expected_cols = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols


def test_generate_market_data_symbol() -> None:
    """Test that generate_market_data uses correct symbol."""
    df = generate_sample_ohlcv.generate_market_data(symbol="ETH", days=1, timeframe="1h", seed=42)

    assert all(df["symbol"] == "ETH")


def test_generate_market_data_bar_count() -> None:
    """Test that generate_market_data produces correct number of bars."""
    # 1 day with 1h timeframe = 24 bars
    df = generate_sample_ohlcv.generate_market_data(symbol="BTC", days=1, timeframe="1h", seed=42)
    assert len(df) == 24

    # 1 day with 4h timeframe = 6 bars
    df = generate_sample_ohlcv.generate_market_data(symbol="BTC", days=1, timeframe="4h", seed=42)
    assert len(df) == 6


def test_generate_market_data_timestamps() -> None:
    """Test that timestamps are correctly generated."""
    df = generate_sample_ohlcv.generate_market_data(
        symbol="BTC",
        days=1,
        timeframe="1h",
        seed=42,
        start_date="2024-06-01",
    )

    assert pd.Timestamp("2024-06-01", tz="UTC") == df["timestamp"].iloc[0]


def test_generate_multi_asset_data_multiple_symbols() -> None:
    """Test that generate_multi_asset_data handles multiple symbols."""
    df = generate_sample_ohlcv.generate_multi_asset_data(
        symbols=["BTC", "ETH"], days=1, timeframe="1h", seed=42
    )

    assert len(df["symbol"].unique()) == 2
    assert "BTC" in df["symbol"].values
    assert "ETH" in df["symbol"].values


def test_generate_multi_asset_data_uses_asset_configs() -> None:
    """Test that asset-specific configs are applied."""
    df = generate_sample_ohlcv.generate_multi_asset_data(
        symbols=["BTC", "EURUSD"], days=1, timeframe="1d", seed=42
    )

    btc_close = df[df["symbol"] == "BTC"]["close"].iloc[0]
    eurusd_close = df[df["symbol"] == "EURUSD"]["close"].iloc[0]

    # BTC should have much higher price than EURUSD
    assert btc_close > eurusd_close * 100


def test_generate_multi_asset_data_deterministic() -> None:
    """Test that multi-asset generation is deterministic with seed."""
    df1 = generate_sample_ohlcv.generate_multi_asset_data(
        symbols=["BTC", "ETH"], days=1, timeframe="1h", seed=42
    )
    df2 = generate_sample_ohlcv.generate_multi_asset_data(
        symbols=["BTC", "ETH"], days=1, timeframe="1h", seed=42
    )

    pd.testing.assert_frame_equal(df1, df2)


def test_write_ohlcv_csv(tmp_path: Path) -> None:
    """Test that write_ohlcv_csv creates file correctly."""
    df = pd.DataFrame(
        {
            "timestamp": ["2024-01-01"],
            "symbol": ["TEST"],
            "open": [100.0],
            "high": [105.0],
            "low": [98.0],
            "close": [102.0],
            "volume": [1000.0],
        }
    )
    output_path = tmp_path / "test.csv"

    result = generate_sample_ohlcv.write_ohlcv_csv(df, output_path)

    assert result == output_path
    assert output_path.exists()

    # Verify content
    loaded = pd.read_csv(output_path)
    assert len(loaded) == 1
    assert loaded["symbol"].iloc[0] == "TEST"


def test_write_ohlcv_csv_creates_parent_dirs(tmp_path: Path) -> None:
    """Test that write_ohlcv_csv creates parent directories."""
    df = pd.DataFrame({"timestamp": ["2024-01-01"], "close": [100.0]})
    output_path = tmp_path / "subdir" / "nested" / "data.csv"

    generate_sample_ohlcv.write_ohlcv_csv(df, output_path)

    assert output_path.exists()


def test_parse_args_defaults() -> None:
    """Test parse_args returns correct defaults."""
    args = generate_sample_ohlcv.parse_args([])

    assert args.output == generate_sample_ohlcv.DEFAULT_OUTPUT_PATH
    assert args.symbols == ["ASSET"]
    assert args.days == generate_sample_ohlcv.DEFAULT_NUM_DAYS
    assert args.timeframe == generate_sample_ohlcv.DEFAULT_TIMEFRAME
    assert args.seed == generate_sample_ohlcv.DEFAULT_SEED
    assert args.verbose is False


def test_parse_args_custom_values() -> None:
    """Test parse_args with custom values."""
    args = generate_sample_ohlcv.parse_args(
        [
            "-o",
            "custom.csv",
            "--symbols",
            "BTC",
            "ETH",
            "-d",
            "30",
            "-t",
            "4h",
            "--seed",
            "123",
            "-v",
        ]
    )

    assert args.output == Path("custom.csv")
    assert args.symbols == ["BTC", "ETH"]
    assert args.days == 30
    assert args.timeframe == "4h"
    assert args.seed == 123
    assert args.verbose is True


def test_main_success(tmp_path: Path, capsys) -> None:
    """Test main returns 0 on success."""
    output_path = tmp_path / "output.csv"

    exit_code = generate_sample_ohlcv.main(
        [
            "-o",
            str(output_path),
            "-d",
            "1",
            "-t",
            "1h",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    captured = capsys.readouterr()
    assert "Generated" in captured.out


def test_main_creates_output_file(tmp_path: Path) -> None:
    """Test that main creates the output file."""
    output_path = tmp_path / "generated.csv"

    generate_sample_ohlcv.main(
        [
            "-o",
            str(output_path),
            "--symbols",
            "BTC",
            "-d",
            "1",
            "-t",
            "1h",
        ]
    )

    assert output_path.exists()
    df = pd.read_csv(output_path)
    assert len(df) == 24  # 1 day, 1h timeframe
    assert "BTC" in df["symbol"].values


def test_main_multiple_symbols(tmp_path: Path) -> None:
    """Test main with multiple symbols."""
    output_path = tmp_path / "multi.csv"

    generate_sample_ohlcv.main(
        [
            "-o",
            str(output_path),
            "--symbols",
            "BTC",
            "ETH",
            "SOL",
            "-d",
            "1",
            "-t",
            "1d",
        ]
    )

    df = pd.read_csv(output_path)
    assert len(df["symbol"].unique()) == 3


def test_constants_defined() -> None:
    """Test that module constants are defined."""
    assert generate_sample_ohlcv.DEFAULT_OUTPUT_PATH is not None
    assert generate_sample_ohlcv.DEFAULT_NUM_DAYS > 0
    assert generate_sample_ohlcv.DEFAULT_TIMEFRAME in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    assert isinstance(generate_sample_ohlcv.DEFAULT_SEED, int)
