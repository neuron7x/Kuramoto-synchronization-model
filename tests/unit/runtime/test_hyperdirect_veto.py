from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from runtime.hyperdirect_veto import (
    HyperdirectConfig,
    HyperdirectVeto,
    HyperdirectVetoError,
    VetoDecision,
)

# --------------------------------------------------------------------------
# HDV-001 / HDV-002: disjunctive single-channel STOP (the core property)
# --------------------------------------------------------------------------


def test_single_channel_stop_cannot_be_laundered_by_strong_evidence() -> None:
    """One saturated red flag vetoes regardless of how strong the margin is.

    This is the whole reason the primitive exists: a single conflict
    channel at the ceiling must not be averaged away by an otherwise
    excellent claim.
    """
    gate = HyperdirectVeto()
    decision = gate.evaluate({"falsifier_disagreement": 0.9}, evidence_margin=1e9)
    assert decision.passed is False
    assert decision.reason == "single_channel_stop:falsifier_disagreement"
    assert decision.vetoing_channel == "falsifier_disagreement"


def test_veto_uses_max_not_mean() -> None:
    """mean({0.9, 0.0, 0.0}) = 0.3 but max = 0.9 — must veto."""
    gate = HyperdirectVeto()
    decision = gate.evaluate({"a": 0.9, "b": 0.0, "c": 0.0}, evidence_margin=1e9)
    assert decision.passed is False
    assert decision.vetoing_channel == "a"
    assert decision.c_max == pytest.approx(0.9)
    assert decision.c_aggregate == pytest.approx(0.3)


def test_channel_exactly_at_ceiling_vetoes() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(hard_ceiling=0.8))
    decision = gate.evaluate({"x": 0.8}, evidence_margin=1e9)
    assert decision.passed is False
    assert decision.reason == "single_channel_stop:x"


# --------------------------------------------------------------------------
# HDV-003: conflict-proportional decision threshold (deterministic, not RNG)
# --------------------------------------------------------------------------


def test_required_margin_rises_with_aggregate_conflict() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(base_margin=0.1, conflict_gain=1.0))
    low = gate.evaluate({"a": 0.1, "b": 0.1}, evidence_margin=0.5)
    high = gate.evaluate({"a": 0.5, "b": 0.5}, evidence_margin=0.5)
    assert high.required_margin > low.required_margin
    assert low.required_margin == pytest.approx(0.1 + 1.0 * 0.1)
    assert high.required_margin == pytest.approx(0.1 + 1.0 * 0.5)


def test_insufficient_margin_under_conflict_vetoes() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    decision = gate.evaluate({"a": 0.4, "b": 0.4}, evidence_margin=0.3)
    assert decision.passed is False
    assert decision.reason == "insufficient_margin_under_conflict"
    assert decision.vetoing_channel is None


def test_sufficient_margin_clears() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    decision = gate.evaluate({"a": 0.4, "b": 0.4}, evidence_margin=0.5)
    assert decision.passed is True
    assert decision.reason == "cleared"


def test_margin_exactly_at_required_passes() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(base_margin=0.0, conflict_gain=1.0))
    # aggregate = 0.2, required = 0.2, margin = 0.2 -> not (0.2 < 0.2) -> pass
    decision = gate.evaluate({"a": 0.2, "b": 0.2}, evidence_margin=0.2)
    assert decision.passed is True


def test_single_channel_stop_takes_precedence_over_margin_check() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(hard_ceiling=0.8, conflict_gain=1.0))
    decision = gate.evaluate({"a": 0.9, "b": 0.0}, evidence_margin=1e9)
    assert decision.reason.startswith("single_channel_stop")


def test_negative_margin_cannot_pass() -> None:
    """Null beat the hypothesis -> margin negative -> never clears base."""
    gate = HyperdirectVeto(HyperdirectConfig(base_margin=0.0, conflict_gain=0.0))
    decision = gate.evaluate({}, evidence_margin=-0.01)
    assert decision.passed is False
    assert decision.reason == "insufficient_margin_under_conflict"


# --------------------------------------------------------------------------
# HDV-006: empty conflict is a valid "no residual conflict" state
# --------------------------------------------------------------------------


def test_empty_conflict_still_requires_base_margin() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(base_margin=0.5, conflict_gain=1.0))
    assert gate.evaluate({}, evidence_margin=0.4).passed is False
    cleared = gate.evaluate({}, evidence_margin=0.6)
    assert cleared.passed is True
    assert cleared.c_max == 0.0
    assert cleared.c_aggregate == 0.0


# --------------------------------------------------------------------------
# Determinism (no clock, no RNG, no state)
# --------------------------------------------------------------------------


def test_repeated_evaluation_is_identical() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    first = gate.evaluate({"a": 0.3, "b": 0.6}, evidence_margin=0.42)
    for _ in range(50):
        again = gate.evaluate({"a": 0.3, "b": 0.6}, evidence_margin=0.42)
        assert again == first


# --------------------------------------------------------------------------
# HDV-004 / HDV-005: fail-closed input validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        cast(Any, None),
        cast(Any, [("a", 0.1)]),
        cast(Any, "not-a-mapping"),
    ],
)
def test_non_mapping_conflict_fails_closed(bad: Any) -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate(bad, evidence_margin=0.0)


@pytest.mark.parametrize("value", [-0.01, 1.01, 2.0])
def test_channel_out_of_unit_range_fails_closed(value: float) -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({"a": value}, evidence_margin=0.0)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_channel_fails_closed(value: float) -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({"a": value}, evidence_margin=0.0)


def test_bool_channel_value_fails_closed() -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({"a": cast(Any, True)}, evidence_margin=0.0)


def test_non_string_or_empty_channel_name_fails_closed() -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({cast(Any, 1): 0.1}, evidence_margin=0.0)
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({"": 0.1}, evidence_margin=0.0)


@pytest.mark.parametrize("margin", [math.nan, math.inf, -math.inf, cast(Any, True), cast(Any, "x")])
def test_non_finite_or_non_real_margin_fails_closed(margin: Any) -> None:
    with pytest.raises(HyperdirectVetoError):
        HyperdirectVeto().evaluate({"a": 0.1}, evidence_margin=margin)


# --------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        HyperdirectConfig(hard_ceiling=0.0),
        HyperdirectConfig(hard_ceiling=1.01),
        HyperdirectConfig(base_margin=-0.1),
        HyperdirectConfig(conflict_gain=-1.0),
        HyperdirectConfig(base_margin=math.inf),
        HyperdirectConfig(conflict_gain=math.inf),
    ],
)
def test_invalid_config_rejected(config: HyperdirectConfig) -> None:
    with pytest.raises(ValueError):
        HyperdirectVeto(config)


def test_ceiling_at_one_is_valid() -> None:
    gate = HyperdirectVeto(HyperdirectConfig(hard_ceiling=1.0))
    assert gate.evaluate({"a": 1.0}, evidence_margin=1e9).passed is False
    assert gate.evaluate({"a": 0.99}, evidence_margin=1e9).passed is True


# --------------------------------------------------------------------------
# HDV-008: immutability
# --------------------------------------------------------------------------


def test_decision_is_frozen() -> None:
    decision = HyperdirectVeto().evaluate({"a": 0.1}, evidence_margin=1.0)
    with pytest.raises(FrozenInstanceError):
        cast(Any, decision).passed = True


def test_conflict_vector_is_read_only() -> None:
    decision = HyperdirectVeto().evaluate({"a": 0.1}, evidence_margin=1.0)
    assert isinstance(decision, VetoDecision)
    with pytest.raises(TypeError):
        cast(Any, decision.conflict_vector)["a"] = 0.9
