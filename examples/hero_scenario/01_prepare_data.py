#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Prepare data for the hero backtest scenario.

This script loads the bundled sample crypto OHLCV data, filters it for BTC only,
validates it, and saves it to a deterministic path for use by the backtest engine.

The hero scenario uses BTC 1-hour data from 2024-01-01 onwards, which is already
included in the repository as test data. This ensures reproducibility without
requiring external API calls or secrets.

Usage:
    python examples/hero_scenario/01_prepare_data.py
    python examples/hero_scenario/01_prepare_data.py --output data/hero/btc_1h.csv
"""

import argparse
from pathlib import Path

import pandas as pd


def prepare_hero_data(
    source_path: Path,
    output_path: Path,
    symbol: str = "BTC",
) -> pd.DataFrame:
    """Load, filter, and validate hero scenario data.

    Args:
        source_path: Path to source OHLCV CSV file.
        output_path: Path where processed data will be saved.
        symbol: Symbol to filter for (default: BTC).

    Returns:
        DataFrame with prepared data.
    """
    print(f"Loading data from {source_path}...")
    df = pd.read_csv(source_path, parse_dates=["timestamp"])

    # Filter for BTC only
    print(f"Filtering for {symbol}...")
    df = df[df["symbol"] == symbol].copy()

    # Sort by timestamp to ensure chronological order
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Set timestamp as index
    df = df.set_index("timestamp")

    # Validate data quality
    print("\nData Quality Checks:")
    print(f"  Total rows: {len(df)}")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Missing values: {df.isnull().sum().sum()}")
    print(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    # Check for any missing values
    if df.isnull().any().any():
        raise ValueError("Data contains missing values")

    # Ensure positive prices
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Data contains non-positive prices")

    # Ensure high >= low
    if (df["high"] < df["low"]).any():
        raise ValueError("Data contains high < low inconsistency")

    # Ensure high is the highest and low is the lowest
    if not ((df["high"] >= df["open"]) & (df["high"] >= df["close"])).all():
        raise ValueError("High is not consistently the highest price")
    if not ((df["low"] <= df["open"]) & (df["low"] <= df["close"])).all():
        raise ValueError("Low is not consistently the lowest price")

    print("\n✓ All data quality checks passed")

    # Save processed data
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path)
    print(f"\n✓ Saved processed data to {output_path}")

    return df


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare data for hero backtest scenario"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/sample_crypto_ohlcv.csv"),
        help="Path to source OHLCV data (default: data/sample_crypto_ohlcv.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/hero/btc_1h.csv"),
        help="Path to save processed data (default: data/hero/btc_1h.csv)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC",
        help="Symbol to filter for (default: BTC)",
    )

    args = parser.parse_args()

    # Convert relative paths to absolute based on repo root
    repo_root = Path(__file__).parent.parent.parent
    source_path = repo_root / args.source
    output_path = repo_root / args.output

    if not source_path.exists():
        raise FileNotFoundError(f"Source data not found: {source_path}")

    df = prepare_hero_data(source_path, output_path, args.symbol)

    print(f"\nReady for backtest with {len(df)} bars of {args.symbol} data")
    print(f"Run: python examples/hero_scenario/02_run_backtest.py")


if __name__ == "__main__":
    main()
