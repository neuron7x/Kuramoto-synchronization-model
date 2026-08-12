# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Leakage / causality sentinel — six-check coverage tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from research.systemic_risk.leakage_sentinel import (
    OpRecord,
    check_centered_windows,
    check_crisis_date_tuning,
    check_full_sample_normalisation,
    check_future_data_via_mutation,
    check_label_leakage,
    check_post_event_contamination,
    run_leakage_audit,
)


@dataclass
class _LeadTime:
    detected_event_count: int
    min_lead_time: int | None


def _trailing_mean_score(window: int = 5) -> Callable[[np.ndarray], np.ndarray]:
    def builder(x: np.ndarray) -> np.ndarray:
        n = x.size
        out = np.full(n, np.nan, dtype=np.float64)
        for t in range(window - 1, n):
            out[t] = float(x[t - window + 1 : t + 1].mean())
        return out

    return builder


def _full_sample_mean_score() -> Callable[[np.ndarray], np.ndarray]:
    def builder(x: np.ndarray) -> np.ndarray:
        return np.full(x.size, float(x.mean()), dtype=np.float64)

    return builder


class TestFutureDataMutation:
    def test_trailing_score_passes(self) -> None:
        x = np.arange(100, dtype=np.float64)
        out = check_future_data_via_mutation(
            _trailing_mean_score(window=5),
            base_series=x,
            cut_index=50,
        )
        assert not out.detected
        assert out.type == "future_data"

    def test_full_sample_score_caught(self) -> None:
        x = np.arange(100, dtype=np.float64)
        out = check_future_data_via_mutation(
            _full_sample_mean_score(),
            base_series=x,
            cut_index=50,
        )
        assert out.detected
        assert "future" in out.reason.lower()


class TestPostEventContamination:
    def test_no_detections_clean(self) -> None:
        out = check_post_event_contamination(_LeadTime(detected_event_count=0, min_lead_time=None))
        assert not out.detected

    def test_lead_below_minimum_caught(self) -> None:
        out = check_post_event_contamination(_LeadTime(detected_event_count=2, min_lead_time=0))
        assert out.detected
        assert "post-event" in out.reason.lower()

    def test_valid_lead_passes(self) -> None:
        out = check_post_event_contamination(_LeadTime(detected_event_count=2, min_lead_time=15))
        assert not out.detected


class TestCenteredWindows:
    def test_clean_config(self) -> None:
        out = check_centered_windows({"window": 60, "align": "trailing"})
        assert not out.detected

    def test_center_flag_caught(self) -> None:
        out = check_centered_windows({"window": 60, "center": True})
        assert out.detected
        assert "center" in out.reason

    def test_align_center_caught(self) -> None:
        out = check_centered_windows({"window": 60, "align": "center"})
        assert out.detected

    def test_offset_positive_caught(self) -> None:
        out = check_centered_windows({"window": 60, "offset": 5})
        assert out.detected

    def test_offset_zero_passes(self) -> None:
        out = check_centered_windows({"window": 60, "offset": 0})
        assert not out.detected


class TestFullSampleNormalisation:
    def test_clean_log(self) -> None:
        out = check_full_sample_normalisation(["rolling_mean", "rolling_std", "rolling_zscore"])
        assert not out.detected

    def test_full_sample_op_caught(self) -> None:
        out = check_full_sample_normalisation(["rolling_mean", "full_sample_zscore", "rolling_std"])
        assert out.detected
        assert "full_sample_zscore" in out.reason


class TestLabelLeakage:
    def test_clean_dag(self) -> None:
        graph = [
            OpRecord(op_name="rolling_mean", time_in_index=10, time_out_index=15),
            OpRecord(op_name="zscore", time_in_index=15, time_out_index=15),
        ]
        out = check_label_leakage(graph)
        assert not out.detected

    def test_backwards_edge_caught(self) -> None:
        graph = [
            OpRecord(op_name="rolling_mean", time_in_index=10, time_out_index=10),
            OpRecord(op_name="future_label_join", time_in_index=20, time_out_index=10),
        ]
        out = check_label_leakage(graph)
        assert out.detected
        assert "future_label_join" in out.reason


class TestCrisisDateTuning:
    def test_lock_before_eval_clean(self) -> None:
        out = check_crisis_date_tuning(
            crisis_lock_timestamp_utc="2026-05-01T12:00:00+00:00",
            first_evaluation_timestamp_utc="2026-05-08T12:00:00+00:00",
        )
        assert not out.detected

    def test_lock_after_eval_caught(self) -> None:
        out = check_crisis_date_tuning(
            crisis_lock_timestamp_utc="2026-05-08T12:00:00+00:00",
            first_evaluation_timestamp_utc="2026-05-01T12:00:00+00:00",
        )
        assert out.detected
        assert "tuning" in out.reason.lower()

    def test_simultaneous_caught(self) -> None:
        same = "2026-05-08T12:00:00+00:00"
        out = check_crisis_date_tuning(
            crisis_lock_timestamp_utc=same,
            first_evaluation_timestamp_utc=same,
        )
        assert out.detected

    def test_invalid_timestamp_caught_as_detected(self) -> None:
        out = check_crisis_date_tuning(
            crisis_lock_timestamp_utc="garbage",
            first_evaluation_timestamp_utc="2026-05-08T12:00:00+00:00",
        )
        assert out.detected
        assert "parse" in out.reason.lower()


class TestRunLeakageAudit:
    def test_all_clean_aggregates_to_clean(self) -> None:
        x = np.arange(100, dtype=np.float64)
        outcomes = [
            check_future_data_via_mutation(
                _trailing_mean_score(window=5), base_series=x, cut_index=50
            ),
            check_post_event_contamination(_LeadTime(detected_event_count=0, min_lead_time=None)),
            check_centered_windows({"window": 60, "align": "trailing"}),
            check_full_sample_normalisation(["rolling_mean"]),
            check_label_leakage([]),
            check_crisis_date_tuning(
                crisis_lock_timestamp_utc="2026-05-01T12:00:00+00:00",
                first_evaluation_timestamp_utc="2026-05-08T12:00:00+00:00",
            ),
        ]
        report = run_leakage_audit(outcomes)
        assert not report.detected
        assert len(report.outcomes) == 6

    def test_one_detected_propagates(self) -> None:
        outcomes = [
            check_centered_windows({"window": 60, "align": "center"}),
        ]
        report = run_leakage_audit(outcomes)
        assert report.detected
