# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the deterministic threshold-calibration instrument.

Covers the calibration-contract properties P1-P12: determinism, allowed
range enforcement, candidate-order independence, tie policy, invalid
candidate rejection, empty calibration/validation handling, NaN/inf
handling, sensitivity-sweep completeness, no-future-leakage, metadata
completeness, and the absence of forecasting / trading language.
"""

from __future__ import annotations

import math

import pytest

from analytics.signals.threshold_calibration import (
    ThresholdCalibrationResult,
    calibrate_threshold,
)

# A calibration sample whose values are 0..9; ~30% lie strictly above 6.0.
_CALIB = [float(i) for i in range(10)]
_VALID = [float(i) + 0.5 for i in range(10)]
_CANDIDATES = [2.0, 4.0, 6.0, 8.0]


def _calibrate(target: float = 0.3) -> ThresholdCalibrationResult:
    return calibrate_threshold(
        _CALIB,
        _VALID,
        candidates=_CANDIDATES,
        target_upper_share=target,
    )


# ── P1: determinism ──────────────────────────────────────────────────────
def test_p1_deterministic_selection() -> None:
    first = _calibrate()
    second = _calibrate()
    assert first.selected_value == second.selected_value
    assert first.metadata == second.metadata
    assert first.sensitivity_sweep == second.sensitivity_sweep


# ── P2: selected value is within the allowed candidate range ─────────────
def test_p2_selected_value_is_a_candidate() -> None:
    result = _calibrate()
    assert result.selected_value in _CANDIDATES


# ── P3: candidate ordering independence ──────────────────────────────────
def test_p3_candidate_order_does_not_change_selection() -> None:
    forward = calibrate_threshold(
        _CALIB, _VALID, candidates=[2.0, 4.0, 6.0, 8.0], target_upper_share=0.3
    )
    shuffled = calibrate_threshold(
        _CALIB, _VALID, candidates=[8.0, 2.0, 6.0, 4.0], target_upper_share=0.3
    )
    assert forward.selected_value == shuffled.selected_value


# ── P4: tie policy → smallest candidate ──────────────────────────────────
def test_p4_tie_breaks_to_smallest_candidate() -> None:
    # target 0.5 with symmetric candidates 4.0 (share .6) and 5.0 (share .5)…
    # construct an exact tie: candidates equidistant from target.
    calib = [0.0, 1.0]  # upper share above -1 is 1.0; above 2 is 0.0
    result = calibrate_threshold(
        calib, calib, candidates=[-1.0, 2.0], target_upper_share=0.5
    )
    # both candidates are 0.5 away from target → smallest (-1.0) wins
    assert result.selected_value == -1.0


# ── P5: invalid candidate rejection (fail-closed) ────────────────────────
def test_p5_empty_candidates_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        calibrate_threshold(_CALIB, _VALID, candidates=[], target_upper_share=0.3)


def test_p5_non_finite_candidate_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        calibrate_threshold(
            _CALIB, _VALID, candidates=[2.0, math.inf], target_upper_share=0.3
        )


def test_p5_duplicate_candidate_rejected() -> None:
    with pytest.raises(ValueError, match="distinct"):
        calibrate_threshold(
            _CALIB, _VALID, candidates=[2.0, 2.0], target_upper_share=0.3
        )


def test_p5_target_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        calibrate_threshold(_CALIB, _VALID, candidates=_CANDIDATES, target_upper_share=1.5)


# ── P6: empty calibration input fails closed ─────────────────────────────
def test_p6_empty_calibration_rejected() -> None:
    with pytest.raises(ValueError, match="calibration sample is empty"):
        calibrate_threshold([], _VALID, candidates=_CANDIDATES, target_upper_share=0.3)


# ── P7: empty validation input is tolerated (validation only reported) ───
def test_p7_empty_validation_is_tolerated() -> None:
    result = calibrate_threshold(
        _CALIB, [], candidates=_CANDIDATES, target_upper_share=0.3
    )
    assert result.metadata["validation_count"] == 0
    # validation metric is NaN when there is no validation sample
    for row in result.sensitivity_sweep:
        assert math.isnan(row["validation_metric"])


# ── P8: NaN/inf observations are counted, not silently dropped ───────────
def test_p8_non_finite_observations_counted() -> None:
    calib = [0.0, float("nan"), 5.0, float("inf")]
    result = calibrate_threshold(
        calib, [float("nan")], candidates=_CANDIDATES, target_upper_share=0.3
    )
    assert result.metadata["calibration_count"] == 2
    assert result.metadata["invalid_count"] == 3  # 2 in calib, 1 in validation


# ── P9: sensitivity sweep completeness ───────────────────────────────────
def test_p9_sensitivity_sweep_covers_every_candidate() -> None:
    result = _calibrate()
    swept = [row["candidate"] for row in result.sensitivity_sweep]
    assert swept == _CANDIDATES
    for row in result.sensitivity_sweep:
        assert set(row) == {
            "candidate",
            "calibration_metric",
            "validation_metric",
            "passes",
            "failure_reason",
        }


def test_p9_changing_threshold_changes_metric() -> None:
    """The selected parameter is not arbitrary: the calibration metric is
    monotonically non-increasing in the threshold and actually varies."""
    result = _calibrate()
    metrics = [row["calibration_metric"] for row in result.sensitivity_sweep]
    assert metrics == sorted(metrics, reverse=True)
    assert metrics[0] != metrics[-1]


# ── P10: no future leakage — validation never drives selection ───────────
def test_p10_validation_does_not_affect_selection() -> None:
    base = _calibrate()
    # Replace validation with wildly different data; selection must not move.
    perturbed = calibrate_threshold(
        _CALIB,
        [1e9, -1e9, 0.0],
        candidates=_CANDIDATES,
        target_upper_share=0.3,
    )
    assert base.selected_value == perturbed.selected_value


# ── P11: metadata completeness ───────────────────────────────────────────
def test_p11_metadata_records_full_contract() -> None:
    result = _calibrate()
    required = {
        "method",
        "parameter_name",
        "candidate_values",
        "selected_value",
        "metric_name",
        "metric_values",
        "target_upper_share",
        "calibration_count",
        "validation_count",
        "invalid_count",
        "seed",
        "tie_policy",
        "sensitivity_band",
        "sensitivity_pass_count",
        "failure_policy",
        "claim_boundary",
        "not_financial_advice",
        "not_predictive_claim",
    }
    assert required <= set(result.metadata)
    assert result.metadata["selected_value"] == result.selected_value
    assert result.metadata["claim_boundary"] == "descriptor_only_not_predictor"


# ── P12: no forecasting / trading language on the output surface ─────────
def test_p12_no_predictive_or_trading_language() -> None:
    forbidden = {
        "buy",
        "sell",
        "long",
        "short",
        "entry",
        "exit",
        "alpha",
        "edge",
        "profit",
        "trade",
        "predict",
        "forecast",
        "guaranteed",
    }
    result = _calibrate()
    disclaimer_keys = {"claim_boundary", "not_predictive_claim", "not_financial_advice"}
    blob = " ".join(
        f"{key}={value}"
        for key, value in result.metadata.items()
        if key not in disclaimer_keys
    ).lower()
    leaked = sorted(term for term in forbidden if term in blob)
    assert not leaked, f"forecasting/trading language leaked: {leaked}"
    assert result.metadata["not_predictive_claim"] is True


# ── selected threshold matches the declared objective on calibration ─────
def test_selected_threshold_meets_objective() -> None:
    # target 0.3 → expect threshold 6.0 (3 of 10 calib values strictly above)
    result = _calibrate(target=0.3)
    assert result.selected_value == 6.0
    selected_metric = result.metadata["metric_values"][6.0]
    assert selected_metric == pytest.approx(0.3)
