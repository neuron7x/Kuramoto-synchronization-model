"""Tests for data_sanity.py script."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from pathlib import Path

import pandas as pd
import pytest

from scripts import data_sanity


def test_analyze_csv_returns_analysis_with_basic_stats(tmp_path: Path) -> None:
    """Test that analyze_csv returns correct basic statistics."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("ts,value\n2024-01-01,10.0\n2024-01-02,20.0\n", encoding="utf-8")

    result = data_sanity.analyze_csv(csv_file)

    assert result.path == csv_file
    assert result.row_count == 2
    assert result.column_count == 2
    assert result.duplicate_rows == 0


def test_analyze_csv_detects_nan_values(tmp_path: Path) -> None:
    """Test that analyze_csv correctly identifies NaN values."""
    csv_file = tmp_path / "with_nans.csv"
    csv_file.write_text("ts,value\n2024-01-01,10.0\n2024-01-02,\n", encoding="utf-8")

    result = data_sanity.analyze_csv(csv_file)

    assert result.nan_ratio > 0
    assert "value" in result.column_nan_ratios


def test_analyze_csv_detects_duplicate_rows(tmp_path: Path) -> None:
    """Test that analyze_csv detects duplicate rows."""
    csv_file = tmp_path / "duplicates.csv"
    csv_file.write_text(
        "ts,value\n2024-01-01,10.0\n2024-01-01,10.0\n2024-01-02,20.0\n",
        encoding="utf-8",
    )

    result = data_sanity.analyze_csv(csv_file)

    assert result.duplicate_rows == 1


def test_analyze_csv_computes_timestamp_gap_stats(tmp_path: Path) -> None:
    """Test that analyze_csv computes timestamp gap statistics."""
    csv_file = tmp_path / "timeseries.csv"
    csv_file.write_text(
        "ts,value\n2024-01-01 00:00:00,10.0\n2024-01-01 01:00:00,20.0\n2024-01-01 02:00:00,30.0\n",
        encoding="utf-8",
    )

    result = data_sanity.analyze_csv(csv_file, timestamp_column="ts")

    assert result.timestamp_gap_stats is not None
    assert result.timestamp_gap_stats.median_seconds == 3600.0
    assert result.timestamp_gap_stats.max_seconds == 3600.0


def test_analyze_csv_handles_missing_timestamp_column(tmp_path: Path) -> None:
    """Test that analyze_csv handles missing timestamp column gracefully."""
    csv_file = tmp_path / "no_ts.csv"
    csv_file.write_text("value,other\n10.0,a\n20.0,b\n", encoding="utf-8")

    result = data_sanity.analyze_csv(csv_file, timestamp_column="ts")

    assert result.timestamp_gap_stats is None


def test_analyze_csv_detects_spikes(tmp_path: Path) -> None:
    """Test that analyze_csv detects spikes in numeric columns."""
    csv_file = tmp_path / "spikes.csv"
    # Create data with an extreme outlier
    values = [10.0] * 50 + [10000.0] + [10.0] * 50
    lines = ["ts,value"]
    for i, v in enumerate(values):
        lines.append(f"2024-01-{i + 1:02d},{v}")
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    result = data_sanity.analyze_csv(csv_file, spike_threshold=5.0)

    assert "value" in result.spike_counts
    assert result.spike_counts["value"] >= 1


def test_compute_spike_counts_empty_dataframe() -> None:
    """Test that _compute_spike_counts handles empty DataFrame."""
    df = pd.DataFrame()
    result = data_sanity._compute_spike_counts(df)
    assert result == {}


def test_compute_spike_counts_no_numeric_columns() -> None:
    """Test that _compute_spike_counts handles non-numeric data."""
    df = pd.DataFrame({"col": ["a", "b", "c"]})
    result = data_sanity._compute_spike_counts(df)
    assert result == {}


def test_summarize_timestamp_gaps_empty_series() -> None:
    """Test that _summarize_timestamp_gaps returns None for empty series."""
    series = pd.Series([], dtype="datetime64[ns]")
    result = data_sanity._summarize_timestamp_gaps(series)
    assert result is None


def test_summarize_timestamp_gaps_with_monotonic_violations() -> None:
    """Test that _summarize_timestamp_gaps tracks monotonic violations."""
    series = pd.Series(
        pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-02", "2024-01-04"])
    )
    result = data_sanity._summarize_timestamp_gaps(series)

    assert result is not None
    assert result.monotonic_violations == 1


def test_iter_csv_files_empty_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that _iter_csv_files handles empty paths list."""
    # Change to tmp_path so default 'data' directory doesn't exist
    monkeypatch.chdir(tmp_path)
    result = list(data_sanity._iter_csv_files([], "**/*.csv"))
    assert result == []


def test_iter_csv_files_finds_csv_in_directory(tmp_path: Path) -> None:
    """Test that _iter_csv_files finds CSV files in a directory."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    result = list(data_sanity._iter_csv_files([tmp_path], "**/*.csv"))

    assert len(result) == 1
    assert result[0].name == "test.csv"


def test_iter_csv_files_deduplicates(tmp_path: Path) -> None:
    """Test that _iter_csv_files deduplicates paths."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    result = list(data_sanity._iter_csv_files([tmp_path, tmp_path], "**/*.csv"))

    assert len(result) == 1


def test_format_analysis_includes_all_sections(tmp_path: Path) -> None:
    """Test that format_analysis includes all sections in output."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "ts,value\n2024-01-01 00:00:00,10.0\n2024-01-01 01:00:00,20.0\n",
        encoding="utf-8",
    )

    analysis = data_sanity.analyze_csv(csv_file)
    formatted = data_sanity.format_analysis(analysis)

    assert "# File:" in formatted
    assert "rows:" in formatted
    assert "cols:" in formatted
    assert "NaN ratio" in formatted


def test_format_column_nan_ratios_limits_output() -> None:
    """Test that _format_column_nan_ratios respects limit parameter."""
    ratios = {"a": 0.5, "b": 0.4, "c": 0.3, "d": 0.2, "e": 0.1}

    result = data_sanity._format_column_nan_ratios(ratios, limit=2)

    assert result is not None
    assert "…" in result
    assert "a=" in result
    assert "b=" in result


def test_format_column_nan_ratios_empty_dict() -> None:
    """Test that _format_column_nan_ratios handles empty dict."""
    result = data_sanity._format_column_nan_ratios({}, limit=5)
    assert result is None


def test_parse_args_defaults() -> None:
    """Test that parse_args returns correct defaults."""
    args = data_sanity.parse_args([])

    assert args.paths == []
    assert args.pattern == "**/*.csv"
    assert args.timestamp_column == "ts"
    assert args.spike_threshold == 10.0
    assert args.fail_on_error is False


def test_parse_args_custom_values() -> None:
    """Test that parse_args handles custom values."""
    args = data_sanity.parse_args(
        [
            "dir1",
            "dir2",
            "--pattern",
            "*.csv",
            "--timestamp-column",
            "time",
            "--spike-threshold",
            "5.0",
            "--fail-on-error",
        ]
    )

    assert len(args.paths) == 2
    assert args.pattern == "*.csv"
    assert args.timestamp_column == "time"
    assert args.spike_threshold == 5.0
    assert args.fail_on_error is True


def test_main_with_no_csv_files(tmp_path: Path, capsys) -> None:
    """Test that main returns 0 when no CSV files found."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    exit_code = data_sanity.main([str(empty_dir)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No CSV files found" in captured.out


def test_main_analyzes_csv_file(tmp_path: Path, capsys) -> None:
    """Test that main correctly analyzes a CSV file."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("ts,value\n2024-01-01,10.0\n2024-01-02,20.0\n", encoding="utf-8")

    exit_code = data_sanity.main([str(csv_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "sample.csv" in captured.out
    assert "rows: 2" in captured.out


def test_main_handles_invalid_csv(tmp_path: Path, capsys) -> None:
    """Test that main handles invalid CSV files."""
    bad_file = tmp_path / "bad.csv"
    # Create a binary file that cannot be parsed as CSV
    bad_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    # With fail_on_error=True
    exit_code = data_sanity.main([str(bad_file), "--fail-on-error"])

    assert exit_code == 1
