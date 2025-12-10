#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""CLI commands for the TradePulse hero backtest scenario.

This module provides a simple command-line interface for running the hero scenario
backtest, which demonstrates TradePulse's capabilities in a reproducible, fast,
and realistic way.

Usage:
    tradepulse hero-scenario run
    tradepulse hero-scenario plot
    tradepulse hero-scenario all
"""

import importlib.util
import sys
from pathlib import Path

import click


def _load_module(module_name: str, file_path: Path):
    """Load a Python module dynamically from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@click.group(name="hero-scenario")
def hero_scenario():
    """Run the TradePulse hero backtest scenario."""
    pass


@hero_scenario.command()
@click.option(
    "--data-source",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to source OHLCV data (default: data/sample_crypto_ohlcv.csv)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to save results (default: results/hero)",
)
@click.option(
    "--capital",
    type=float,
    default=100_000.0,
    help="Initial capital (default: 100000)",
)
def run(data_source, output_dir, capital):
    """Run the complete hero scenario (prepare data + backtest)."""
    # Add repo root to path
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))

    # Import after path is set
    from examples.hero_scenario import prepare_data_module, run_backtest_module

    click.echo("=" * 70)
    click.echo("TradePulse Hero Scenario")
    click.echo("=" * 70)

    # Set defaults
    if data_source is None:
        data_source = repo_root / "data" / "sample_crypto_ohlcv.csv"
    data_path = repo_root / "data" / "hero" / "btc_1h.csv"
    if output_dir is None:
        output_dir = repo_root / "results" / "hero"

    # Step 1: Prepare data
    click.echo("\n[1/2] Preparing data...")
    try:
        prepare_module = _load_module(
            "prepare_data",
            repo_root / "examples" / "hero_scenario" / "01_prepare_data.py"
        )
        prepare_module.prepare_hero_data(data_source, data_path, "BTC")
    except Exception as e:
        click.echo(f"✗ Data preparation failed: {e}", err=True)
        sys.exit(1)

    # Step 2: Run backtest
    click.echo("\n[2/2] Running backtest...")
    try:
        backtest_module = _load_module(
            "run_backtest",
            repo_root / "examples" / "hero_scenario" / "02_run_backtest.py"
        )
        backtest_module.run_hero_backtest(data_path, output_dir, capital)
    except Exception as e:
        click.echo(f"✗ Backtest failed: {e}", err=True)
        sys.exit(1)

    click.echo("\n" + "=" * 70)
    click.echo("✓ Hero scenario complete!")
    click.echo(f"✓ Results saved to {output_dir}")
    click.echo("\nNext steps:")
    click.echo("  - View results: cat results/hero/metrics.json")
    click.echo("  - Plot equity curve: tradepulse hero-scenario plot")
    click.echo("=" * 70)


@hero_scenario.command()
@click.option(
    "--results-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory containing results (default: results/hero)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to save plot (default: results/hero/equity_curve.png)",
)
def plot(results_dir, output):
    """Generate equity curve plot from hero scenario results."""
    # Add repo root to path
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))

    if results_dir is None:
        results_dir = repo_root / "results" / "hero"

    if not results_dir.exists():
        click.echo(
            f"✗ Results directory not found: {results_dir}\n"
            f"  Run: tradepulse hero-scenario run",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Generating equity curve plot from {results_dir}...")

    try:
        plot_module = _load_module(
            "plot_equity",
            repo_root / "examples" / "hero_scenario" / "03_plot_equity.py"
        )
        plot_module.plot_equity_curve(results_dir, output)
    except Exception as e:
        click.echo(f"✗ Plotting failed: {e}", err=True)
        sys.exit(1)

    click.echo("✓ Plot generated successfully!")


@hero_scenario.command()
@click.option(
    "--data-source",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to source OHLCV data (default: data/sample_crypto_ohlcv.csv)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to save results (default: results/hero)",
)
@click.option(
    "--capital",
    type=float,
    default=100_000.0,
    help="Initial capital (default: 100000)",
)
def all(data_source, output_dir, capital):
    """Run complete hero scenario: data prep, backtest, and plotting."""
    from click.testing import CliRunner

    runner = CliRunner()

    # Run data prep + backtest
    result = runner.invoke(
        run,
        args=[
            f"--capital={capital}",
        ]
        + (["--data-source", str(data_source)] if data_source else [])
        + (["--output-dir", str(output_dir)] if output_dir else []),
        catch_exceptions=False,
    )

    if result.exit_code != 0:
        sys.exit(result.exit_code)

    # Run plotting
    result = runner.invoke(
        plot,
        args=(["--results-dir", str(output_dir)] if output_dir else []),
        catch_exceptions=False,
    )

    if result.exit_code != 0:
        sys.exit(result.exit_code)

    click.echo("\n✓ Complete hero scenario finished (data, backtest, plot)!")


def main():
    """Main entry point for CLI."""
    hero_scenario()


if __name__ == "__main__":
    main()
