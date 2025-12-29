#!/usr/bin/env python3
"""Data Pipeline Demo: Generate, Validate, and Analyze OHLCV Data.

This example demonstrates the complete data pipeline workflow:
1. Generate synthetic multi-asset OHLCV data
2. Validate data quality
3. Perform basic market analysis
4. Export analysis results

This is a good starting point for understanding TradePulse's data handling
and validation capabilities.

Usage:
    python examples/data_pipeline_demo.py
    python examples/data_pipeline_demo.py --symbols BTC ETH --days 30
"""
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import data generation utilities
# Import validation utilities
from core.data.validation import validate_ohlcv  # noqa: E402

# Import analysis engine
from core.indicators.kuramoto_ricci_composite import (
    TradePulseCompositeEngine,
)  # noqa: E402
from core.utils.determinism import DEFAULT_SEED  # noqa: E402
from scripts.generate_sample_ohlcv import generate_multi_asset_data  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def generate_data(
    symbols: list[str], days: int, timeframe: str, seed: int
) -> pd.DataFrame:
    """Generate synthetic OHLCV data.

    Args:
        symbols: List of asset symbols to generate
        days: Number of days of data
        timeframe: Bar timeframe (1h, 1d, etc.)
        seed: Random seed for reproducibility

    Returns:
        DataFrame with generated OHLCV data
    """
    logger.info("Generating %d days of %s data for %s", days, timeframe, symbols)

    df = generate_multi_asset_data(
        symbols=symbols,
        days=days,
        timeframe=timeframe,
        seed=seed,
    )

    logger.info("Generated %d rows across %d symbols", len(df), len(symbols))
    return df


def validate_data(df: pd.DataFrame) -> bool:
    """Validate OHLCV data quality.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        True if validation passed, False otherwise
    """
    logger.info("Validating data quality...")

    all_valid = True
    for symbol in df["symbol"].unique():
        symbol_df = df[df["symbol"] == symbol].copy()
        result = validate_ohlcv(
            symbol_df,
            price_col="close",
            open_col="open",
            high_col="high",
            low_col="low",
            volume_col="volume",
        )

        if result.valid:
            logger.info("✅ %s: %s", symbol, result.summary())
        else:
            logger.error("❌ %s: %s", symbol, result.summary())
            for issue in result.issues:
                logger.error("   - %s", issue)
            all_valid = False

        for warning in result.warnings:
            logger.warning("   ⚠️ %s: %s", symbol, warning)

    return all_valid


def analyze_market(df: pd.DataFrame, symbol: str) -> dict:
    """Analyze market regime for a single asset.

    Args:
        df: DataFrame with OHLCV data
        symbol: Symbol to analyze

    Returns:
        Dictionary with analysis results
    """
    logger.info("Analyzing market regime for %s", symbol)

    # Filter to single symbol
    symbol_df = df[df["symbol"] == symbol].copy()

    # Set timestamp as index if available
    if "timestamp" in symbol_df.columns:
        symbol_df["timestamp"] = pd.to_datetime(symbol_df["timestamp"])
        symbol_df.set_index("timestamp", inplace=True)

    # Ensure we have enough data
    if len(symbol_df) < 200:
        logger.warning(
            "%s has only %d rows, may not have enough data for reliable analysis",
            symbol,
            len(symbol_df),
        )

    # Run analysis
    engine = TradePulseCompositeEngine()
    snapshot = engine.analyze_market(symbol_df)

    results = {
        "symbol": symbol,
        "rows": len(symbol_df),
        "phase": snapshot.phase.value,
        "confidence": float(snapshot.confidence),
        "entry_signal": float(snapshot.entry_signal),
        "price_range": {
            "min": float(symbol_df["close"].min()),
            "max": float(symbol_df["close"].max()),
            "mean": float(symbol_df["close"].mean()),
        },
        "returns": {
            "mean": float(symbol_df["close"].pct_change().mean()),
            "std": float(symbol_df["close"].pct_change().std()),
        },
    }

    logger.info(
        "  Phase: %s (confidence: %.2f%%)",
        results["phase"],
        results["confidence"] * 100,
    )

    return results


def display_results(results: list[dict]) -> None:
    """Display analysis results in a formatted table.

    Args:
        results: List of analysis result dictionaries
    """
    print("\n" + "=" * 70)
    print("MARKET ANALYSIS RESULTS")
    print("=" * 70)

    print(
        f"\n{'Symbol':<10} {'Phase':<15} {'Confidence':>12} {'Entry Signal':>14} {'Avg Price':>12}"
    )
    print("-" * 70)

    for r in results:
        print(
            f"{r['symbol']:<10} {r['phase']:<15} {r['confidence']:>12.1%} "
            f"{r['entry_signal']:>14.3f} {r['price_range']['mean']:>12,.2f}"
        )

    print("\n" + "-" * 70)
    print("\nPHASE DESCRIPTIONS:")
    print("  accumulation  - Market consolidating, potential bottom forming")
    print("  distribution  - Market distributing, potential top forming")
    print("  trending      - Strong directional movement")
    print("  transition    - Regime change in progress")
    print()


def save_results(df: pd.DataFrame, results: list[dict], output_dir: Path) -> None:
    """Save data and results to files.

    Args:
        df: Generated OHLCV data
        results: Analysis results
        output_dir: Directory for output files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save OHLCV data
    data_path = output_dir / "generated_ohlcv.csv"
    df.to_csv(data_path, index=False)
    logger.info("Saved OHLCV data to %s", data_path)

    # Save analysis results
    results_df = pd.DataFrame(results)
    results_path = output_dir / "analysis_results.csv"
    results_df.to_csv(results_path, index=False)
    logger.info("Saved analysis results to %s", results_path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Data Pipeline Demo: Generate, Validate, and Analyze OHLCV Data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use defaults (BTC, ETH, SOL for 7 days)
    python examples/data_pipeline_demo.py

    # Custom symbols and duration
    python examples/data_pipeline_demo.py --symbols BTC ETH --days 30

    # Different timeframe
    python examples/data_pipeline_demo.py --timeframe 4h --days 14

    # Save results to custom directory
    python examples/data_pipeline_demo.py --output results/demo
        """,
    )
    parser.add_argument(
        "--symbols",
        "-s",
        nargs="+",
        default=["BTC", "ETH", "SOL"],
        help="Asset symbols to generate and analyze (default: BTC ETH SOL)",
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=7,
        help="Number of days of data (default: 7)",
    )
    parser.add_argument(
        "--timeframe",
        "-t",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        default="1h",
        help="Bar timeframe (default: 1h)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for results (optional)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "=" * 70)
    print("TRADEPULSE DATA PIPELINE DEMO")
    print("=" * 70 + "\n")

    try:
        # Step 1: Generate data
        print("📊 STEP 1: Generating Synthetic OHLCV Data")
        print("-" * 50)
        df = generate_data(
            symbols=args.symbols,
            days=args.days,
            timeframe=args.timeframe,
            seed=args.seed,
        )
        print()

        # Step 2: Validate data
        print("✅ STEP 2: Validating Data Quality")
        print("-" * 50)
        is_valid = validate_data(df)
        if not is_valid:
            logger.error("Data validation failed!")
            return 1
        print()

        # Step 3: Analyze each symbol
        print("🔬 STEP 3: Analyzing Market Regimes")
        print("-" * 50)
        results = []
        for symbol in args.symbols:
            result = analyze_market(df, symbol.upper())
            results.append(result)
        print()

        # Step 4: Display results
        display_results(results)

        # Step 5: Optionally save results
        if args.output:
            print("💾 STEP 4: Saving Results")
            print("-" * 50)
            save_results(df, results, args.output)
            print()

        print("✨ Demo completed successfully!")
        return 0

    except Exception as e:
        logger.exception("Demo failed: %s", e)
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
