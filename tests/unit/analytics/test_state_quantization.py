# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the deterministic state-quantization compiler.

Each test maps to a property of the quantization contract (P1-P10):
determinism, finite bounded output, exact tie behaviour, explicit
non-finite handling, empty/constant/outlier behaviour, metadata
completeness, fail-closed rule validation, absence of forecasting
language, and the no-future-leakage guarantee of a fixed-threshold rule.
"""

from __future__ import annotations

import math

import pytest

from analytics.signals.state_quantization import (
    DEFAULT_INVALID_STATE,
    QuantizationStateResult,
    quantize_states,
)

_THRESHOLDS = [-0.5, 0.5]
_LABELS = ["low", "neutral", "high"]


def _quantize(values: list[float]) -> QuantizationStateResult:
    return quantize_states(values, thresholds=_THRESHOLDS, labels=_LABELS)


# ── P1: determinism ──────────────────────────────────────────────────────
def test_p1_deterministic_for_same_input_and_config() -> None:
    values = [-2.0, -0.4, 0.0, 0.6, 3.0]
    first = _quantize(values)
    second = _quantize(values)
    assert first.states == second.states
    assert first.metadata == second.metadata
    # config hash pins the rule and is stable across runs.
    assert first.metadata["config_hash"] == second.metadata["config_hash"]


# ── P2 / P3: finite bounded output, no state outside the declared set ─────
def test_p2_p3_all_states_belong_to_declared_set() -> None:
    allowed = set(_LABELS) | {DEFAULT_INVALID_STATE}
    result = _quantize([-1e9, -0.5, 0.0, 0.5, 1e9, float("nan")])
    assert set(result.states) <= allowed
    assert all(isinstance(s, str) for s in result.states)


# ── P4: exact threshold / tie behaviour (searchsorted right → upper band) ─
def test_p4_value_equal_to_threshold_maps_to_upper_band() -> None:
    result = quantize_states([-0.5, 0.5], thresholds=_THRESHOLDS, labels=_LABELS)
    # -0.5 == lower threshold → upper adjacent band "neutral"
    # 0.5 == upper threshold → upper adjacent band "high"
    assert result.states == ("neutral", "high")


def test_p4_tie_behaviour_is_stable_for_repeated_values() -> None:
    result = quantize_states([0.5] * 5, thresholds=_THRESHOLDS, labels=_LABELS)
    assert result.states == ("high",) * 5


# ── P5: explicit NaN / inf handling, counted not absorbed ────────────────
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_p5_non_finite_maps_to_invalid_and_is_counted(bad: float) -> None:
    result = quantize_states([0.0, bad, 0.0], thresholds=_THRESHOLDS, labels=_LABELS)
    assert result.states[1] == DEFAULT_INVALID_STATE
    assert result.metadata["invalid_count"] == 1
    assert result.metadata["finite_count"] == 2
    # the invalid observation must NOT inflate any real band (negative
    # evidence is preserved, P10).
    assert sum(result.metadata["state_counts"].values()) == 2


# ── P6: empty input behaviour ────────────────────────────────────────────
def test_p6_empty_input_is_declared_not_crashing() -> None:
    result = quantize_states([], thresholds=_THRESHOLDS, labels=_LABELS)
    assert result.states == ()
    assert result.metadata["empty_input"] is True
    assert result.metadata["input_count"] == 0
    assert result.metadata["finite_count"] == 0
    assert result.metadata["invalid_count"] == 0


# ── constant input behaviour ─────────────────────────────────────────────
def test_constant_input_collapses_to_single_band() -> None:
    result = quantize_states([0.1] * 10, thresholds=_THRESHOLDS, labels=_LABELS)
    assert set(result.states) == {"neutral"}
    assert result.metadata["state_counts"]["neutral"] == 10


# ── P3: outlier behaviour (clamped to extreme bands) ─────────────────────
def test_p3_outliers_clamp_to_extreme_bands() -> None:
    result = quantize_states([-1e18, 1e18], thresholds=_THRESHOLDS, labels=_LABELS)
    assert result.states == ("low", "high")


# ── P8: metadata completeness ────────────────────────────────────────────
def test_p8_metadata_records_full_contract() -> None:
    result = _quantize([-1.0, 0.0, 1.0, float("nan")])
    required = {
        "method",
        "labels",
        "thresholds",
        "invalid_state",
        "input_count",
        "finite_count",
        "invalid_count",
        "empty_input",
        "tie_policy",
        "outlier_policy",
        "state_counts",
        "config_hash",
        "information_loss",
        "information_loss_declared",
        "claim_boundary",
        "not_financial_advice",
        "not_predictive_claim",
    }
    assert required <= set(result.metadata)
    assert result.metadata["method"] == "fixed_threshold"
    assert result.metadata["information_loss_declared"] is True
    assert result.metadata["claim_boundary"] == "descriptor_only_not_predictor"
    # counts are internally consistent
    md = result.metadata
    assert md["input_count"] == md["finite_count"] + md["invalid_count"]


# ── P9: no forecasting / trading language in output surface ──────────────
def test_p9_no_predictive_or_trading_language_in_metadata() -> None:
    forbidden = {
        "buy",
        "sell",
        "long",
        "short",
        "entry",
        "exit",
        "alpha",
        "profit",
        "trade",
        "predict",
        "forecast",
        "guaranteed",
    }
    result = _quantize([0.0, 1.0])
    # The disclaimer fields legitimately negate prediction
    # ("not_predictive_claim", "descriptor_only_not_predictor"); scanning
    # them for the substring "predict" would flag the very guarantee we want.
    disclaimer_keys = {"claim_boundary", "not_predictive_claim", "not_financial_advice"}
    blob = " ".join(
        f"{key}={value}"
        for key, value in result.metadata.items()
        if key not in disclaimer_keys
    ).lower()
    leaked = sorted(term for term in forbidden if term in blob)
    assert not leaked, f"forecasting/trading language leaked into metadata: {leaked}"
    # and the disclaimers are present and affirmative.
    assert result.metadata["not_predictive_claim"] is True
    assert result.metadata["claim_boundary"].endswith("not_predictor")


# ── P10 / fail-closed: malformed rule rejection ──────────────────────────
def test_failclosed_non_finite_threshold_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        quantize_states([0.0], thresholds=[0.0, math.inf], labels=_LABELS)


def test_failclosed_unordered_thresholds_rejected() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        quantize_states([0.0], thresholds=[0.5, -0.5], labels=_LABELS)


def test_failclosed_duplicate_thresholds_rejected() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        quantize_states([0.0], thresholds=[0.5, 0.5], labels=_LABELS)


def test_failclosed_label_cardinality_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="labels"):
        quantize_states([0.0], thresholds=_THRESHOLDS, labels=["low", "high"])


def test_failclosed_invalid_state_collision_rejected() -> None:
    with pytest.raises(ValueError, match="collide"):
        quantize_states(
            [0.0],
            thresholds=_THRESHOLDS,
            labels=_LABELS,
            invalid_state="neutral",
        )


# ── no future leakage: thresholds are caller-declared, output is per-point ─
def test_no_future_leakage_output_is_independent_of_unseen_tail() -> None:
    """A fixed-threshold rule fits nothing on the data, so the state of an
    early observation cannot depend on later (future) observations."""
    prefix = quantize_states([0.0, 0.6], thresholds=_THRESHOLDS, labels=_LABELS)
    full = quantize_states([0.0, 0.6, -3.0, 9.0], thresholds=_THRESHOLDS, labels=_LABELS)
    assert full.states[: len(prefix.states)] == prefix.states


def test_single_band_rule_no_thresholds() -> None:
    """A degenerate single-state rule (no thresholds) is valid and bounded."""
    result = quantize_states([-1.0, 5.0], thresholds=[], labels=["only"])
    assert result.states == ("only", "only")
    assert result.metadata["state_counts"] == {"only": 2}
