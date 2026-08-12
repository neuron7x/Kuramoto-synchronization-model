# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Quick data quality sanity checks for CSV files.

This module started life as a small ad-hoc script but has since been tidied up
so it is easier to extend, test and run as part of CI workflows.  The
improvements include:

* Fully typed, documented helper functions that can be imported from tests.
* Structured analysis results that make downstream processing easier.
* A tiny CLI powered by :mod:`argparse` for filtering input files and tweaking
  behaviour without editing the script.
* Outlier detection using a configurable median absolute deviation threshold so
  data spikes are surfaced alongside duplicate and missing value checks.

Typical usage from the repository root::

    python scripts/data_sanity.py data --pattern "**/*.csv"

"""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd


@dataclass(frozen=True)
class TimestampGapStats:
    """Summary statistics describing gaps between consecutive timestamps.

    In addition to the traditional ``median`` and ``max`` gap, the structure
    keeps lightweight quality indicators so callers can reason about the health
    of the timestamp column.  ``usable_gap_ratio`` expresses how many of the
    theoretically possible gaps remained after filtering invalid timestamps and
    monotonicity violations, while ``valid_row_ratio`` tracks how many original
    rows contributed to the statistics.  ``monotonic_violations`` counts the
    number of times the timestamp column moved backwards in the input order.
    """

    median_seconds: float
    max_seconds: float
    usable_gap_ratio: float
    valid_row_ratio: float
    monotonic_violations: int


@dataclass(frozen=True)
class CSVAnalysis:
    """Container for the computed quality metrics of a CSV file."""

    path: Path
    row_count: int
    column_count: int
    nan_ratio: float
    duplicate_rows: int
    column_nan_ratios: dict[str, float]
    timestamp_gap_stats: TimestampGapStats | None
    spike_counts: dict[str, int]


def _iter_csv_files(paths: Sequence[Path], pattern: str) -> Iterable[Path]:
    """Yield CSV files contained in *paths*.

    When *paths* is empty the function falls back to the default ``data``
    directory.  Directory arguments are walked recursively using :meth:`Path.rglob`.
    """

    if not paths:
        default_root = Path("data")
        if not default_root.exists():
            return
        paths = [default_root]

    seen: set[Path] = set()
    for path in paths:
        if path.is_dir():
            candidates = path.rglob(pattern)
        else:
            candidates = [path]

        for candidate in candidates:
            if candidate.suffix.lower() != ".csv":
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield resolved


def _compute_spike_counts(df: pd.DataFrame, threshold: float = 10.0) -> dict[str, int]:
    """Identify columns containing significant spikes/outliers."""

    numeric = df.select_dtypes(include=["number"])
    if numeric.empty:
        return {}

    spike_counts: dict[str, int] = {}
    for column in numeric.columns:
        series = numeric[column].dropna().astype(float)
        if series.empty:
            continue
        median = float(series.median())
        deviations = (series - median).abs()
        mad = float(deviations.median())
        if mad == 0.0:
            mad = float(deviations.mean())
        if mad == 0.0:
            continue
        scaled = deviations / mad
        spikes = int(scaled.gt(threshold).sum())
        if spikes:
            spike_counts[column] = spikes
    return spike_counts


def _summarize_timestamp_gaps(series: pd.Series) -> TimestampGapStats | None:
    """Compute gap statistics while tracking timestamp data quality."""

    if series.empty:
        return None

    coerced = pd.to_datetime(series, errors="coerce")
    total_rows = len(coerced)
    valid = coerced.dropna()
    valid_count = len(valid)
    if valid_count < 2:
        return None

    valid_row_ratio = valid_count / total_rows if total_rows else 0.0

    diffs = valid.diff().dt.total_seconds().iloc[1:]
    monotonic_violations = int(diffs.lt(0).sum())

    usable_pairs = max(valid_count - 1 - monotonic_violations, 0)
    possible_pairs = max(total_rows - 1, 1)
    usable_gap_ratio = usable_pairs / possible_pairs

    sorted_valid = valid.sort_values()
    gaps = sorted_valid.diff().dt.total_seconds().dropna()
    if gaps.empty:
        return None

    return TimestampGapStats(
        median_seconds=float(gaps.median()),
        max_seconds=float(gaps.max()),
        usable_gap_ratio=usable_gap_ratio,
        valid_row_ratio=valid_row_ratio,
        monotonic_violations=monotonic_violations,
    )


def analyze_csv(
    path: Path, timestamp_column: str | None = "ts", spike_threshold: float = 10.0
) -> CSVAnalysis:
    """Inspect a CSV file and derive lightweight quality metrics."""

    df = pd.read_csv(path)
    row_count, column_count = df.shape
    nan_ratio = float(df.isna().mean().mean()) if column_count else 0.0
    duplicate_rows = int(df.duplicated().sum())

    timestamp_gap_stats: TimestampGapStats | None = None
    if timestamp_column and timestamp_column in df.columns:
        timestamp_gap_stats = _summarize_timestamp_gaps(df[timestamp_column])

    per_column_nan = (
        df.isna().mean().loc[lambda series: series.gt(0)].sort_values(ascending=False).to_dict()
    )

    spike_counts = _compute_spike_counts(df, threshold=spike_threshold)

    return CSVAnalysis(
        path=Path(path),
        row_count=int(row_count),
        column_count=int(column_count),
        nan_ratio=nan_ratio,
        duplicate_rows=duplicate_rows,
        column_nan_ratios=per_column_nan,
        timestamp_gap_stats=timestamp_gap_stats,
        spike_counts=spike_counts,
    )


def _format_column_nan_ratios(column_nan_ratios: dict[str, float], limit: int) -> str | None:
    if not column_nan_ratios:
        return None

    items = list(column_nan_ratios.items())[:limit]
    formatted = ", ".join(f"{column}={ratio:.2%}" for column, ratio in items)
    if len(column_nan_ratios) > limit:
        formatted += ", …"
    return formatted


def format_analysis(analysis: CSVAnalysis, *, max_column_details: int = 5) -> str:
    """Convert :class:`CSVAnalysis` into the original human readable format."""

    report_lines = [
        f"# File: {analysis.path}",
        f"- rows: {analysis.row_count}; cols: {analysis.column_count}",
        f"- NaN ratio (avg): {analysis.nan_ratio:.4f}",
    ]

    column_details = _format_column_nan_ratios(analysis.column_nan_ratios, max_column_details)
    if column_details:
        report_lines.append(f"- column NaN ratios: {column_details}")

    if analysis.timestamp_gap_stats:
        gap_stats = analysis.timestamp_gap_stats
        gap_line = (
            "- median gap (s): "
            f"{gap_stats.median_seconds:.3f}; max gap (s): "
            f"{gap_stats.max_seconds:.3f}; usable gaps: "
            f"{gap_stats.usable_gap_ratio:.1%}"
        )

        extras: list[str] = []
        if gap_stats.valid_row_ratio < 1.0:
            extras.append(f"valid ts rows: {gap_stats.valid_row_ratio:.1%}")
        if gap_stats.monotonic_violations:
            extras.append(f"monotonic violations: {gap_stats.monotonic_violations}")
        if extras:
            gap_line += "; " + "; ".join(extras)

        report_lines.append(gap_line)

    if analysis.spike_counts:
        spike_details = ", ".join(
            f"{column}={count}" for column, count in sorted(analysis.spike_counts.items())
        )
        report_lines.append(f"- spikes: {spike_details}")

    report_lines.append(f"- duplicates: {analysis.duplicate_rows}")
    return "\n".join(report_lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "CSV files or directories to inspect.  When omitted the script "
            "searches the 'data' directory."
        ),
    )
    parser.add_argument(
        "--pattern",
        default="**/*.csv",
        help="Glob-style pattern used when walking directories (default: **/*.csv).",
    )
    parser.add_argument(
        "--timestamp-column",
        default="ts",
        help="Column containing timestamps used for gap statistics (default: ts).",
    )
    parser.add_argument(
        "--spike-threshold",
        type=float,
        default=10.0,
        help=(
            "Median absolute deviation multiplier used to flag spikes in numeric "
            "columns (default: 10.0)."
        ),
    )
    parser.add_argument(
        "--max-column-details",
        type=int,
        default=5,
        help="Maximum number of per-column NaN ratios to display (default: 5).",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return a non-zero exit status if any file fails to parse.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    analyses: List[str] = []
    exit_code = 0

    csv_files = sorted(_iter_csv_files(args.paths, args.pattern) or [])
    spike_threshold = max(args.spike_threshold, 0.0)
    if spike_threshold == 0.0:
        spike_threshold = 10.0

    if not csv_files:
        print("No CSV files found — nothing to check (OK).")
        return exit_code

    for csv_file in csv_files:
        try:
            analysis = analyze_csv(
                csv_file,
                args.timestamp_column,
                spike_threshold=spike_threshold,
            )
        except Exception as exc:  # pragma: no cover - defensive: pandas error message varies
            analyses.append(f"# File: {csv_file}\n- ERROR: {exc}")
            if args.fail_on_error:
                exit_code = 1
        else:
            analyses.append(
                format_analysis(analysis, max_column_details=max(1, args.max_column_details))
            )

    print("\n\n".join(analyses))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
