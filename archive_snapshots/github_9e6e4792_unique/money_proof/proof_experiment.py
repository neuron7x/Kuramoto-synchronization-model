#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Proof Experiment — Reproducible demonstration of Risk Guardian value.

This script runs a complete experiment comparing trading with and without
TradePulse Risk Guardian, generating metrics that demonstrate monetary value.

Usage:
    python -m money_proof.proof_experiment --csv=sample.csv
    python -m money_proof.proof_experiment --csv=data.csv --output=results.json

The experiment:
1. Loads historical price data
2. Applies a trading strategy (momentum-based by default)
3. Runs two simulations: baseline (no controls) and protected (with Risk Guardian)
4. Calculates and reports the difference in monetary terms
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import click
import numpy as np
import pandas as pd
from numpy.typing import NDArray

# Add parent to path for standalone execution
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.risk_guardian import RiskGuardian, RiskGuardianConfig, SimulationResult


def momentum_strategy(prices: NDArray[np.float64]) -> NDArray[np.float64]:
    """Simple momentum strategy: buy above SMA, sell below SMA.

    This is a basic strategy used for demonstration purposes. In practice,
    traders would use their own strategies.

    Args:
        prices: Array of price values.

    Returns:
        Array of signals: 1 (long), -1 (short), 0 (flat).
    """
    window = min(20, len(prices) // 4) if len(prices) > 4 else 1
    signals = np.zeros_like(prices)

    for i in range(window, len(prices)):
        sma = np.mean(prices[max(0, i - window) : i])
        current = prices[i]

        if current > sma * 1.01:  # 1% above SMA = bullish
            signals[i] = 1.0
        elif current < sma * 0.99:  # 1% below SMA = bearish
            signals[i] = -1.0
        else:
            signals[i] = signals[i - 1] if i > 0 else 0.0

    return signals


def mean_reversion_strategy(prices: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mean reversion strategy: buy when oversold, sell when overbought.

    Uses Bollinger Bands concept: buy when price < SMA - 2*std, sell when > SMA + 2*std.

    Args:
        prices: Array of price values.

    Returns:
        Array of signals.
    """
    window = min(20, len(prices) // 4) if len(prices) > 4 else 1
    signals = np.zeros_like(prices)

    for i in range(window, len(prices)):
        window_prices = prices[max(0, i - window) : i]
        sma = np.mean(window_prices)
        std = np.std(window_prices) if len(window_prices) > 1 else 0

        if std == 0:
            signals[i] = 0.0
            continue

        upper = sma + 2 * std
        lower = sma - 2 * std
        current = prices[i]

        if current < lower:  # Oversold
            signals[i] = 1.0
        elif current > upper:  # Overbought
            signals[i] = -1.0
        else:
            signals[i] = signals[i - 1] if i > 0 else 0.0

    return signals


def run_experiment(
    prices: NDArray[np.float64],
    strategy_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    config: RiskGuardianConfig,
    timestamps: pd.DatetimeIndex | None = None,
) -> SimulationResult:
    """Run a complete proof-of-value experiment.

    Args:
        prices: Historical price data.
        strategy_fn: Trading strategy function.
        config: Risk Guardian configuration.
        timestamps: Optional timestamps for the data.

    Returns:
        SimulationResult with comparison metrics.
    """
    guardian = RiskGuardian(config)
    return guardian.simulate_from_prices(prices, strategy_fn, timestamps=timestamps)


def print_experiment_summary(result: SimulationResult, strategy_name: str) -> None:
    """Print a formatted experiment summary to stdout."""
    print("\n" + "=" * 70)
    print("           TRADEPULSE RISK GUARDIAN - PROOF OF VALUE")
    print("=" * 70)
    print(f"\nStrategy: {strategy_name}")
    print(f"Periods: {result.total_periods:,}")
    print(f"Initial Capital: ${result.config.initial_capital:,.0f}")
    print()
    print(result.summary())


@click.command()
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to CSV file with price data.",
)
@click.option(
    "--price-col",
    default="close",
    show_default=True,
    help="Column name containing prices.",
)
@click.option(
    "--timestamp-col",
    default=None,
    help="Column name containing timestamps.",
)
@click.option(
    "--strategy",
    type=click.Choice(["momentum", "mean_reversion"]),
    default="momentum",
    show_default=True,
    help="Trading strategy to use.",
)
@click.option(
    "--initial-capital",
    type=float,
    default=100_000,
    show_default=True,
    help="Starting capital.",
)
@click.option(
    "--daily-limit",
    type=float,
    default=5.0,
    show_default=True,
    help="Daily loss limit percentage.",
)
@click.option(
    "--max-drawdown",
    type=float,
    default=10.0,
    show_default=True,
    help="Max drawdown kill-switch percentage.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to save JSON results.",
)
def main(
    csv_path: Path,
    price_col: str,
    timestamp_col: str | None,
    strategy: str,
    initial_capital: float,
    daily_limit: float,
    max_drawdown: float,
    output_path: Path | None,
) -> None:
    """Run a Risk Guardian proof-of-value experiment.

    This script demonstrates the monetary value of TradePulse Risk Guardian
    by comparing trading performance with and without risk controls.

    \b
    Example:
        python -m money_proof.proof_experiment --csv=sample.csv
        python -m money_proof.proof_experiment --csv=data.csv --strategy=mean_reversion
    """
    # Load data
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        click.echo(f"Error loading CSV: {e}", err=True)
        sys.exit(1)

    if price_col not in df.columns:
        click.echo(f"Error: Column '{price_col}' not found in CSV", err=True)
        sys.exit(1)

    prices = df[price_col].to_numpy(dtype=float)

    # Get timestamps if available
    timestamps = None
    if timestamp_col and timestamp_col in df.columns:
        timestamps = pd.to_datetime(df[timestamp_col])
    elif df.index.name and "date" in df.index.name.lower():
        timestamps = pd.to_datetime(df.index)

    # Select strategy
    strategy_fn = (
        momentum_strategy if strategy == "momentum" else mean_reversion_strategy
    )
    strategy_name = (
        "Momentum (SMA Crossover)"
        if strategy == "momentum"
        else "Mean Reversion (Bollinger)"
    )

    # Configure Risk Guardian
    config = RiskGuardianConfig(
        initial_capital=initial_capital,
        daily_loss_limit_pct=daily_limit,
        max_drawdown_pct=max_drawdown,
        safe_mode_threshold_pct=max_drawdown * 0.7,  # 70% of max as warning
    )

    # Run experiment
    result = run_experiment(prices, strategy_fn, config, timestamps)

    # Print results
    print_experiment_summary(result, strategy_name)

    # Save if requested
    if output_path:
        output_data = {
            "experiment": {
                "timestamp": datetime.now().isoformat(),
                "data_source": str(csv_path),
                "strategy": strategy_name,
                "periods": result.total_periods,
            },
            "results": result.to_dict(),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
        click.echo(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
