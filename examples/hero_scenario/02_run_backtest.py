#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Run the hero backtest scenario.

This script executes a simple momentum-based backtest on BTC/USD hourly data
using a simple walk-forward approach. It produces equity curve and metrics that
can be compared against golden snapshots for regression testing.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path


def momentum_signal(prices: np.ndarray, window: int = 24) -> np.ndarray:
    """Simple momentum signal based on price changes.
    
    Args:
        prices: Array of price values
        window: Lookback window for momentum calculation (default 24h)
    
    Returns:
        Signal array: 1 (long), 0 (flat), -1 (short)
    """
    signal = np.zeros_like(prices)
    
    for i in range(window, len(prices)):
        # Compare current price to price 24 hours ago
        price_change = prices[i] - prices[i - window]
        
        if price_change > 0:
            signal[i] = 1.0  # Long
        elif price_change < 0:
            signal[i] = -1.0  # Short
        else:
            signal[i] = 0.0  # Flat
    
    return signal


def simple_momentum_backtest(prices, window=24, fee=0.001, initial_capital=100000.0):
    """Simple momentum backtest implementation.
    
    Args:
        prices: Array of close prices
        window: Lookback window in bars
        fee: Transaction fee as decimal (0.001 = 0.1%)
        initial_capital: Starting capital
    
    Returns:
        Dictionary with backtest results
    """
    n = len(prices)
    position = 0.0  # Current position (-1, 0, 1)
    equity = np.zeros(n)
    equity[0] = initial_capital
    cash = initial_capital
    pnl = 0.0
    trades = 0
    commission_cost = 0.0
    
    for i in range(1, n):
        # Calculate signal
        if i >= window:
            price_change = prices[i] - prices[i - window]
            if price_change > 0:
                signal = 1.0  # Long
            elif price_change < 0:
                signal = -1.0  # Short
            else:
                signal = 0.0  # Flat
        else:
            signal = 0.0  # Warmup period
        
        # Execute trade if signal changes
        if signal != position:
            # Close existing position
            if position != 0:
                pnl_change = position * (prices[i] - prices[i - 1])
                pnl += pnl_change
                cash += pnl_change
                
            # Open new position
            if signal != 0:
                cost = abs(signal) * prices[i] * fee
                commission_cost += cost
                cash -= cost
                trades += 1
            
            position = signal
        else:
            # Update P&L for existing position
            if position != 0:
                pnl_change = position * (prices[i] - prices[i - 1])
                pnl += pnl_change
                cash += pnl_change
        
        equity[i] = cash
    
    # Calculate max drawdown
    running_max = np.maximum.accumulate(equity)
    drawdown = equity - running_max
    max_dd = np.min(drawdown)
    
    return {
        "pnl": pnl,
        "equity_curve": equity,
        "trades": trades,
        "commission_cost": commission_cost,
        "max_dd": max_dd,
    }


def run_hero_backtest():
    """Execute the hero backtest scenario."""
    # Setup paths
    repo_root = Path(__file__).parent.parent.parent
    data_file = repo_root / "data" / "hero" / "btc_1h.csv"
    results_dir = repo_root / "results" / "hero"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("HERO SCENARIO: Backtest Execution")
    print("=" * 60)
    print()
    
    # Load data
    print(f"Loading data from: {data_file}")
    if not data_file.exists():
        print("ERROR: Data file not found. Run 01_prepare_data.py first.")
        return
    
    df = pd.read_csv(data_file)
    prices = df['close'].values
    
    print(f"  Data points: {len(prices)}")
    print(f"  Price range: ${prices.min():.2f} to ${prices.max():.2f}")
    print()
    
    # Configuration
    initial_capital = 100_000.0
    fee = 0.001  # 0.1% transaction fee (realistic for crypto)
    window = 24  # 24-hour momentum
    
    print("Configuration:")
    print(f"  Initial capital: ${initial_capital:,.2f}")
    print(f"  Transaction fee: {fee * 100:.2f}%")
    print(f"  Strategy: Simple Momentum (24h lookback)")
    print()
    
    # Run backtest
    print("Running backtest...")
    result = simple_momentum_backtest(prices, window=window, fee=fee, initial_capital=initial_capital)
    
    print("✓ Backtest complete")
    print()
    
    # Calculate metrics
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    pnl = result["pnl"]
    pnl_pct = (pnl / initial_capital) * 100
    max_dd = result["max_dd"]
    max_dd_pct = (max_dd / initial_capital) * 100
    trades = result["trades"]
    
    # Calculate Sharpe ratio
    sharpe = None
    equity_curve = result["equity_curve"]
    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if len(returns) > 0 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(24 * 365)  # Annualized (hourly data)
    
    print(f"P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")
    print(f"Max Drawdown: ${abs(max_dd):,.2f} ({abs(max_dd_pct):.2f}%)")
    print(f"Number of Trades: {trades}")
    if sharpe is not None:
        print(f"Sharpe Ratio (annualized): {sharpe:.3f}")
    print(f"Commission Cost: ${result['commission_cost']:.2f}")
    print()
    
    # Save equity curve
    equity_df = pd.DataFrame({
        'timestamp': df['timestamp'],
        'equity': equity_curve
    })
    equity_file = results_dir / "equity_curve.csv"
    equity_df.to_csv(equity_file, index=False)
    print(f"✓ Equity curve saved to: {equity_file}")
    
    # Save metrics
    metrics = {
        "pnl": float(pnl),
        "pnl_pct": float(pnl_pct),
        "max_drawdown": float(max_dd),
        "max_drawdown_pct": float(max_dd_pct),
        "num_trades": int(trades),
        "sharpe_ratio": float(sharpe) if sharpe is not None else None,
        "initial_capital": float(initial_capital),
        "final_equity": float(initial_capital + pnl),
        "commission_cost": float(result["commission_cost"]),
    }
    
    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"✓ Metrics saved to: {metrics_file}")
    print()
    
    print("=" * 60)
    print("Hero backtest complete!")
    print("=" * 60)
    
    return metrics


if __name__ == "__main__":
    run_hero_backtest()
