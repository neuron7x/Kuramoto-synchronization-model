#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Example usage of the Dopamine TD backtesting module.

This script demonstrates how to use the dopamine-based temporal difference
learning algorithm for generating trading signals and running backtests.
"""

import numpy as np

from backtest import DopamineTDParams, run_dopamine_backtest
from core.utils.determinism import seed_numpy


def main():
    """Run example dopamine TD backtest."""
    # Generate synthetic price data (random walk)
    seed_numpy()
    returns = np.random.normal(0, 0.001, 10_000)
    prices = 100.0 * np.cumprod(1 + returns)

    print("Running Dopamine TD Backtest Example")
    print("=" * 50)
    print(f"Number of price points: {len(prices)}")
    print(f"Initial price: ${prices[0]:.2f}")
    print(f"Final price: ${prices[-1]:.2f}")
    print()

    # Configure dopamine TD parameters
    config = DopamineTDParams(
        discount_gamma=0.99,
        learning_rate_v=0.01,
        decay_rate=0.1,
        burst_factor=2.0,
        k=5.0,
        theta=0.5,
        c_novelty=0.1,
    )

    print("Configuration:")
    print(f"  Discount gamma: {config.discount_gamma}")
    print(f"  Learning rate: {config.learning_rate_v}")
    print(f"  Decay rate: {config.decay_rate}")
    print(f"  Burst factor: {config.burst_factor}")
    print(f"  Sigmoid k: {config.k}")
    print(f"  Sigmoid theta: {config.theta}")
    print(f"  Novelty weight: {config.c_novelty}")
    print()

    # Run backtest
    print("Running backtest...")
    result = run_dopamine_backtest(
        prices,
        config=config,
        fee=0.0005,  # 0.05% transaction fee
        initial_capital=10000.0,
    )

    print("Backtest Results:")
    print("=" * 50)
    print(f"PnL: ${result.pnl:.2f}")
    print(f"Max Drawdown: ${result.max_dd:.2f}")
    print(f"Number of Trades: {result.trades}")
    print(f"Commission Cost: ${result.commission_cost:.2f}")
    print(f"Spread Cost: ${result.spread_cost:.2f}")
    print()

    if result.equity_curve is not None:
        print(f"Equity Curve Shape: {result.equity_curve.shape}")
        print(f"Final Equity: ${result.equity_curve[-1]:.2f}")
        print()

    # Example with different parameters
    print("Running backtest with more aggressive parameters...")
    aggressive_config = DopamineTDParams(
        discount_gamma=0.95,
        learning_rate_v=0.02,
        k=10.0,  # Higher k = more sensitive to dopamine changes
        theta=0.6,  # Higher threshold = more selective entries
    )

    result_aggressive = run_dopamine_backtest(
        prices,
        config=aggressive_config,
        fee=0.0005,
    )

    print("Aggressive Strategy Results:")
    print("=" * 50)
    print(f"PnL: ${result_aggressive.pnl:.2f}")
    print(f"Max Drawdown: ${result_aggressive.max_dd:.2f}")
    print(f"Number of Trades: {result_aggressive.trades}")
    print()

    print("Example completed successfully!")


if __name__ == "__main__":
    main()
