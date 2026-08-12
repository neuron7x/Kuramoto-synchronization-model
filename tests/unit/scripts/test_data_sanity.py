# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pandas as pd
import pytest

from scripts import data_sanity


def _write_sample_csv(path: str | bytes):
    df = pd.DataFrame(
        {
            "ts": [
                "2021-01-01T00:00:00Z",
                "2021-01-01T00:00:10Z",
                "2021-01-01T00:00:25Z",
                "2021-01-01T00:00:25Z",
            ],
            "value": [1, 2, None, None],
            "category": ["a", "a", "b", "b"],
        }
    )
    df.to_csv(path, index=False)
    return df


def _write_spiky_csv(path: str | bytes):
    df = pd.DataFrame(
        {
            "ts": [
                "2021-01-01T00:00:00Z",
                "2021-01-01T00:00:10Z",
                "2021-01-01T00:00:20Z",
                "2021-01-01T00:00:30Z",
            ],
            "value": [1, 2, 100, 3],
        }
    )
    df.to_csv(path, index=False)
    return df


def test_analyze_csv_returns_expected_metrics(tmp_path):
    csv_path = tmp_path / "example.csv"
    df = _write_sample_csv(csv_path)

    analysis = data_sanity.analyze_csv(csv_path)

    assert analysis.path == csv_path
    assert analysis.row_count == len(df)
    assert analysis.column_count == len(df.columns)
    assert analysis.duplicate_rows == 1
    assert analysis.nan_ratio == pytest.approx(df.isna().mean().mean())
    assert analysis.column_nan_ratios["value"] == pytest.approx(0.5)
    assert analysis.timestamp_gap_stats is not None
    assert analysis.timestamp_gap_stats.median_seconds == pytest.approx(10.0)
    assert analysis.timestamp_gap_stats.max_seconds == pytest.approx(15.0)
    assert analysis.timestamp_gap_stats.usable_gap_ratio == pytest.approx(1.0)
    assert analysis.timestamp_gap_stats.valid_row_ratio == pytest.approx(1.0)
    assert analysis.timestamp_gap_stats.monotonic_violations == 0
    assert analysis.spike_counts == {}


def test_format_analysis_includes_column_limits(tmp_path):
    csv_path = tmp_path / "example.csv"
    _write_sample_csv(csv_path)

    analysis = data_sanity.analyze_csv(csv_path)
    report = data_sanity.format_analysis(analysis, max_column_details=1)

    assert "column NaN ratios" in report
    assert "value=50.00%" in report
    assert "…" not in report
    assert "usable gaps" in report


def test_analyze_csv_detects_spikes(tmp_path):
    csv_path = tmp_path / "spikes.csv"
    _write_spiky_csv(csv_path)

    analysis = data_sanity.analyze_csv(csv_path)

    assert analysis.spike_counts == {"value": 1}


def test_analyze_csv_handles_invalid_timestamps(tmp_path):
    csv_path = tmp_path / "mixed.csv"
    df = pd.DataFrame(
        {
            "ts": [
                "2021-01-01T00:00:10Z",
                "not-a-timestamp",
                "2021-01-01T00:00:05Z",
                "2021-01-01T00:00:20Z",
            ],
            "value": [1, 2, 3, 4],
        }
    )
    df.to_csv(csv_path, index=False)

    analysis = data_sanity.analyze_csv(csv_path)

    assert analysis.timestamp_gap_stats is not None
    assert analysis.timestamp_gap_stats.median_seconds == pytest.approx(7.5)
    assert analysis.timestamp_gap_stats.max_seconds == pytest.approx(10.0)
    assert analysis.timestamp_gap_stats.usable_gap_ratio == pytest.approx(1 / 3)
    assert analysis.timestamp_gap_stats.valid_row_ratio == pytest.approx(0.75)
    assert analysis.timestamp_gap_stats.monotonic_violations == 1


def test_analyze_csv_flags_monotonic_issues(tmp_path):
    csv_path = tmp_path / "backwards.csv"
    df = pd.DataFrame(
        {
            "ts": [
                "2021-01-01T00:00:10Z",
                "2021-01-01T00:00:05Z",
                "2021-01-01T00:00:08Z",
                "2021-01-01T00:00:12Z",
            ],
            "value": [1, 2, 3, 4],
        }
    )
    df.to_csv(csv_path, index=False)

    analysis = data_sanity.analyze_csv(csv_path)

    assert analysis.timestamp_gap_stats is not None
    assert analysis.timestamp_gap_stats.monotonic_violations == 1
    assert analysis.timestamp_gap_stats.usable_gap_ratio == pytest.approx(2 / 3)


def test_main_handles_cli_execution(tmp_path, capsys):
    csv_path = tmp_path / "dataset.csv"
    _write_sample_csv(csv_path)

    exit_code = data_sanity.main([str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert f"# File: {csv_path}" in output
    assert "duplicates" in output


def test_main_reports_spikes(tmp_path, capsys):
    csv_path = tmp_path / "dataset.csv"
    _write_spiky_csv(csv_path)

    exit_code = data_sanity.main([str(tmp_path), "--spike-threshold", "5"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "- spikes: value=1" in output
