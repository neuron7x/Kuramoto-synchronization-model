"""Quick start example demonstrating TradePulse's core market analysis capabilities.

This script shows how to:
1. Generate sample market data
2. Analyze market regime using the Kuramoto-Ricci composite engine
3. Interpret the analysis results

Usage:
    python examples/quick_start.py
    python examples/quick_start.py --csv data/my_prices.csv --price-col close
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from core.data.validation import validate_ohlcv
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine
from core.utils.determinism import DEFAULT_SEED, seed_numpy


def sample_df(n: int = 1500, seed: int | None = None) -> pd.DataFrame:
    """Generate synthetic market data with regime changes.

    Creates a price series with three distinct regimes:
    1. Random walk (drift)
    2. Trending with oscillation
    3. Volatile random walk

    Args:
        n: Number of data points to generate
        seed: Random seed for reproducibility (optional)

    Returns:
        DataFrame with 'close' prices and 'volume' indexed by datetime
    """
    if seed is not None:
        seed_numpy(seed)

    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    r1 = np.cumsum(np.random.normal(0, 0.6, n // 3))
    r2 = (
        r1[-1]
        + 0.05 * np.arange(n // 3)
        + 2.5 * np.sin(2 * np.pi * np.arange(n // 3) / 100.0)
    )
    r3 = r2[-1] + np.cumsum(np.random.normal(0, 1.2, n - 2 * (n // 3)))
    price = 100 + np.concatenate([r1, r2, r3])
    vol = np.random.lognormal(10, 1, n)
    return pd.DataFrame({"close": price, "volume": vol}, index=idx)


def load_csv_data(csv_path: str, price_col: str = "close") -> pd.DataFrame:
    """Load market data from CSV file.

    Args:
        csv_path: Path to CSV file
        price_col: Name of the price column

    Returns:
        DataFrame with price data

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If required columns are missing
    """
    path = Path(csv_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    if price_col not in df.columns:
        available = ", ".join(df.columns[:10])
        raise ValueError(
            f"Column '{price_col}' not found. Available columns: {available}"
        )

    # Try to parse datetime index
    date_cols = [
        "date",
        "datetime",
        "timestamp",
        "time",
        "Date",
        "DateTime",
        "Timestamp",
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
            df.set_index(col, inplace=True)
            break

    # Ensure we have at least close and volume
    result = pd.DataFrame({"close": df[price_col]})
    if "volume" in df.columns:
        result["volume"] = df["volume"]
    elif "Volume" in df.columns:
        result["volume"] = df["Volume"]
    else:
        # Generate synthetic volume if not available
        result["volume"] = np.random.lognormal(10, 1, len(df))

    # Validate the loaded data
    validation = validate_ohlcv(result, price_col="close")
    if not validation.valid:
        raise ValueError(f"Data validation failed: {'; '.join(validation.issues)}")

    if validation.warnings:
        import sys

        for warning in validation.warnings:
            print(f"⚠️  Data warning: {warning}", file=sys.stderr)

    return result


def analyze_market(df: pd.DataFrame) -> dict:
    """Analyze market data and return comprehensive results.

    Args:
        df: DataFrame with 'close' and optionally 'volume' columns

    Returns:
        Dictionary with analysis results
    """
    engine = TradePulseCompositeEngine()
    snapshot = engine.analyze_market(df)

    return {
        "phase": snapshot.phase.value,
        "confidence": float(snapshot.confidence),
        "entry_signal": float(snapshot.entry_signal),
        "raw_snapshot": snapshot,
    }


def main():
    """Main entry point for quick start example."""
    parser = argparse.ArgumentParser(
        description="TradePulse Quick Start - Market Analysis Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
    # Use synthetic data
    python examples/quick_start.py

    # Use custom CSV data
    python examples/quick_start.py --csv data/prices.csv --price-col close

    # Reproducible analysis with seed
    python examples/quick_start.py --seed {DEFAULT_SEED}
        """,
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to CSV file with price data (optional, uses synthetic data if not provided)",
    )
    parser.add_argument(
        "--price-col",
        type=str,
        default="close",
        help="Name of the price column in CSV (default: close)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducible synthetic data generation",
    )
    parser.add_argument(
        "-n",
        "--num-points",
        type=int,
        default=1500,
        help="Number of data points to generate for synthetic data (default: 1500)",
    )

    args = parser.parse_args()

    try:
        # Load or generate data
        if args.csv:
            print(f"Loading data from: {args.csv}")
            df = load_csv_data(args.csv, args.price_col)
            print(f"Loaded {len(df)} data points")
        else:
            print(f"Generating synthetic data with {args.num_points} points...")
            df = sample_df(n=args.num_points, seed=args.seed)
            if args.seed:
                print(f"Using random seed: {args.seed}")

        # Validate data
        if len(df) < 200:
            print(
                f"Warning: Only {len(df)} data points. Recommend at least 200 for reliable analysis."
            )

        # Analyze
        print("\n=== TradePulse Market Analysis ===")
        print("-" * 40)

        result = analyze_market(df)

        print(f"Market Phase:     {result['phase']}")
        print(f"Confidence:       {result['confidence']:.3f}")
        print(f"Entry Signal:     {result['entry_signal']:.3f}")
        print("-" * 40)

        # Interpretation
        phase = result["phase"]
        confidence = result["confidence"]

        print("\n📊 Interpretation:")
        if phase == "accumulation":
            print("  • Market is in accumulation phase (potential bottoming)")
        elif phase == "distribution":
            print("  • Market is in distribution phase (potential topping)")
        elif phase == "trending":
            print("  • Market is trending strongly")
        elif phase == "transition":
            print("  • Market is transitioning between regimes")
        else:
            print(f"  • Current phase: {phase}")

        if confidence > 0.7:
            print(f"  • High confidence ({confidence:.1%}) in current phase")
        elif confidence > 0.4:
            print(f"  • Moderate confidence ({confidence:.1%}) - exercise caution")
        else:
            print(f"  • Low confidence ({confidence:.1%}) - high uncertainty")

        print("\n✅ Analysis complete!")
        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"❌ Data error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
