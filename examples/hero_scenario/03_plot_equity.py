#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Plot equity curve for the hero backtest scenario.

This script generates a visual representation of the backtest results,
including the equity curve and basic statistics.
"""

import json
import pandas as pd
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


def plot_equity_curve():
    """Generate equity curve plot from backtest results."""
    # Setup paths
    repo_root = Path(__file__).parent.parent.parent
    results_dir = repo_root / "results" / "hero"
    equity_file = results_dir / "equity_curve.csv"
    metrics_file = results_dir / "metrics.json"
    output_file = results_dir / "equity_curve.png"
    
    print("=" * 60)
    print("HERO SCENARIO: Equity Curve Plot")
    print("=" * 60)
    print()
    
    # Check files exist
    if not equity_file.exists():
        print("ERROR: equity_curve.csv not found. Run 02_run_backtest.py first.")
        return
    
    if not MATPLOTLIB_AVAILABLE:
        print("ERROR: matplotlib not installed. Cannot generate plot.")
        print("Install with: pip install matplotlib")
        return
    
    # Load data
    print(f"Loading equity curve from: {equity_file}")
    df = pd.read_csv(equity_file)
    
    print(f"Loading metrics from: {metrics_file}")
    with open(metrics_file, 'r') as f:
        metrics = json.load(f)
    
    print()
    
    # Create plot
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(df.index, df['equity'], linewidth=2, color='#2E86AB', label='Equity')
    ax.axhline(y=metrics['initial_capital'], color='gray', linestyle='--', 
               linewidth=1, alpha=0.7, label='Initial Capital')
    
    ax.set_xlabel('Time (hours)', fontsize=12)
    ax.set_ylabel('Equity ($)', fontsize=12)
    ax.set_title('Hero Scenario: BTC/USD Backtest Equity Curve', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best')
    
    # Add metrics text box
    textstr = '\n'.join([
        f"P&L: ${metrics['pnl']:,.2f} ({metrics['pnl_pct']:+.2f}%)",
        f"Max DD: ${abs(metrics['max_drawdown']):,.2f} ({abs(metrics['max_drawdown_pct']):.2f}%)",
        f"Trades: {metrics['num_trades']}",
        f"Sharpe: {metrics['sharpe_ratio']:.3f}" if metrics['sharpe_ratio'] else "Sharpe: N/A"
    ])
    
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=props, family='monospace')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    
    print(f"✓ Plot saved to: {output_file}")
    print(f"  Size: {output_file.stat().st_size / 1024:.1f} KB")
    print()
    
    print("=" * 60)
    print("Plot generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    plot_equity_curve()
