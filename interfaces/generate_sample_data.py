#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate sample market data CSV files for testing GeoSync interfaces.

This utility creates realistic synthetic market data suitable for testing
the CLI, dashboard, and other interfaces. The generated data includes
price, volume, and timestamp information with configurable market regimes.

Usage:
    python generate_sample_data.py --output sample.csv --periods 1000
    python generate_sample_data.py --regime trending --periods 500
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


def generate_trending_prices(
    n: int,
    initial_price: float = 100.0,
    trend: float = 0.02,
    volatility: float = 1.0,
    seed: int | None = None,
) -> np.ndarray:
    """Generate prices with a trending pattern.

    Args:
        n: Number of price points to generate.
        initial_price: Starting price level.
        trend: Trend strength (positive = uptrend, negative = downtrend).
        volatility: Price volatility multiplier.
        seed: Random seed for reproducibility.

    Returns:
        Array of generated prices.
    """
    rng = np.random.default_rng(seed)

    # Create trend component
    np.linspace(0, trend * n, n)

    # Create noise component
    noise = rng.normal(0, volatility, n)

    # Combine and cumsum
    returns = (trend + noise) / 100
    prices = initial_price * np.exp(np.cumsum(returns))

    return prices


def generate_mean_reverting_prices(
    n: int,
    mean_price: float = 100.0,
    reversion_speed: float = 0.1,
    volatility: float = 1.5,
    seed: int | None = None,
) -> np.ndarray:
    """Generate prices with mean-reverting behavior.

    Args:
        n: Number of price points to generate.
        mean_price: Central price level.
        reversion_speed: Speed of reversion to mean (0-1).
        volatility: Price volatility multiplier.
        seed: Random seed for reproducibility.

    Returns:
        Array of generated prices.
    """
    rng = np.random.default_rng(seed)
    prices = np.zeros(n)
    prices[0] = mean_price

    for i in range(1, n):
        # Ornstein-Uhlenbeck process
        drift = reversion_speed * (mean_price - prices[i - 1])
        shock = rng.normal(0, volatility)
        prices[i] = prices[i - 1] + drift + shock

    return prices


def generate_random_walk_prices(
    n: int,
    initial_price: float = 100.0,
    volatility: float = 1.0,
    seed: int | None = None,
) -> np.ndarray:
    """Generate prices following a random walk.

    Args:
        n: Number of price points to generate.
        initial_price: Starting price level.
        volatility: Price volatility multiplier.
        seed: Random seed for reproducibility.

    Returns:
        Array of generated prices.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, volatility / 100, n)
    prices = initial_price * np.exp(np.cumsum(returns))

    return prices


def generate_volume(
    n: int,
    mean_volume: float = 1_000_000,
    volatility: float = 0.3,
    price_correlation: float = 0.2,
    prices: np.ndarray | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate trading volume data.

    Args:
        n: Number of volume points to generate.
        mean_volume: Average volume level.
        volatility: Volume volatility (log-normal sigma).
        price_correlation: Correlation with price changes (-1 to 1).
        prices: Optional price array for correlation.
        seed: Random seed for reproducibility.

    Returns:
        Array of generated volumes.
    """
    rng = np.random.default_rng(seed)

    # Base log-normal volume
    volume = rng.lognormal(mean=np.log(mean_volume) - (volatility**2) / 2, sigma=volatility, size=n)

    # Add correlation with price changes if prices provided
    if prices is not None and len(prices) == n and price_correlation != 0:
        price_returns = np.diff(np.log(prices), prepend=np.log(prices[0]))
        volume_adjustment = 1 + price_correlation * np.abs(price_returns)
        volume = volume * volume_adjustment

    return volume


def generate_market_data(
    periods: int,
    regime: Literal["trending", "mean_reverting", "random_walk"] = "random_walk",
    freq: str = "1h",
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate a complete market data CSV.

    Args:
        periods: Number of periods to generate.
        regime: Market regime type.
        freq: Time frequency (e.g., '1h', '5m', '1d').
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with timestamp, price, and volume columns.
    """
    # Generate timestamps
    start_date = datetime(2024, 1, 1, 9, 0, 0)
    timestamps = pd.date_range(start_date, periods=periods, freq=freq)

    # Generate prices based on regime
    if regime == "trending":
        prices = generate_trending_prices(periods, trend=0.03, volatility=1.2, seed=seed)
    elif regime == "mean_reverting":
        prices = generate_mean_reverting_prices(
            periods, reversion_speed=0.15, volatility=2.0, seed=seed
        )
    else:  # random_walk
        prices = generate_random_walk_prices(periods, volatility=1.5, seed=seed)

    # Generate correlated volume
    volume = generate_volume(
        periods,
        mean_volume=1_500_000,
        volatility=0.4,
        price_correlation=0.3,
        prices=prices,
        seed=seed,
    )

    # Create DataFrame
    df = pd.DataFrame({"timestamp": timestamps, "price": prices, "volume": volume.astype(int)})

    return df


def main():
    """Main entry point for the sample data generator."""
    parser = argparse.ArgumentParser(
        description="Generate sample market data CSV for testing GeoSync interfaces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate 1000 periods of random walk data
    python generate_sample_data.py --output random_data.csv --periods 1000

    # Generate trending market data
    python generate_sample_data.py --output trending.csv --periods 500 --regime trending

    # Generate mean-reverting data with 5-minute frequency
    python generate_sample_data.py --output mrv.csv --periods 2000 --regime mean_reverting --freq 5m

    # Use specific random seed for reproducibility
    python generate_sample_data.py --output data.csv --periods 300 --seed 42
        """,
    )

    parser.add_argument("--output", "-o", type=str, required=True, help="Output CSV file path")

    parser.add_argument(
        "--periods",
        "-n",
        type=int,
        default=1000,
        help="Number of periods to generate (default: 1000)",
    )

    parser.add_argument(
        "--regime",
        "-r",
        type=str,
        choices=["trending", "mean_reverting", "random_walk"],
        default="random_walk",
        help="Market regime type (default: random_walk)",
    )

    parser.add_argument(
        "--freq",
        "-f",
        type=str,
        default="1h",
        help="Time frequency: e.g., 1m, 5m, 15m, 1h, 4h, 1d (default: 1h)",
    )

    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility (optional)",
    )

    args = parser.parse_args()

    # Generate data
    print(f"Generating {args.periods} periods of {args.regime} market data...")
    df = generate_market_data(
        periods=args.periods, regime=args.regime, freq=args.freq, seed=args.seed
    )

    # Save to CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # Print summary
    print(f"\n✓ Generated {len(df)} rows of market data")
    print(f"✓ Saved to: {output_path.absolute()}")
    print("\nData Summary:")
    print(f"  Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Price range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
    print(f"  Mean price: ${df['price'].mean():.2f}")
    print(f"  Price std dev: ${df['price'].std():.2f}")
    print(f"  Mean volume: {df['volume'].mean():,.0f}")
    print("\nYou can now use this data with:")
    print(f"  geosync analyze --csv {output_path}")
    print(f"  geosync backtest --csv {output_path}")
    print("  streamlit run interfaces/dashboard_streamlit.py")


if __name__ == "__main__":
    main()
