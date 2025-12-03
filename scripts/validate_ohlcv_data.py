#!/usr/bin/env python3
"""Validate OHLCV data files for trading analysis quality.

This script provides comprehensive data quality checks for OHLCV files,
validating schema, value constraints, and time series properties.

Usage:
    python scripts/validate_ohlcv_data.py data/sample_crypto_ohlcv.csv
    python scripts/validate_ohlcv_data.py data/*.csv --format json
"""
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Sequence

import pandas as pd

LOGGER = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Comprehensive validation report for OHLCV data."""

    file_path: str
    valid: bool = True
    row_count: int = 0
    column_count: int = 0
    columns: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    date_range: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert report to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


def validate_ohlcv_file(
    file_path: Path,
    close_col: str = "close",
    open_col: str | None = "open",
    high_col: str | None = "high",
    low_col: str | None = "low",
    volume_col: str | None = "volume",
    timestamp_col: str | None = "timestamp",
    symbol_col: str | None = "symbol",
) -> ValidationReport:
    """Validate an OHLCV data file.

    Args:
        file_path: Path to CSV file
        close_col: Name of close price column
        open_col: Name of open price column (optional)
        high_col: Name of high price column (optional)
        low_col: Name of low price column (optional)
        volume_col: Name of volume column (optional)
        timestamp_col: Name of timestamp column (optional)
        symbol_col: Name of symbol column (optional)

    Returns:
        ValidationReport with detailed results
    """
    report = ValidationReport(file_path=str(file_path))

    # Check file exists
    if not file_path.exists():
        report.valid = False
        report.errors.append(f"File not found: {file_path}")
        return report

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        report.valid = False
        report.errors.append(f"Failed to read CSV: {e}")
        return report

    report.row_count = len(df)
    report.column_count = len(df.columns)
    report.columns = list(df.columns)

    # Check for empty file
    if df.empty:
        report.valid = False
        report.errors.append("File is empty")
        return report

    # Check required close column
    if close_col not in df.columns:
        report.valid = False
        report.errors.append(f"Required column '{close_col}' not found")
        return report

    # Collect symbols if present
    if symbol_col and symbol_col in df.columns:
        report.symbols = list(df[symbol_col].unique())

    # Collect date range if timestamp present
    if timestamp_col and timestamp_col in df.columns:
        try:
            timestamps = pd.to_datetime(df[timestamp_col])
            report.date_range = f"{timestamps.min()} to {timestamps.max()}"
        except (ValueError, TypeError) as exc:
            # Handle expected parsing errors with specific message
            report.warnings.append(
                f"Could not parse timestamps in column '{timestamp_col}': {exc}"
            )
        except Exception as exc:
            # Log unexpected errors for debugging but continue validation
            LOGGER.warning(
                "Unexpected error parsing timestamps in column '%s': %s",
                timestamp_col,
                exc,
                exc_info=True,
            )
            report.warnings.append(
                f"Could not parse timestamps in column '{timestamp_col}': unexpected error"
            )

    # Validate price columns
    price_cols = [
        (close_col, "close"),
        (open_col, "open"),
        (high_col, "high"),
        (low_col, "low"),
    ]

    for col, label in price_cols:
        if col and col in df.columns:
            series = df[col]

            # Check for NaN values
            nan_count = series.isna().sum()
            if nan_count > 0:
                nan_pct = nan_count / len(df) * 100
                if nan_pct > 5:
                    report.valid = False
                    report.errors.append(
                        f"{nan_count} NaN values in {label} ({nan_pct:.1f}%)"
                    )
                else:
                    report.warnings.append(f"{nan_count} NaN values in {label}")

            # Check for non-positive prices
            valid_values = series.dropna()
            non_positive = (valid_values <= 0).sum()
            if non_positive > 0:
                report.valid = False
                report.errors.append(f"{non_positive} non-positive values in {label}")

    # Validate OHLC relationships
    has_ohlc = all(
        col and col in df.columns for col in [open_col, high_col, low_col, close_col]
    )

    if has_ohlc:
        # High >= Low
        violations = (df[high_col] < df[low_col]).sum()
        if violations > 0:
            report.valid = False
            report.errors.append(f"{violations} rows where high < low")

        # High >= max(open, close)
        max_oc = df[[open_col, close_col]].max(axis=1)
        violations = (df[high_col] < max_oc).sum()
        if violations > 0:
            report.warnings.append(f"{violations} rows where high < max(open, close)")

        # Low <= min(open, close)
        min_oc = df[[open_col, close_col]].min(axis=1)
        violations = (df[low_col] > min_oc).sum()
        if violations > 0:
            report.warnings.append(f"{violations} rows where low > min(open, close)")

    # Validate volume
    if volume_col and volume_col in df.columns:
        vol_series = df[volume_col]
        negative_volume = (vol_series < 0).sum()
        if negative_volume > 0:
            report.valid = False
            report.errors.append(f"{negative_volume} negative volume values")

    # Calculate statistics
    close_series = df[close_col].dropna()
    report.statistics = {
        "close_mean": float(close_series.mean()),
        "close_std": float(close_series.std()),
        "close_min": float(close_series.min()),
        "close_max": float(close_series.max()),
        "returns_mean": float(close_series.pct_change().dropna().mean()),
        "returns_std": float(close_series.pct_change().dropna().std()),
    }

    if volume_col and volume_col in df.columns:
        vol_series = df[volume_col].dropna()
        report.statistics["volume_mean"] = float(vol_series.mean())
        report.statistics["volume_std"] = float(vol_series.std())

    return report


def print_report(report: ValidationReport, format: str = "text") -> None:
    """Print validation report.

    Args:
        report: ValidationReport to print
        format: Output format (text or json)
    """
    if format == "json":
        print(report.to_json())
        return

    # Text format
    status = "✅ PASSED" if report.valid else "❌ FAILED"
    print(f"\n{'=' * 60}")
    print(f"Validation Report: {report.file_path}")
    print(f"{'=' * 60}")
    print(f"Status: {status}")
    print(f"Rows: {report.row_count:,}")
    print(f"Columns: {', '.join(report.columns)}")

    if report.symbols:
        print(f"Symbols: {', '.join(report.symbols)}")

    if report.date_range:
        print(f"Date Range: {report.date_range}")

    if report.errors:
        print(f"\n❌ Errors ({len(report.errors)}):")
        for error in report.errors:
            print(f"  • {error}")

    if report.warnings:
        print(f"\n⚠️  Warnings ({len(report.warnings)}):")
        for warning in report.warnings:
            print(f"  • {warning}")

    if report.statistics:
        print("\n📊 Statistics:")
        for key, value in report.statistics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")

    print()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate OHLCV data files for trading analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Validate a single file
    python scripts/validate_ohlcv_data.py data/sample_crypto_ohlcv.csv

    # Validate multiple files
    python scripts/validate_ohlcv_data.py data/*.csv

    # Output as JSON
    python scripts/validate_ohlcv_data.py data/sample.csv --format json

    # Custom column names
    python scripts/validate_ohlcv_data.py data.csv --close-col price --no-ohlc
        """,
    )
    parser.add_argument(
        "files",
        type=Path,
        nargs="+",
        help="CSV files to validate",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--close-col",
        default="close",
        help="Name of close price column (default: close)",
    )
    parser.add_argument(
        "--no-ohlc",
        action="store_true",
        help="Skip OHLC validation (for simple price data)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
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

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    all_valid = True
    reports = []

    for file_path in args.files:
        LOGGER.info("Validating %s", file_path)

        # Determine column configuration
        open_col = None if args.no_ohlc else "open"
        high_col = None if args.no_ohlc else "high"
        low_col = None if args.no_ohlc else "low"

        report = validate_ohlcv_file(
            file_path,
            close_col=args.close_col,
            open_col=open_col,
            high_col=high_col,
            low_col=low_col,
        )

        if args.strict and report.warnings:
            report.valid = False
            report.errors.extend(report.warnings)
            report.warnings = []

        reports.append(report)
        all_valid = all_valid and report.valid

    # Print results
    for report in reports:
        print_report(report, args.format)

    # Summary
    if len(reports) > 1:
        passed = sum(1 for r in reports if r.valid)
        total = len(reports)
        print(f"\n📋 Summary: {passed}/{total} files passed validation")

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
