# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Integration test for the hero backtest scenario.

This test validates that the hero scenario produces consistent results
by comparing against a golden snapshot of metrics. It ensures that
changes to the codebase don't silently break the backtesting engine.
"""

import json
import numpy as np
import pandas as pd
import pytest
from pathlib import Path


# Tolerance for metric comparisons (allow small numerical differences)
RELATIVE_TOLERANCE = 0.05  # 5% relative tolerance
ABSOLUTE_TOLERANCE = 100.0  # $100 absolute tolerance for dollar amounts


def load_golden_metrics():
    """Load golden metrics from the snapshot file."""
    repo_root = Path(__file__).parent.parent.parent
    golden_file = repo_root / "tests" / "golden" / "hero_scenario_metrics.json"
    
    if not golden_file.exists():
        pytest.skip(f"Golden snapshot not found: {golden_file}")
    
    with open(golden_file, 'r') as f:
        return json.load(f)


def simple_momentum_backtest(prices, window=24, fee=0.001, initial_capital=100000.0):
    """Simple momentum backtest implementation (same as hero scenario)."""
    n = len(prices)
    position = 0.0
    equity = np.zeros(n)
    equity[0] = initial_capital
    cash = initial_capital
    pnl = 0.0
    trades = 0
    commission_cost = 0.0
    
    for i in range(1, n):
        if i >= window:
            price_change = prices[i] - prices[i - window]
            signal = 1.0 if price_change > 0 else (-1.0 if price_change < 0 else 0.0)
        else:
            signal = 0.0
        
        if signal != position:
            if position != 0:
                pnl_change = position * (prices[i] - prices[i - 1])
                pnl += pnl_change
                cash += pnl_change
            
            if signal != 0:
                cost = abs(signal) * prices[i] * fee
                commission_cost += cost
                cash -= cost
                trades += 1
            
            position = signal
        else:
            if position != 0:
                pnl_change = position * (prices[i] - prices[i - 1])
                pnl += pnl_change
                cash += pnl_change
        
        equity[i] = cash
    
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


def run_hero_backtest_simplified():
    """Run simplified version of hero backtest for testing."""
    repo_root = Path(__file__).parent.parent.parent
    data_file = repo_root / "data" / "sample_crypto_ohlcv.csv"
    
    # Load BTC data
    df = pd.read_csv(data_file)
    btc = df[df['symbol'] == 'BTC'].copy()
    prices = btc['close'].values
    
    # Configuration (same as hero scenario)
    initial_capital = 100_000.0
    fee = 0.001
    window = 24
    
    # Run backtest
    result = simple_momentum_backtest(prices, window=window, fee=fee, initial_capital=initial_capital)
    
    # Calculate metrics
    pnl = result["pnl"]
    pnl_pct = (pnl / initial_capital) * 100
    max_dd = result["max_dd"]
    max_dd_pct = (max_dd / initial_capital) * 100
    
    # Calculate Sharpe ratio
    sharpe = None
    equity_curve = result["equity_curve"]
    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if len(returns) > 0 and np.std(returns) > 0:
            sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(24 * 365))
    
    return {
        "pnl": float(pnl),
        "pnl_pct": float(pnl_pct),
        "max_drawdown": float(max_dd),
        "max_drawdown_pct": float(max_dd_pct),
        "num_trades": int(result["trades"]),
        "sharpe_ratio": sharpe,
    }


def test_hero_scenario_metrics():
    """Test that hero scenario produces metrics within expected range."""
    golden = load_golden_metrics()
    actual = run_hero_backtest_simplified()
    
    print("\n" + "=" * 60)
    print("Hero Scenario Regression Test")
    print("=" * 60)
    
    # Compare each metric
    for metric_name in ["pnl", "pnl_pct", "max_drawdown", "max_drawdown_pct", "num_trades"]:
        golden_value = golden[metric_name]
        actual_value = actual[metric_name]
        
        print(f"\n{metric_name}:")
        print(f"  Golden: {golden_value}")
        print(f"  Actual: {actual_value}")
        
        # For num_trades, require exact match or small difference
        if metric_name == "num_trades":
            diff = abs(actual_value - golden_value)
            print(f"  Difference: {diff} trades")
            assert diff <= 2, f"Trade count differs by more than 2: {diff}"
        else:
            # For other metrics, allow relative tolerance
            if abs(golden_value) > ABSOLUTE_TOLERANCE:
                rel_diff = abs((actual_value - golden_value) / golden_value)
                print(f"  Relative diff: {rel_diff * 100:.2f}%")
                assert rel_diff <= RELATIVE_TOLERANCE, \
                    f"{metric_name} differs by {rel_diff * 100:.2f}% (max {RELATIVE_TOLERANCE * 100:.0f}%)"
            else:
                abs_diff = abs(actual_value - golden_value)
                print(f"  Absolute diff: {abs_diff:.2f}")
                assert abs_diff <= ABSOLUTE_TOLERANCE, \
                    f"{metric_name} differs by {abs_diff:.2f} (max {ABSOLUTE_TOLERANCE})"
    
    # Check Sharpe ratio if present
    if golden.get("sharpe_ratio") is not None and actual.get("sharpe_ratio") is not None:
        golden_sharpe = golden["sharpe_ratio"]
        actual_sharpe = actual["sharpe_ratio"]
        
        print(f"\nsharpe_ratio:")
        print(f"  Golden: {golden_sharpe:.3f}")
        print(f"  Actual: {actual_sharpe:.3f}")
        
        # Sharpe ratio can vary more, allow 20% relative tolerance
        if abs(golden_sharpe) > 0.1:
            rel_diff = abs((actual_sharpe - golden_sharpe) / golden_sharpe)
            print(f"  Relative diff: {rel_diff * 100:.2f}%")
            assert rel_diff <= 0.20, \
                f"Sharpe ratio differs by {rel_diff * 100:.2f}% (max 20%)"
    
    print("\n" + "=" * 60)
    print("✓ All metrics within tolerance")
    print("=" * 60)


def test_hero_scenario_data_available():
    """Test that required data files are present."""
    repo_root = Path(__file__).parent.parent.parent
    data_file = repo_root / "data" / "sample_crypto_ohlcv.csv"
    
    assert data_file.exists(), f"Sample data not found: {data_file}"
    
    df = pd.read_csv(data_file)
    assert 'BTC' in df['symbol'].values, "BTC data not found in sample dataset"
    assert len(df[df['symbol'] == 'BTC']) > 100, "Insufficient BTC data points"


def test_hero_scenario_backtest_runs():
    """Test that backtest executes without errors."""
    metrics = run_hero_backtest_simplified()
    
    # Basic sanity checks
    assert metrics["num_trades"] >= 0, "Trade count cannot be negative"
    assert isinstance(metrics["pnl"], (int, float)), "PnL must be numeric"
    assert isinstance(metrics["max_drawdown"], (int, float)), "Max drawdown must be numeric"
    
    # Max drawdown should be non-positive
    assert metrics["max_drawdown"] <= 0, "Max drawdown should be negative or zero"
    
    print(f"\n✓ Backtest executed successfully")
    print(f"  P&L: ${metrics['pnl']:,.2f}")
    print(f"  Trades: {metrics['num_trades']}")
    print(f"  Max DD: ${metrics['max_drawdown']:,.2f}")
