#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Plot equity curve from hero backtest results.

This script generates a publication-quality equity curve plot from the
hero scenario backtest results, showing portfolio value over time with
key statistics annotated.

Usage:
    python examples/hero_scenario/03_plot_equity.py
    python examples/hero_scenario/03_plot_equity.py --results results/hero
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_equity_curve(
    results_dir: Path,
    output_path: Path | None = None,
) -> None:
    """Plot equity curve from backtest results.

    Args:
        results_dir: Directory containing backtest results.
        output_path: Path to save plot (default: results_dir/equity_curve.png).
    """
    # Load data
    equity_path = results_dir / "equity_curve.csv"
    metrics_path = results_dir / "metrics.json"

    if not equity_path.exists():
        raise FileNotFoundError(
            f"Equity curve not found: {equity_path}\n"
            f"Run: python examples/hero_scenario/02_run_backtest.py"
        )

    print(f"Loading results from {results_dir}...")
    equity_df = pd.read_csv(equity_path, parse_dates=["timestamp"])

    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    # Create plot
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot equity curve
    ax.plot(
        equity_df["timestamp"],
        equity_df["equity"],
        linewidth=2,
        color="#2E86AB",
        label="Portfolio Equity",
    )

    # Add initial capital reference line
    ax.axhline(
        y=metrics["initial_capital"],
        color="gray",
        linestyle="--",
        linewidth=1,
        alpha=0.5,
        label="Initial Capital",
    )

    # Formatting
    ax.set_xlabel("Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Portfolio Value ($)", fontsize=12, fontweight="bold")
    ax.set_title(
        "TradePulse Hero Scenario: NeuroTradePulseStrategy on BTCUSDT 1h",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    # Format y-axis as currency
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, p: f"${x:,.0f}")
    )

    # Rotate x-axis labels
    plt.xticks(rotation=45, ha="right")

    # Add grid
    ax.grid(True, alpha=0.3, linestyle=":", linewidth=0.5)

    # Add legend
    ax.legend(loc="best", framealpha=0.9)

    # Add statistics box
    # total_return_pct is already in percentage form (e.g., 0.80 for 0.80%)
    stats_text = (
        f"Initial: ${metrics['initial_capital']:,.0f}\n"
        f"Final: ${metrics['final_equity']:,.0f}\n"
        f"P&L: ${metrics['total_pnl']:,.2f}\n"
        f"Return: {metrics['total_return_pct']:.2f}%\n"
        f"Trades: {metrics['num_trades']}\n"
    )
    if metrics.get("sharpe_ratio") is not None:
        stats_text += f"Sharpe: {metrics['sharpe_ratio']:.3f}\n"
    if metrics.get("max_drawdown") is not None:
        stats_text += f"Max DD: {metrics['max_drawdown'] * 100:.2f}%\n"

    # Position stats box in upper left
    ax.text(
        0.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox=dict(
            boxstyle="round",
            facecolor="wheat",
            alpha=0.8,
            edgecolor="black",
            linewidth=1.5,
        ),
    )

    # Tight layout
    plt.tight_layout()

    # Save plot
    if output_path is None:
        output_path = results_dir / "equity_curve.png"

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"✓ Saved equity curve plot to {output_path}")

    # Also save as PDF for publications
    pdf_path = output_path.with_suffix(".pdf")
    plt.savefig(pdf_path, bbox_inches="tight")
    print(f"✓ Saved PDF version to {pdf_path}")

    plt.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plot equity curve from hero backtest results"
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results/hero"),
        help="Directory containing results (default: results/hero)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to save plot (default: results/hero/equity_curve.png)",
    )

    args = parser.parse_args()

    # Convert relative paths to absolute based on repo root
    repo_root = Path(__file__).parent.parent.parent
    results_dir = repo_root / args.results
    output_path = repo_root / args.output if args.output else None

    plot_equity_curve(results_dir, output_path)

    print("\nVisualization complete!")


if __name__ == "__main__":
    main()
