# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Risk Guardian CLI — command-line interface for risk-controlled trading simulation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd

from .config import RiskGuardianConfig
from .engine import RiskGuardian


def _default_signal_fn(prices: np.ndarray) -> np.ndarray:
    """Default momentum-based signal function for demonstration.

    Uses simple momentum: buy when price > SMA, sell when price < SMA.
    """
    window = min(20, len(prices) // 4) if len(prices) > 4 else 1
    if window < 1:
        window = 1

    signals = np.zeros_like(prices)

    for i in range(window, len(prices)):
        sma = np.mean(prices[i - window : i])
        if prices[i] > sma * 1.01:  # 1% above SMA
            signals[i] = 1.0  # Long
        elif prices[i] < sma * 0.99:  # 1% below SMA
            signals[i] = -1.0  # Short
        else:
            signals[i] = signals[i - 1]  # Hold previous

    return signals


@click.group()
@click.version_option(version="1.0.0", prog_name="Risk Guardian")
def cli() -> None:
    """TradePulse Risk Guardian — Automated risk control for trading.

    Risk Guardian limits maximum drawdown and daily losses by:

    \b
    - Activating kill-switch at critical drawdown levels
    - Entering safe-mode at warning levels (reduced position sizes)
    - Blocking new trades when daily loss limit is reached

    Run simulations on historical data to see how much capital Risk Guardian
    would have saved.

    \b
    Examples:
        tp-risk-guardian simulate --csv=sample.csv --price-col=close
        tp-risk-guardian simulate --csv=trades.csv --max-drawdown=10 --daily-limit=5
        tp-risk-guardian report --csv=sample.csv --output=report.json
    """
    pass


@cli.command()
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
    "--signal-col",
    default=None,
    help="Column name containing signals (-1 to 1). If not provided, uses default momentum strategy.",
)
@click.option(
    "--timestamp-col",
    default=None,
    help="Column name containing timestamps. If not provided, uses index.",
)
@click.option(
    "--initial-capital",
    type=float,
    default=100_000,
    show_default=True,
    help="Starting capital for simulation.",
)
@click.option(
    "--daily-limit",
    type=float,
    default=5.0,
    show_default=True,
    help="Maximum daily loss percentage.",
)
@click.option(
    "--max-drawdown",
    type=float,
    default=10.0,
    show_default=True,
    help="Kill-switch trigger level (percentage).",
)
@click.option(
    "--safe-threshold",
    type=float,
    default=7.0,
    show_default=True,
    help="Safe-mode trigger level (percentage).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to YAML configuration file (overrides other options).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to save JSON report (optional).",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Only output JSON, suppress summary text.",
)
def simulate(
    csv_path: Path,
    price_col: str,
    signal_col: str | None,
    timestamp_col: str | None,
    initial_capital: float,
    daily_limit: float,
    max_drawdown: float,
    safe_threshold: float,
    config_path: Path | None,
    output_path: Path | None,
    quiet: bool,
) -> None:
    """Run a Risk Guardian simulation on historical price data.

    Compares trading with and without risk controls, showing how much
    capital would have been saved.

    \b
    Example:
        tp-risk-guardian simulate --csv=sample.csv --max-drawdown=10

    \b
    Output includes:
        - Baseline vs Protected PnL
        - Max Drawdown comparison
        - Sharpe Ratio improvement
        - Capital saved by risk controls
        - Number of kill-switch activations
    """
    # Load configuration
    if config_path is not None:
        try:
            config = RiskGuardianConfig.from_yaml(config_path)
        except Exception as e:
            click.echo(f"Error loading config: {e}", err=True)
            sys.exit(1)
    else:
        config = RiskGuardianConfig(
            initial_capital=initial_capital,
            daily_loss_limit_pct=daily_limit,
            max_drawdown_pct=max_drawdown,
            safe_mode_threshold_pct=safe_threshold,
        )

    # Load data
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        click.echo(f"Error reading CSV: {e}", err=True)
        sys.exit(1)

    if price_col not in df.columns:
        click.echo(f"Error: Price column '{price_col}' not found in CSV", err=True)
        click.echo(f"Available columns: {list(df.columns)}", err=True)
        sys.exit(1)

    # Determine signal function
    signal_fn = None
    if signal_col is None:
        signal_fn = _default_signal_fn

    # Run simulation
    guardian = RiskGuardian(config)

    try:
        result = guardian.simulate_from_dataframe(
            df,
            price_col=price_col,
            signal_col=signal_col,
            signal_fn=signal_fn,
            timestamp_col=timestamp_col,
        )
    except Exception as e:
        click.echo(f"Error during simulation: {e}", err=True)
        sys.exit(1)

    # Output results
    if not quiet:
        click.echo(result.summary())

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        if not quiet:
            click.echo(f"\nReport saved to: {output_path}")

    if quiet:
        click.echo(json.dumps(result.to_dict(), indent=2))


@cli.command()
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
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default="risk_guardian_report.md",
    show_default=True,
    help="Path to save markdown report.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to YAML configuration file.",
)
def report(
    csv_path: Path,
    price_col: str,
    output_path: Path,
    config_path: Path | None,
) -> None:
    """Generate a detailed markdown report for Risk Guardian analysis.

    Creates a comprehensive report suitable for documentation, README files,
    or investor presentations.

    \b
    Example:
        tp-risk-guardian report --csv=sample.csv --output=report.md
    """
    # Load configuration
    if config_path is not None:
        config = RiskGuardianConfig.from_yaml(config_path)
    else:
        config = RiskGuardianConfig()

    # Load data
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        click.echo(f"Error reading CSV: {e}", err=True)
        sys.exit(1)

    if price_col not in df.columns:
        click.echo(f"Error: Price column '{price_col}' not found", err=True)
        sys.exit(1)

    # Run simulation
    guardian = RiskGuardian(config)
    result = guardian.simulate_from_dataframe(
        df,
        price_col=price_col,
        signal_fn=_default_signal_fn,
    )

    # Generate markdown report
    md_lines = [
        "# Risk Guardian Analysis Report",
        "",
        f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Data Source:** `{csv_path.name}`",
        f"**Periods Analyzed:** {result.total_periods:,}",
        "",
        "## Configuration",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Initial Capital | ${config.initial_capital:,.0f} |",
        f"| Daily Loss Limit | {config.daily_loss_limit_pct}% |",
        f"| Max Drawdown (Kill-Switch) | {config.max_drawdown_pct}% |",
        f"| Safe Mode Threshold | {config.safe_mode_threshold_pct}% |",
        f"| Safe Mode Position Size | {config.safe_mode_position_multiplier * 100}% |",
        "",
        "## Results Comparison",
        "",
        "### Baseline (No Risk Control)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Return | {result.baseline_pnl / config.initial_capital * 100:+.2f}% |",
        f"| Max Drawdown | {result.baseline_max_drawdown * 100:.2f}% |",
        f"| Sharpe Ratio | {result.baseline_sharpe:.2f} |",
        f"| Worst Day | {result.baseline_worst_day * 100:.2f}% |",
        "",
        "### With Risk Guardian",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Return | {result.protected_pnl / config.initial_capital * 100:+.2f}% |",
        f"| Max Drawdown | {result.protected_max_drawdown * 100:.2f}% |",
        f"| Sharpe Ratio | {result.protected_sharpe:.2f} |",
        f"| Worst Day | {result.protected_worst_day * 100:.2f}% |",
        "",
        "### Risk Events",
        "",
        "| Event | Count |",
        "|-------|-------|",
        f"| Kill-Switch Activations | {result.kill_switch_activations} |",
        f"| Safe Mode Periods | {result.safe_mode_periods} |",
        f"| Blocked Trades | {result.blocked_trades} |",
        "",
        "## Value Delivered",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Saved Capital** | **${result.saved_capital:,.2f}** ({result.saved_capital_pct:.1f}%) |",
        f"| Sharpe Improvement | {result.sharpe_improvement:+.0f}% |",
        f"| Drawdown Reduction | {result.drawdown_reduction:.0f}% |",
        "",
        "## Interpretation",
        "",
        f"Risk Guardian protected against {result.drawdown_reduction:.0f}% of the maximum drawdown.",
        f"The kill-switch was activated {result.kill_switch_activations} time(s) to prevent catastrophic losses.",
        "",
        "---",
        "",
        "*Generated by TradePulse Risk Guardian*",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    click.echo(f"Report saved to: {output_path}")


@cli.command("generate-config")
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default="risk_guardian_config.yaml",
    show_default=True,
    help="Path to save the configuration template.",
)
def generate_config(output_path: Path) -> None:
    """Generate a sample YAML configuration file.

    Creates a configuration template with default values that you can customize.

    \b
    Example:
        tp-risk-guardian generate-config --output=my_config.yaml
    """
    config_template = """# Risk Guardian Configuration
# TradePulse Risk Management Settings

risk_guardian:
  # Starting capital for simulation
  initial_capital: 100000.0

  # Maximum allowed daily loss as percentage
  # Trading halts when this limit is reached
  daily_loss_limit_pct: 5.0

  # Kill-switch trigger level (percentage drawdown)
  # All trading stops when drawdown reaches this level
  max_drawdown_pct: 10.0

  # Safe-mode trigger level (percentage drawdown)
  # Position sizes are reduced when drawdown reaches this level
  safe_mode_threshold_pct: 7.0

  # Position size multiplier when in safe-mode
  # 0.5 = positions are reduced to 50% of normal size
  safe_mode_position_multiplier: 0.5

  # Maximum position size as percentage of equity
  max_position_pct: 20.0

  # Enable/disable risk control features
  enable_kill_switch: true
  enable_safe_mode: true
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(config_template, encoding="utf-8")
    click.echo(f"Configuration template saved to: {output_path}")


def main() -> None:
    """Entry point for Risk Guardian CLI."""
    cli()


if __name__ == "__main__":
    main()
