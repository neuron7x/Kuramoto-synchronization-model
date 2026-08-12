# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pandas as pd
import pytest

from core.data.quality_control import (
    QualityGateConfig,
    QualityGateError,
    QualityReport,
    QualitySummary,
    RangeCheck,
    TemporalContract,
    quarantine_anomalies,
    summarise_quality,
    validate_and_quarantine,
)
from core.data.validation import TimeSeriesValidationConfig, ValueColumnConfig


def _frame() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=6, freq="1min", tz="UTC")
    data = pd.DataFrame(
        {
            "timestamp": index,
            "close": [100, 101, 150, 102, 103, 104],
        }
    )
    data.loc[5, "timestamp"] = data.loc[4, "timestamp"]
    return data


def test_quarantine_detects_spikes_and_duplicates():
    frame = _frame().set_index("timestamp")
    result = quarantine_anomalies(frame, threshold=2.0, window=2, price_column="close")
    assert not result["duplicates"].empty
    assert not result["spikes"].empty
    assert result["clean"].shape[0] < frame.shape[0]


def test_validate_and_quarantine_integrates_schema():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        anomaly_threshold=2.0,
        anomaly_window=2,
        max_quarantine_fraction=1.0,
    )
    report = validate_and_quarantine(frame, gate)
    assert isinstance(report, QualityReport)
    assert set(report.clean.columns) >= {"timestamp", "close"}
    assert not report.quarantined.empty
    assert report.blocked is False


def test_range_gate_blocks_out_of_bounds_rows():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        range_checks=(RangeCheck(column="close", max_value=120.0),),
    )
    report = validate_and_quarantine(frame, gate)
    assert report.blocked is True
    assert "close" in report.range_violations
    with pytest.raises(QualityGateError):
        report.raise_if_blocked()


def test_temporal_contract_flags_stale_batches():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        temporal_contract=TemporalContract(max_lag="0s"),
    )
    report = validate_and_quarantine(frame, gate)
    assert report.blocked is True
    assert report.contract_breaches
    with pytest.raises(QualityGateError):
        report.raise_if_blocked()


def test_quality_summary_reports_metrics_and_validators():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        anomaly_threshold=2.0,
        anomaly_window=2,
    )
    report = validate_and_quarantine(frame, gate)
    summary = report.summarise(gate)

    assert isinstance(summary, QualitySummary)
    assert summary.total_rows == frame.shape[0]
    assert summary.quarantined_rows == summary.sanitised_rows
    validator_statuses = {
        outcome.category: outcome.status for outcome in summary.validator_outcomes
    }
    assert validator_statuses["syntax"] == "pass"
    assert validator_statuses["semantics"] == "warn"
    assert validator_statuses["security"] == "warn"
    assert summary.duplicate_rows == report.duplicates.shape[0]
    payload = summary.to_dict()
    assert payload["total_rows"] == frame.shape[0]
    assert payload["validator_outcomes"]
    assert payload["anomaly_threshold"] == pytest.approx(gate.anomaly_threshold)


def test_quality_summary_flags_range_failures():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        range_checks=(RangeCheck(column="close", max_value=120.0),),
    )
    report = validate_and_quarantine(frame, gate)
    summary = report.summarise(gate)

    assert summary.blocked is True
    assert summary.range_violation_rows["close"] == 1
    semantics = next(
        outcome
        for outcome in summary.validator_outcomes
        if outcome.category == "semantics"
    )
    assert semantics.status == "fail"


def test_quality_summary_warns_when_blocked_by_quarantine_ratio():
    frame = _frame()
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(
        schema=config,
        price_column="close",
        anomaly_threshold=99.0,
        anomaly_window=2,
        max_quarantine_fraction=0.1,
    )
    report = validate_and_quarantine(frame, gate)
    assert report.blocked is True
    summary = report.summarise(gate)

    semantics = next(
        outcome
        for outcome in summary.validator_outcomes
        if outcome.category == "semantics"
    )
    assert semantics.status == "warn"
    assert "blocked" in semantics.detail.lower()


def test_quality_summary_passes_when_dataset_clean():
    index = pd.date_range("2024-01-01", periods=4, freq="1min", tz="UTC")
    frame = pd.DataFrame({"timestamp": index, "close": [100, 101, 102, 103]})
    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
    )
    gate = QualityGateConfig(schema=config, price_column="close")
    report = validate_and_quarantine(frame, gate)
    summary = summarise_quality(report, gate)

    assert summary.quarantined_rows == 0
    assert summary.quarantine_ratio == 0.0
    for outcome in summary.validator_outcomes:
        assert outcome.status == "pass"
