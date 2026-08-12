# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Detection-metric tests — NaN-not-zero, lead-time strictness."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from research.systemic_risk.metrics import (
    LeadTimeConfig,
    compute_classification_metrics,
    compute_lead_time_metrics,
)


class TestClassificationMetrics:
    def test_normal_case(self) -> None:
        # 3 TP, 1 FP, 1 TN, 1 FN
        y_true = np.array([1, 1, 1, 0, 0, 1], dtype=np.bool_)
        y_pred = np.array([1, 1, 1, 1, 0, 0], dtype=np.bool_)
        m = compute_classification_metrics(y_true, y_pred)
        assert m.tp == 3
        assert m.fp == 1
        assert m.tn == 1
        assert m.fn == 1
        assert m.precision == pytest.approx(0.75)
        assert m.recall == pytest.approx(0.75)
        assert m.false_positive_rate == pytest.approx(0.5)
        assert m.false_negative_rate == pytest.approx(0.25)

    def test_zero_predictions_yields_nan_precision(self) -> None:
        y_true = np.array([1, 0, 1, 0], dtype=np.bool_)
        y_pred = np.zeros(4, dtype=np.bool_)
        m = compute_classification_metrics(y_true, y_pred)
        assert np.isnan(m.precision)
        assert m.recall == 0.0  # 0 / 2 positives

    def test_zero_positives_yields_nan_recall(self) -> None:
        y_true = np.zeros(4, dtype=np.bool_)
        y_pred = np.array([1, 0, 1, 0], dtype=np.bool_)
        m = compute_classification_metrics(y_true, y_pred)
        assert np.isnan(m.recall)
        assert np.isnan(m.false_negative_rate)
        assert m.precision == 0.0  # 0 / 2 predictions
        assert m.false_positive_rate == pytest.approx(0.5)

    def test_no_negatives_yields_nan_fpr(self) -> None:
        y_true = np.ones(4, dtype=np.bool_)
        y_pred = np.array([1, 0, 1, 0], dtype=np.bool_)
        m = compute_classification_metrics(y_true, y_pred)
        assert np.isnan(m.false_positive_rate)

    def test_shape_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="matching shape"):
            compute_classification_metrics(np.ones(3, dtype=np.bool_), np.ones(4, dtype=np.bool_))

    def test_arbitrary_numeric_input_rejected(self) -> None:
        # Codex audit P1: arbitrary floats must NOT be silently
        # coerced via np.asarray(..., dtype=bool). The binary
        # contract is enforced fail-closed.
        with pytest.raises(ValueError, match="bool or binary"):
            compute_classification_metrics(
                np.array([0.0, 1.0, 0.5], dtype=np.float64),
                np.array([0, 1, 1], dtype=np.int64),
            )

    def test_out_of_range_int_rejected(self) -> None:
        with pytest.raises(ValueError, match="0/1"):
            compute_classification_metrics(
                np.array([0, 1, 2], dtype=np.int64),
                np.array([0, 1, 1], dtype=np.int64),
            )

    def test_binary_int_input_accepted(self) -> None:
        m = compute_classification_metrics(
            np.array([1, 1, 0, 0], dtype=np.int64),
            np.array([1, 0, 0, 1], dtype=np.int64),
        )
        assert m.tp == 1 and m.fp == 1 and m.tn == 1 and m.fn == 1


class TestLeadTimeConfig:
    def test_negative_min_lead_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_lead_days"):
            LeadTimeConfig(min_lead_days=-1, max_lead_days=10)

    def test_max_lt_min_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= min_lead"):
            LeadTimeConfig(min_lead_days=5, max_lead_days=3)

    def test_max_below_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_lead_days"):
            LeadTimeConfig(min_lead_days=0, max_lead_days=0)

    def test_event_exclusion_param_removed(self) -> None:
        # event_exclusion_days_after has been removed from
        # LeadTimeConfig; passing it must raise TypeError as a
        # protective regression test against future re-introduction
        # without explicit operationalisation.
        with pytest.raises(TypeError):
            LeadTimeConfig(  # type: ignore[call-arg]
                min_lead_days=1,
                max_lead_days=10,
                event_exclusion_days_after=0,
            )


class TestLeadTimeMetrics:
    def _make(self, n: int, start: date) -> tuple[np.ndarray, tuple[date, ...]]:
        score = np.zeros(n, dtype=np.float64)
        dates = tuple(start + timedelta(days=i) for i in range(n))
        return score, dates

    def test_signal_before_event_counted(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        # Alarm at day 30; event at day 50 ⇒ lead = 20 days.
        score[30] = 1.0
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=60)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50],),
            config=cfg,
        )
        assert out.event_count == 1
        assert out.detected_event_count == 1
        assert out.lead_times == (20,)
        assert out.median_lead_time == 20.0
        assert out.min_lead_time == 20
        assert out.max_lead_time == 20

    def test_signal_after_event_not_counted(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        # Alarm at day 55, event at day 50 → post-event, no lead.
        score[55] = 1.0
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=60)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50],),
            config=cfg,
        )
        assert out.detected_event_count == 0
        assert out.lead_times == ()
        assert np.isnan(out.median_lead_time)
        assert out.min_lead_time is None

    def test_event_date_signal_excluded_when_min_lead_one(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        # Alarm exactly on event day 50 — must NOT count when
        # min_lead_days=1.
        score[50] = 1.0
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=60)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50],),
            config=cfg,
        )
        assert out.detected_event_count == 0

    def test_event_date_signal_counted_when_min_lead_zero(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        score[50] = 1.0
        cfg = LeadTimeConfig(min_lead_days=0, max_lead_days=60)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50],),
            config=cfg,
        )
        # Lead = 0 days.
        assert out.detected_event_count == 1
        assert out.lead_times == (0,)

    def test_first_valid_signal_used(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        # Two pre-event alarms inside the window: at day 20 and day 40.
        # Earliest valid one is day 20 → lead = 30.
        score[20] = 1.0
        score[40] = 1.0
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=40)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50],),
            config=cfg,
        )
        assert out.detected_event_count == 1
        assert out.lead_times == (30,)

    def test_threshold_must_be_finite(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=60)
        with pytest.raises(ValueError, match="threshold must be finite"):
            compute_lead_time_metrics(
                score,
                dates,
                threshold=float("inf"),
                event_dates=(dates[50],),
                config=cfg,
            )

    def test_dates_must_be_strictly_increasing(self) -> None:
        start = date(2020, 1, 1)
        score = np.zeros(3, dtype=np.float64)
        bad_dates = (start, start, start + timedelta(days=1))
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=10)
        with pytest.raises(ValueError, match="strictly increasing"):
            compute_lead_time_metrics(
                score,
                bad_dates,
                threshold=0.5,
                event_dates=(start + timedelta(days=2),),
                config=cfg,
            )

    def test_warmup_nan_allowed_by_default(self) -> None:
        # Leading NaN block from rolling-window warmup is accepted;
        # a NaN past warmup is rejected.
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        score[:10] = np.nan  # warmup
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=30)
        # No alarms inside window so detected count = 0 — but the
        # call must not raise on the warmup NaN block.
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[40],),
            config=cfg,
        )
        assert out.detected_event_count == 0

    def test_nan_past_warmup_rejected(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        score[5] = 1.0  # finite — first finite value
        score[20] = np.nan  # NaN past warmup
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=30)
        with pytest.raises(ValueError, match="past the leading warmup"):
            compute_lead_time_metrics(
                score,
                dates,
                threshold=0.5,
                event_dates=(dates[40],),
                config=cfg,
            )

    def test_strict_finite_score_mode(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        score[3] = np.nan
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=30)
        with pytest.raises(ValueError, match="must be finite"):
            compute_lead_time_metrics(
                score,
                dates,
                threshold=0.5,
                event_dates=(dates[40],),
                config=cfg,
                allow_warmup_nan=False,
            )

    def test_no_signal_undetected(self) -> None:
        start = date(2020, 1, 1)
        score, dates = self._make(60, start)
        cfg = LeadTimeConfig(min_lead_days=1, max_lead_days=60)
        out = compute_lead_time_metrics(
            score,
            dates,
            threshold=0.5,
            event_dates=(dates[50], dates[55]),
            config=cfg,
        )
        assert out.event_count == 2
        assert out.detected_event_count == 0
        assert out.min_lead_time is None
        assert out.max_lead_time is None
