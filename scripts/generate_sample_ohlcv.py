#!/usr/bin/env python3
"""Generate comprehensive OHLCV sample data for testing and development.

This script creates realistic OHLCV (Open, High, Low, Close, Volume) time series
data with configurable market regimes, useful for testing trading algorithms,
indicators, and market analysis tools.

Usage:
    python scripts/generate_sample_ohlcv.py --output data/sample_multi_asset.csv
    python scripts/generate_sample_ohlcv.py --symbols BTC ETH --days 30 --seed 42
"""
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

from __future__ import annotations

import argparse
import logging
import sys
from datetime import timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = Path("data/sample_ohlcv_generated.csv")
DEFAULT_NUM_DAYS = 7
DEFAULT_TIMEFRAME = "1h"
DEFAULT_SEED = 42


def generate_price_series(
    n: int,
    base_price: float = 100.0,
    volatility: float = 0.02,
    drift: float = 0.0001,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a geometric Brownian motion price series.

    Args:
        n: Number of data points
        base_price: Starting price
        volatility: Volatility parameter (standard deviation of returns)
        drift: Drift parameter (mean return per step)
        seed: Random seed for reproducibility

    Returns:
        Array of simulated prices
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, volatility, n)
    log_prices = np.cumsum(returns)
    prices = base_price * np.exp(log_prices)
    return prices


def generate_ohlcv_from_ticks(
    close_prices: np.ndarray,
    intrabar_volatility: float = 0.005,
    volume_mean: float = 10000.0,
    volume_std: float = 5000.0,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate OHLCV bars from close prices.

    Args:
        close_prices: Array of closing prices
        intrabar_volatility: Expected intrabar price movement
        volume_mean: Mean volume per bar
        volume_std: Volume standard deviation
        seed: Random seed for reproducibility

    Returns:
        DataFrame with columns: open, high, low, close, volume
    """
    rng = np.random.default_rng(seed)
    n = len(close_prices)

    # Generate open prices (previous close with small gap)
    open_prices = np.zeros(n)
    open_prices[0] = close_prices[0] * (1 + rng.normal(0, 0.001))
    open_prices[1:] = close_prices[:-1] * (1 + rng.normal(0, 0.001, n - 1))

    # Generate high and low prices
    high_deviation = np.abs(rng.normal(0, intrabar_volatility, n))
    low_deviation = np.abs(rng.normal(0, intrabar_volatility, n))

    max_oc = np.maximum(open_prices, close_prices)
    min_oc = np.minimum(open_prices, close_prices)

    high_prices = max_oc * (1 + high_deviation)
    low_prices = min_oc * (1 - low_deviation)

    # Generate volume (log-normal distribution)
    # Use proper sigma calculation to achieve target coefficient of variation
    cv = volume_std / volume_mean
    sigma = np.sqrt(np.log(1 + cv**2))
    mu = np.log(volume_mean) - 0.5 * sigma**2
    volume = np.abs(rng.lognormal(mu, sigma, n))

    return pd.DataFrame(
        {
            "open": open_prices.round(4),
            "high": high_prices.round(4),
            "low": low_prices.round(4),
            "close": close_prices.round(4),
            "volume": volume.round(2),
        }
    )


def generate_market_data(
    symbol: str = "ASSET",
    days: int = DEFAULT_NUM_DAYS,
    timeframe: str = DEFAULT_TIMEFRAME,
    base_price: float = 100.0,
    volatility: float = 0.02,
    seed: int | None = None,
    start_date: str | None = None,
) -> pd.DataFrame:
    """Generate complete market data for a single symbol.

    Args:
        symbol: Asset symbol name
        days: Number of days of data to generate
        timeframe: Bar timeframe (1m, 5m, 15m, 1h, 4h, 1d)
        base_price: Starting price for the asset
        volatility: Daily volatility
        seed: Random seed for reproducibility
        start_date: Start date in ISO format (default: 2024-01-01)

    Returns:
        DataFrame with timestamp, symbol, and OHLCV columns
    """
    # Calculate number of bars based on timeframe
    timeframe_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }
    minutes = timeframe_minutes.get(timeframe, 60)
    bars_per_day = 1440 // minutes
    n_bars = days * bars_per_day

    # Adjust volatility for timeframe
    bar_volatility = volatility * np.sqrt(minutes / 1440)

    # Generate timestamps
    start = pd.Timestamp(start_date or "2024-01-01", tz=timezone.utc)
    timestamps = pd.date_range(start, periods=n_bars, freq=f"{minutes}min")

    # Generate price series with regime changes
    close_prices = generate_price_series(
        n_bars,
        base_price=base_price,
        volatility=bar_volatility,
        drift=0.0001 * (minutes / 1440),
        seed=seed,
    )

    # Generate OHLCV from closes
    ohlcv = generate_ohlcv_from_ticks(
        close_prices,
        intrabar_volatility=bar_volatility * 0.5,
        volume_mean=10000 * (minutes / 60),  # Scale volume with timeframe
        volume_std=5000 * (minutes / 60),
        seed=seed + 1000 if seed is not None else None,
    )

    # Add timestamp and symbol
    ohlcv.insert(0, "timestamp", timestamps)
    ohlcv.insert(1, "symbol", symbol)

    return ohlcv


def generate_multi_asset_data(
    symbols: list[str],
    days: int = DEFAULT_NUM_DAYS,
    timeframe: str = DEFAULT_TIMEFRAME,
    seed: int | None = None,
    start_date: str | None = None,
) -> pd.DataFrame:
    """Generate market data for multiple assets.

    Args:
        symbols: List of asset symbols
        days: Number of days of data
        timeframe: Bar timeframe
        seed: Base random seed
        start_date: Start date in ISO format

    Returns:
        DataFrame with all assets' data concatenated
    """
    # Default configurations for common assets
    asset_configs = {
        "BTC": {"base_price": 45000.0, "volatility": 0.03},
        "ETH": {"base_price": 2500.0, "volatility": 0.04},
        "SOL": {"base_price": 100.0, "volatility": 0.05},
        "AAPL": {"base_price": 180.0, "volatility": 0.015},
        "SPY": {"base_price": 480.0, "volatility": 0.01},
        "EURUSD": {"base_price": 1.08, "volatility": 0.005},
        "GOLD": {"base_price": 2000.0, "volatility": 0.008},
    }

    all_data = []
    for i, symbol in enumerate(symbols):
        config = asset_configs.get(
            symbol.upper(), {"base_price": 100.0, "volatility": 0.02}
        )
        symbol_seed = seed + i * 10000 if seed is not None else None

        df = generate_market_data(
            symbol=symbol.upper(),
            days=days,
            timeframe=timeframe,
            base_price=config["base_price"],
            volatility=config["volatility"],
            seed=symbol_seed,
            start_date=start_date,
        )
        all_data.append(df)

    return pd.concat(all_data, ignore_index=True)


def write_ohlcv_csv(
    df: pd.DataFrame,
    output_path: Path,
) -> Path:
    """Write OHLCV data to CSV file.

    Args:
        df: DataFrame with OHLCV data
        output_path: Output file path

    Returns:
        Path to the written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    LOGGER.info("Wrote %d rows to %s", len(df), output_path)
    return output_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic OHLCV market data for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate single asset data
    python scripts/generate_sample_ohlcv.py --output data/btc_sample.csv --symbols BTC

    # Generate multi-asset data for 30 days
    python scripts/generate_sample_ohlcv.py --symbols BTC ETH SOL --days 30

    # Generate 1-minute data
    python scripts/generate_sample_ohlcv.py --timeframe 1m --days 1
        """,
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output CSV file path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--symbols",
        "-s",
        nargs="+",
        default=["ASSET"],
        help="Asset symbols to generate (default: ASSET)",
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=DEFAULT_NUM_DAYS,
        help=f"Number of days of data to generate (default: {DEFAULT_NUM_DAYS})",
    )
    parser.add_argument(
        "--timeframe",
        "-t",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        default=DEFAULT_TIMEFRAME,
        help=f"Bar timeframe (default: {DEFAULT_TIMEFRAME})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-01",
        help="Start date in ISO format (default: 2024-01-01)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        LOGGER.info(
            "Generating OHLCV data: symbols=%s, days=%d, timeframe=%s",
            args.symbols,
            args.days,
            args.timeframe,
        )

        df = generate_multi_asset_data(
            symbols=args.symbols,
            days=args.days,
            timeframe=args.timeframe,
            seed=args.seed,
            start_date=args.start_date,
        )

        output_path = write_ohlcv_csv(df, args.output)
        print(f"✅ Generated {len(df)} rows of OHLCV data to {output_path}")
        return 0

    except Exception as e:
        LOGGER.exception("Failed to generate OHLCV data: %s", e)
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
