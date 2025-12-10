#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Prepare data for the hero backtest scenario.

This script extracts a clean subset of BTC/USD data from the existing sample
dataset for use in the hero scenario. It validates data quality and saves it
in a format ready for backtesting.
"""

import pandas as pd
from pathlib import Path


def prepare_hero_data():
    """Extract and prepare BTC/USD data for hero scenario."""
    # Load sample crypto data from repository
    repo_root = Path(__file__).parent.parent.parent
    source_file = repo_root / "data" / "sample_crypto_ohlcv.csv"
    output_dir = repo_root / "data" / "hero"
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("HERO SCENARIO: Data Preparation")
    print("=" * 60)
    print()
    
    # Load data
    print(f"Loading data from: {source_file}")
    df = pd.read_csv(source_file)
    print(f"  Total rows loaded: {len(df)}")
    print(f"  Symbols: {df['symbol'].unique().tolist()}")
    print()
    
    # Filter to BTC only
    btc = df[df['symbol'] == 'BTC'].copy()
    print(f"Filtering to BTC only: {len(btc)} rows")
    
    # Basic validation
    assert len(btc) > 0, "No BTC data found"
    assert 'close' in btc.columns, "Missing 'close' column"
    assert btc['close'].notna().all(), "NaN values in close prices"
    assert (btc['close'] > 0).all(), "Non-positive prices found"
    
    print(f"  Date range: {btc['timestamp'].min()} to {btc['timestamp'].max()}")
    print(f"  Price range: ${btc['close'].min():.2f} to ${btc['close'].max():.2f}")
    print()
    
    # Save prepared data
    output_file = output_dir / "btc_1h.csv"
    btc.to_csv(output_file, index=False)
    print(f"✓ Data saved to: {output_file}")
    print(f"  Rows: {len(btc)}")
    print(f"  Size: {output_file.stat().st_size / 1024:.1f} KB")
    print()
    
    # Display sample
    print("Sample data (first 5 rows):")
    print(btc.head().to_string())
    print()
    
    print("=" * 60)
    print("Data preparation complete!")
    print("=" * 60)
    
    return output_file


if __name__ == "__main__":
    prepare_hero_data()
