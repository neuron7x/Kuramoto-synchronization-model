#!/usr/bin/env python3
"""Golden Path Backtest — TradePulse's reproducible minimal demo.

This script provides a guaranteed-to-work backtest scenario that:
1. Generates synthetic market data (no external dependencies)
2. Runs a simple momentum strategy backtest
3. Outputs PnL metrics and an equity curve plot

STATUS: Research Beta (guaranteed to work as of 2025-01-01)

USAGE:
    # From repository root, after installation:
    PYTHONPATH=. python scripts/golden_path_backtest.py

    # Or via make:
    make golden-path

REQUIREMENTS:
    - Python 3.11+
    - Core dependencies installed (see requirements.txt)

OUTPUT:
    - reports/golden_path/pnl.csv — Equity curve data
    - reports/golden_path/metrics.json — Performance metrics
    - reports/golden_path/plot.png — Equity curve visualization (if matplotlib available)

This is the "golden core" of TradePulse — the simplest reproducible path from
install to result. All other complex features (live trading, GPU, etc.) are
marked as experimental/lab.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure we can import from the repository root
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from backtest.event_driven import EventDrivenBacktestEngine  # noqa: E402


def generate_synthetic_data(
    n_bars: int = 1000,
    seed: int = 42,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Generate reproducible synthetic price data.

    Creates a price series with realistic characteristics:
    - Random walk with drift
    - Mean-reverting regime
    - Trending regime

    Args:
        n_bars: Number of price bars to generate
        seed: Random seed for reproducibility

    Returns:
        Tuple of (prices array, bars DataFrame with close/volume)
    """
    rng = np.random.default_rng(seed)

    # Phase 1: Random walk (first third)
    phase1_len = n_bars // 3
    phase1 = np.cumsum(rng.normal(0, 0.5, phase1_len))

    # Phase 2: Trending up (second third)
    phase2_len = n_bars // 3
    phase2 = phase1[-1] + 0.03 * np.arange(phase2_len) + rng.normal(0, 0.3, phase2_len)

    # Phase 3: Mean reversion (remaining)
    phase3_len = n_bars - 2 * (n_bars // 3)
    phase3 = phase2[-1] + np.cumsum(rng.normal(0, 0.4, phase3_len))

    # Combine and normalize to realistic price range
    raw_prices = np.concatenate([phase1, phase2, phase3])
    prices = 100 + raw_prices  # Base price of 100

    # Ensure prices are positive
    prices = np.maximum(prices, 1.0)

    # Create DataFrame with datetime index
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="1h")
    volume = rng.lognormal(10, 0.5, n_bars)

    bars = pd.DataFrame({"close": prices, "volume": volume}, index=idx)

    return prices, bars


def simple_momentum_signal(prices: np.ndarray, window: int = 20) -> np.ndarray:
    """Simple momentum strategy signal function.

    Generates signals based on price momentum:
    - +1 (long) when price is above moving average
    - -1 (short) when price is below moving average
    - 0 during warmup period

    Args:
        prices: Array of prices
        window: Lookback window for moving average

    Returns:
        Array of signals in [-1, 0, 1]
    """
    n = len(prices)
    signals = np.zeros(n)

    for i in range(window, n):
        ma = np.mean(prices[i - window : i])
        if prices[i] > ma * 1.01:  # 1% above MA = long
            signals[i] = 1.0
        elif prices[i] < ma * 0.99:  # 1% below MA = short
            signals[i] = -1.0
        # else: signals[i] = 0.0 (neutral)

    return signals


def save_results(
    output_dir: Path,
    result: object,
    prices: np.ndarray,
    bars: pd.DataFrame,
) -> dict:
    """Save backtest results to files.

    Args:
        output_dir: Directory for output files
        result: Backtest result object
        prices: Original price array
        bars: Original bars DataFrame

    Returns:
        Dictionary of metrics
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract metrics
    pnl = getattr(result, "pnl", 0.0)
    max_dd = getattr(result, "max_dd", 0.0)
    trades = getattr(result, "trades", 0)
    equity_curve = getattr(result, "equity_curve", np.array([]))

    # Performance metrics if available
    performance = getattr(result, "performance", None)
    sharpe = getattr(performance, "sharpe_ratio", 0.0) if performance else 0.0
    total_return_pct = (
        getattr(performance, "total_return", 0.0) * 100 if performance else 0.0
    )

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "pnl": float(pnl),
        "max_drawdown": float(max_dd),
        "trades": int(trades),
        "sharpe_ratio": float(sharpe),
        "total_return_pct": float(total_return_pct),
        "n_bars": len(prices),
        "initial_capital": 100000.0,
        "status": "success",
    }

    # Save metrics JSON
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"📊 Metrics saved: {metrics_path}")

    # Save equity curve CSV
    pnl_path = output_dir / "pnl.csv"
    if len(equity_curve) > 0:
        equity_df = pd.DataFrame(
            {
                "step": range(len(equity_curve)),
                "equity": equity_curve,
            }
        )
        equity_df.to_csv(pnl_path, index=False)
    else:
        # Fallback: save prices
        pd.DataFrame({"close": prices}).to_csv(pnl_path, index=False)
    print(f"📈 PnL data saved: {pnl_path}")

    # Try to generate plot
    try:
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 1, figsize=(12, 8))

        # Price chart
        axes[0].plot(bars.index, bars["close"], label="Price", color="blue", alpha=0.8)
        axes[0].set_title("Price History")
        axes[0].set_ylabel("Price")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Equity curve
        if len(equity_curve) > 0:
            axes[1].plot(equity_curve, label="Equity", color="green", alpha=0.8)
            axes[1].axhline(
                y=100000, color="gray", linestyle="--", label="Initial Capital"
            )
            axes[1].set_title(
                f"Equity Curve (PnL: ${pnl:,.2f}, Max DD: {max_dd:.2%})"
            )
            axes[1].set_ylabel("Equity ($)")
            axes[1].set_xlabel("Step")
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = output_dir / "plot.png"
        plt.savefig(plot_path, dpi=100)
        plt.close()
        print(f"📉 Plot saved: {plot_path}")
    except ImportError:
        print("⚠️  matplotlib not available, skipping plot generation")
    except Exception as e:
        print(f"⚠️  Could not generate plot: {e}")

    return metrics


def main() -> int:
    """Run the Golden Path backtest demo.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 60)
    print("🌟 TradePulse Golden Path Backtest")
    print("=" * 60)
    print()
    print("Status: Research Beta")
    print("This is the guaranteed reproducible demo scenario.")
    print()

    # Configuration
    n_bars = 1000
    initial_capital = 100_000.0
    seed = 42

    output_dir = REPO_ROOT / "reports" / "golden_path"

    try:
        # Step 1: Generate data
        print("📥 Step 1: Generating synthetic market data...")
        prices, bars = generate_synthetic_data(n_bars=n_bars, seed=seed)
        print(f"   Generated {len(prices)} price bars")
        print(f"   Price range: ${prices.min():.2f} - ${prices.max():.2f}")
        print()

        # Step 2: Run backtest
        print("⚙️  Step 2: Running backtest...")
        engine = EventDrivenBacktestEngine()
        result = engine.run(
            prices,
            simple_momentum_signal,
            initial_capital=initial_capital,
            strategy_name="golden_path_momentum",
        )
        print("   Backtest completed successfully")
        print()

        # Step 3: Display results
        print("📊 Step 3: Results")
        print("-" * 40)

        pnl = getattr(result, "pnl", 0.0)
        max_dd = getattr(result, "max_dd", 0.0)
        trades = getattr(result, "trades", 0)
        performance = getattr(result, "performance", None)
        sharpe = getattr(performance, "sharpe_ratio", None) if performance else None

        print(f"   PnL:           ${pnl:,.2f}")
        print(f"   Max Drawdown:  {max_dd:.2%}")
        print(f"   Total Trades:  {trades}")
        if sharpe is not None:
            print(f"   Sharpe Ratio:  {sharpe:.3f}")
        print()

        # Step 4: Save outputs
        print("💾 Step 4: Saving outputs...")
        metrics = save_results(output_dir, result, prices, bars)
        print()

        # Summary
        print("=" * 60)
        print("✅ Golden Path backtest completed successfully!")
        print()
        print("Output files:")
        print(f"   - {output_dir / 'metrics.json'}")
        print(f"   - {output_dir / 'pnl.csv'}")
        if (output_dir / "plot.png").exists():
            print(f"   - {output_dir / 'plot.png'}")
        print()
        print("Next steps:")
        print("   1. Review the metrics in metrics.json")
        print("   2. Analyze the equity curve in pnl.csv")
        print("   3. View the plot in plot.png")
        print("   4. Modify the strategy in this script to experiment")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
