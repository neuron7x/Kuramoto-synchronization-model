#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Run the hero backtest scenario.

This script runs a complete backtest using the NeuroTradePulseStrategy on BTC 1h data,
computing all relevant performance metrics and saving results for analysis.

The backtest uses:
- Instrument: BTCUSDT (spot)
- Timeframe: 1 hour
- Strategy: NeuroTradePulseStrategy (combines Kuramoto-Ricci composite signals
  with fractal motivation for neuro-inspired trading decisions)
- Period: ~3 weeks of data from 2024-01-01
- Initial capital: $100,000

Usage:
    python examples/hero_scenario/02_run_backtest.py
    python examples/hero_scenario/02_run_backtest.py --data data/hero/btc_1h.csv
"""

import argparse
import json
import sys
from pathlib import Path

# Add repo root to path for module imports
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

import numpy as np
import pandas as pd

from backtest.event_driven import EventDrivenBacktestEngine
from strategies.neuro_trade_pulse import NeuroTradePulseStrategy


def run_hero_backtest(
    data_path: Path,
    results_dir: Path,
    initial_capital: float = 100_000.0,
) -> dict:
    """Run the hero backtest scenario.

    Args:
        data_path: Path to prepared OHLCV data.
        results_dir: Directory to save results.
        initial_capital: Initial capital for backtest.

    Returns:
        Dictionary with backtest results and metrics.
    """
    print("=" * 70)
    print("TradePulse Hero Backtest Scenario")
    print("=" * 70)

    # Load data
    print(f"\nLoading data from {data_path}...")
    df = pd.read_csv(data_path, parse_dates=["timestamp"], index_col="timestamp")

    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Total bars: {len(df)}")
    print(f"  Initial price: ${df['close'].iloc[0]:.2f}")
    print(f"  Final price: ${df['close'].iloc[-1]:.2f}")

    # Initialize strategy
    print("\nInitializing NeuroTradePulseStrategy...")
    strategy = NeuroTradePulseStrategy()

    # Generate signals
    print("Generating trading signals...")
    bars_for_strategy = df[["close", "volume"]].copy()
    signals = strategy.generate_signals(bars_for_strategy)
    actions = signals.to_numpy()

    print(f"  Total signals: {len(actions)}")
    print(f"  Long signals: {(actions > 0).sum()}")
    print(f"  Flat signals: {(actions == 0).sum()}")
    print(f"  Short signals: {(actions < 0).sum()}")

    # Prepare prices for backtest engine
    prices = df["close"].to_numpy()

    # Create strategy function wrapper
    def strategy_fn(price_series: np.ndarray) -> np.ndarray:
        """Strategy function that returns precomputed actions."""
        return actions[: price_series.size]

    # Run backtest
    print(f"\nRunning backtest with ${initial_capital:,.2f} initial capital...")
    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        strategy_fn,
        initial_capital=initial_capital,
        strategy_name="NeuroTradePulse_Hero",
    )

    # Extract metrics
    print("\n" + "=" * 70)
    print("Backtest Results")
    print("=" * 70)

    metrics = {
        "initial_capital": initial_capital,
        "final_equity": float(result.equity_curve[-1]) if result.equity_curve is not None else initial_capital,
        "total_pnl": float(result.pnl) if result.pnl is not None else 0.0,
        "total_return_pct": (float(result.equity_curve[-1]) / initial_capital - 1.0) * 100.0 if result.equity_curve is not None else 0.0,
        "num_trades": int(result.trades) if result.trades is not None else 0,
        "sharpe_ratio": float(result.performance.sharpe_ratio) if result.performance and result.performance.sharpe_ratio is not None else None,
        "sortino_ratio": float(result.performance.sortino_ratio) if result.performance and result.performance.sortino_ratio is not None else None,
        "max_drawdown": float(result.performance.max_drawdown) if result.performance and result.performance.max_drawdown is not None else None,
        "cagr": float(result.performance.cagr) if result.performance and result.performance.cagr is not None else None,
        "hit_ratio": float(result.performance.hit_ratio) if result.performance and result.performance.hit_ratio is not None else None,
        "num_bars": len(df),
        "start_date": str(df.index[0]),
        "end_date": str(df.index[-1]),
        "strategy": "NeuroTradePulseStrategy",
        "instrument": "BTCUSDT",
        "timeframe": "1h",
    }

    print(f"\nInitial Capital:    ${metrics['initial_capital']:>12,.2f}")
    print(f"Final Equity:       ${metrics['final_equity']:>12,.2f}")
    print(f"Total P&L:          ${metrics['total_pnl']:>12,.2f}")
    print(f"Total Return:       {metrics['total_return_pct']:>12.2f}%")
    print(f"Number of Trades:   {metrics['num_trades']:>12}")
    print(f"\nSharpe Ratio:       {metrics['sharpe_ratio']:>12.4f}" if metrics['sharpe_ratio'] is not None else "\nSharpe Ratio:       N/A")
    print(f"Sortino Ratio:      {metrics['sortino_ratio']:>12.4f}" if metrics['sortino_ratio'] is not None else "Sortino Ratio:      N/A")
    print(f"Max Drawdown:       {metrics['max_drawdown']:>12.2%}" if metrics['max_drawdown'] is not None else "Max Drawdown:       N/A")
    print(f"CAGR:               {metrics['cagr']:>12.2%}" if metrics['cagr'] is not None else "CAGR:               N/A")
    print(f"Hit Ratio:          {metrics['hit_ratio']:>12.2%}" if metrics['hit_ratio'] is not None else "Hit Ratio:          N/A")

    # Save results
    results_dir.mkdir(parents=True, exist_ok=True)

    # Save metrics JSON
    metrics_path = results_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n✓ Saved metrics to {metrics_path}")

    # Save equity curve
    if result.equity_curve is not None:
        equity_df = pd.DataFrame({
            "timestamp": df.index,
            "equity": result.equity_curve,
        })
        equity_path = results_dir / "equity_curve.csv"
        equity_df.to_csv(equity_path, index=False)
        print(f"✓ Saved equity curve to {equity_path}")

    # Save trades summary
    trades_summary = {
        "total_trades": metrics["num_trades"],
        "long_signals": int((actions > 0).sum()),
        "flat_signals": int((actions == 0).sum()),
        "short_signals": int((actions < 0).sum()),
    }
    trades_path = results_dir / "trades_summary.json"
    with open(trades_path, "w") as f:
        json.dump(trades_summary, f, indent=2)
    print(f"✓ Saved trades summary to {trades_path}")

    print("\n" + "=" * 70)
    print("Run visualization: python examples/hero_scenario/03_plot_equity.py")
    print("=" * 70)

    return metrics


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run hero backtest scenario"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/hero/btc_1h.csv"),
        help="Path to prepared data (default: data/hero/btc_1h.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/hero"),
        help="Directory to save results (default: results/hero)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100_000.0,
        help="Initial capital (default: 100000)",
    )

    args = parser.parse_args()

    # Convert relative paths to absolute based on repo root
    repo_root = Path(__file__).parent.parent.parent
    data_path = repo_root / args.data
    results_dir = repo_root / args.output

    if not data_path.exists():
        raise FileNotFoundError(
            f"Data not found: {data_path}\n"
            f"Run: python examples/hero_scenario/01_prepare_data.py"
        )

    run_hero_backtest(data_path, results_dir, args.capital)


if __name__ == "__main__":
    main()
