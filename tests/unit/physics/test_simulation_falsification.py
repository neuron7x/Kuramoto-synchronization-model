# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for INV-SIMULATION-FALSIFICATION (P1, statistical).

The simulation hypothesis is operationalized as a registry of enumerable
signatures with explicit thresholds and observation status. These tests
exercise the registry's contract — they do NOT perform any cosmological
measurement. The empirical observation status of each signature is
maintained by hand against published peer-reviewed references.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.physics.simulation_falsification import (
    CANONICAL_SIGNATURES,
    FalsificationLadder,
    FalsificationSignature,
    ObservationStatus,
    SignatureEvaluation,
    build_canonical_ladder,
    evaluate_signature_observation,
)

# ---------------------------------------------------------------------------
# Canonical ladder shape
# ---------------------------------------------------------------------------


def test_canonical_ladder_has_six_pre_registered_signatures() -> None:
    """The pre-registered ladder ships with exactly the six documented entries."""
    ladder = build_canonical_ladder()
    assert len(ladder.signatures) == 6


def test_canonical_signature_ids_are_unique() -> None:
    """No duplicate signature_id in the canonical ladder."""
    ids = [s.signature_id for s in CANONICAL_SIGNATURES]
    assert len(ids) == len(set(ids)), f"duplicate signature_ids: {ids}"


def test_canonical_signatures_carry_published_reference() -> None:
    """Every signature must cite a peer-reviewed source — no naked claims."""
    for sig in CANONICAL_SIGNATURES:
        assert sig.reference, f"{sig.signature_id} has no reference"
        assert len(sig.reference) > 20, f"{sig.signature_id} reference too terse: {sig.reference!r}"


def test_canonical_thresholds_are_finite_and_positive() -> None:
    """Detectability thresholds must be finite positive numbers."""
    for sig in CANONICAL_SIGNATURES:
        assert math.isfinite(sig.detectability_threshold)
        msg = f"{sig.signature_id} non-positive threshold {sig.detectability_threshold}"
        assert sig.detectability_threshold > 0.0, msg


def test_canonical_status_values_are_valid_enum_members() -> None:
    """Status field must be an ObservationStatus enum value, not a free string."""
    valid = set(ObservationStatus)
    for sig in CANONICAL_SIGNATURES:
        assert sig.current_observation_status in valid


# ---------------------------------------------------------------------------
# status_summary
# ---------------------------------------------------------------------------


def test_status_summary_counts_match_registry() -> None:
    """status_summary returns one bucket per ObservationStatus, totals match."""
    ladder = build_canonical_ladder()
    summary = ladder.status_summary()
    assert set(summary.keys()) == {s.value for s in ObservationStatus}
    assert sum(summary.values()) == len(ladder.signatures)


def test_status_summary_returns_zero_for_unused_buckets() -> None:
    """Custom ladder with only NOT_OBSERVED entries reports zero elsewhere."""
    custom = FalsificationLadder(
        signatures=(
            FalsificationSignature(
                signature_id="TEST-A",
                name="A",
                prediction_under_simulation="x",
                detectability_threshold=1.0,
                detectability_units="u",
                current_observation_status=ObservationStatus.NOT_OBSERVED,
                current_observation_value=None,
                reference="ref",
                reasoning_tier="DERIVED",
            ),
        )
    )
    summary = custom.status_summary()
    assert summary["NOT_OBSERVED"] == 1
    assert summary["OPEN"] == 0
    assert summary["RULED_OUT"] == 0


# ---------------------------------------------------------------------------
# signature_by_id and rule_out
# ---------------------------------------------------------------------------


def test_signature_by_id_returns_canonical_entry() -> None:
    """Lookup by id returns the matching canonical signature."""
    ladder = build_canonical_ladder()
    sig = ladder.signature_by_id("SIM-HOLOGRAPHIC-SATURATION")
    assert sig.signature_id == "SIM-HOLOGRAPHIC-SATURATION"


def test_signature_by_id_unknown_raises_key_error() -> None:
    """Unknown signature_id is fail-closed: KeyError, not None."""
    ladder = build_canonical_ladder()
    with pytest.raises(KeyError):
        ladder.signature_by_id("SIM-DOES-NOT-EXIST")


def test_hardware_class_ruled_out_when_observed_above_threshold() -> None:
    """observed > threshold ⇒ hardware-class predicting <threshold is ruled out."""
    ladder = build_canonical_ladder()
    sig = ladder.signature_by_id("SIM-HOLOGRAPHIC-SATURATION")
    above = sig.detectability_threshold * 2.0
    assert ladder.hardware_class_ruled_out("SIM-HOLOGRAPHIC-SATURATION", above) is True


def test_hardware_class_not_ruled_out_when_observed_below_threshold() -> None:
    """observed <= threshold ⇒ no rule-out (consistent with simulation)."""
    ladder = build_canonical_ladder()
    sig = ladder.signature_by_id("SIM-HOLOGRAPHIC-SATURATION")
    below = sig.detectability_threshold * 0.5
    assert ladder.hardware_class_ruled_out("SIM-HOLOGRAPHIC-SATURATION", below) is False


def test_hardware_class_at_exact_threshold_not_ruled_out() -> None:
    """observed == threshold is the boundary; strict > required to rule out."""
    ladder = build_canonical_ladder()
    sig = ladder.signature_by_id("SIM-HOLOGRAPHIC-SATURATION")
    assert (
        ladder.hardware_class_ruled_out("SIM-HOLOGRAPHIC-SATURATION", sig.detectability_threshold)
        is False
    )


def test_hardware_class_ruled_out_non_finite_observed_raises() -> None:
    """NaN / Inf observation is fail-closed (INV-HPC2)."""
    ladder = build_canonical_ladder()
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            ladder.hardware_class_ruled_out("SIM-HOLOGRAPHIC-SATURATION", bad)


def test_hardware_class_ruled_out_unknown_signature_raises() -> None:
    """KeyError, not silent False, on unknown signature_id."""
    ladder = build_canonical_ladder()
    with pytest.raises(KeyError):
        ladder.hardware_class_ruled_out("SIM-DOES-NOT-EXIST", 1.0)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_signature_dataclass_is_frozen() -> None:
    """FalsificationSignature is frozen — fields cannot be mutated post-construction."""
    sig = CANONICAL_SIGNATURES[0]
    with pytest.raises(AttributeError):
        sig.detectability_threshold = 0.0  # type: ignore[misc]


def test_ladder_dataclass_is_frozen() -> None:
    """FalsificationLadder is frozen — signatures tuple is immutable."""
    ladder = build_canonical_ladder()
    with pytest.raises(AttributeError):
        ladder.signatures = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


@given(observed=st.floats(allow_nan=False, allow_infinity=False))
def test_property_rule_out_iff_strictly_above_threshold(observed: float) -> None:
    """Property: rule_out is the boolean (observed > threshold) for any
    finite observation — no hidden tolerance, no silent clamp."""
    ladder = build_canonical_ladder()
    sig = ladder.signature_by_id("SIM-HOLOGRAPHIC-SATURATION")
    expected = observed > sig.detectability_threshold
    actual = ladder.hardware_class_ruled_out("SIM-HOLOGRAPHIC-SATURATION", observed)
    assert actual is expected


# ---------------------------------------------------------------------------
# reasoning_tier (inference flaw #6 — DERIVED vs ANALOGICAL gap)
# ---------------------------------------------------------------------------


_VALID_TIERS: frozenset[str] = frozenset({"DERIVED", "ANALOGICAL"})


def test_each_canonical_signature_has_valid_reasoning_tier() -> None:
    """Every canonical signature must carry a valid reasoning_tier label."""
    for sig in CANONICAL_SIGNATURES:
        msg = f"{sig.signature_id} has invalid reasoning_tier {sig.reasoning_tier!r}"
        assert sig.reasoning_tier in _VALID_TIERS, msg


def test_canonical_distribution_is_4_derived_2_analogical() -> None:
    """Pre-registered tier distribution: 4 DERIVED + 2 ANALOGICAL.

    Changing this count is a contract change and must be accompanied by a
    documented justification in INVARIANTS.yaml under
    `simulation_falsification.statement`.
    """
    derived = [s for s in CANONICAL_SIGNATURES if s.reasoning_tier == "DERIVED"]
    analogical = [s for s in CANONICAL_SIGNATURES if s.reasoning_tier == "ANALOGICAL"]
    assert len(derived) == 4, [s.signature_id for s in derived]
    assert len(analogical) == 2, [s.signature_id for s in analogical]
    assert {s.signature_id for s in analogical} == {
        "SIM-HOLOGRAPHIC-SATURATION",
        "SIM-COMPUTE-COMPLEXITY-WALL",
    }


def test_signatures_by_tier_buckets_correctly() -> None:
    """signatures_by_tier exposes both buckets with correct counts and content."""
    ladder = build_canonical_ladder()
    buckets = ladder.signatures_by_tier()
    assert set(buckets.keys()) == _VALID_TIERS
    assert len(buckets["DERIVED"]) == 4
    assert len(buckets["ANALOGICAL"]) == 2
    # Round-trip: every signature appears in exactly one bucket.
    union_ids = {s.signature_id for s in buckets["DERIVED"]} | {
        s.signature_id for s in buckets["ANALOGICAL"]
    }
    assert union_ids == {s.signature_id for s in CANONICAL_SIGNATURES}
    assert len(union_ids) == len(CANONICAL_SIGNATURES)


# ---------------------------------------------------------------------------
# Point-eval bridge (Task 5) — evaluate_signature_observation
# ---------------------------------------------------------------------------


def test_point_eval_below_threshold_does_not_rule_out() -> None:
    """observed < threshold ⇒ hardware_class_ruled_out is False; no reason."""
    sig = next(s for s in CANONICAL_SIGNATURES if s.signature_id == "SIM-HOLOGRAPHIC-SATURATION")
    eval_result = evaluate_signature_observation(
        "SIM-HOLOGRAPHIC-SATURATION",
        sig.detectability_threshold * 0.5,
    )
    assert isinstance(eval_result, SignatureEvaluation)
    assert eval_result.signature_id == "SIM-HOLOGRAPHIC-SATURATION"
    assert eval_result.hardware_class_ruled_out is False
    assert eval_result.reason is None


def test_point_eval_at_exact_threshold_does_not_rule_out() -> None:
    """Boundary case: observed == threshold. Per ladder contract
    (hardware_class_ruled_out uses strict >), equality does NOT rule out."""
    sig = next(s for s in CANONICAL_SIGNATURES if s.signature_id == "SIM-HOLOGRAPHIC-SATURATION")
    eval_result = evaluate_signature_observation(
        "SIM-HOLOGRAPHIC-SATURATION",
        sig.detectability_threshold,
    )
    assert eval_result.hardware_class_ruled_out is False
    assert eval_result.reason is None


def test_point_eval_above_threshold_rules_out_with_reason() -> None:
    """observed > threshold ⇒ ruled_out True with quantitative reason."""
    sig = next(s for s in CANONICAL_SIGNATURES if s.signature_id == "SIM-HOLOGRAPHIC-SATURATION")
    eval_result = evaluate_signature_observation(
        "SIM-HOLOGRAPHIC-SATURATION",
        sig.detectability_threshold * 2.0,
    )
    assert eval_result.hardware_class_ruled_out is True
    assert eval_result.reason is not None
    assert "exceeds detectability threshold" in eval_result.reason
    assert "SIM-HOLOGRAPHIC-SATURATION" in eval_result.reason


def test_point_eval_non_finite_observed_value_raises() -> None:
    """NaN / ±Inf must be rejected before producing any verdict."""
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            evaluate_signature_observation("SIM-HOLOGRAPHIC-SATURATION", bad)


def test_point_eval_unknown_signature_id_raises() -> None:
    """KeyError, not silent SignatureEvaluation, on unknown signature."""
    with pytest.raises(KeyError):
        evaluate_signature_observation("SIM-DOES-NOT-EXIST", 1.0)


def test_point_eval_preserves_derived_reasoning_tier() -> None:
    """DERIVED signatures evaluate with reasoning_tier='DERIVED' in result."""
    eval_result = evaluate_signature_observation(
        "SIM-LATTICE-UHECR",
        observed_value=1.0,
    )
    assert eval_result.reasoning_tier == "DERIVED"


def test_point_eval_preserves_analogical_reasoning_tier() -> None:
    """ANALOGICAL signatures evaluate with reasoning_tier='ANALOGICAL'."""
    eval_result = evaluate_signature_observation(
        "SIM-HOLOGRAPHIC-SATURATION",
        observed_value=0.0,
    )
    assert eval_result.reasoning_tier == "ANALOGICAL"


def test_point_eval_preserves_observation_status() -> None:
    """Result carries the registry's current_observation_status verbatim;
    point evaluation does NOT mutate the ladder."""
    eval_result = evaluate_signature_observation("SIM-LATTICE-UHECR", 0.0)
    sig = next(s for s in CANONICAL_SIGNATURES if s.signature_id == "SIM-LATTICE-UHECR")
    assert eval_result.observation_status == sig.current_observation_status


def test_point_eval_does_not_aggregate_across_signatures() -> None:
    """Sanity: the function returns ONE SignatureEvaluation, never a
    composite. There is no API path that turns multiple point evals
    into a global simulation verdict."""
    # Type assertion + pinning the return shape.
    eval_result = evaluate_signature_observation("SIM-LATTICE-UHECR", 0.0)
    assert isinstance(eval_result, SignatureEvaluation)
    fields = {f.name for f in SignatureEvaluation.__dataclass_fields__.values()}
    assert fields == {
        "signature_id",
        "reasoning_tier",
        "observation_status",
        "detectability_threshold",
        "detectability_units",
        "observed_value",
        "hardware_class_ruled_out",
        "reason",
    }


def test_point_eval_registry_order_unchanged_after_evaluation() -> None:
    """Registry order is invariant; point evaluation is read-only."""
    before = tuple(s.signature_id for s in CANONICAL_SIGNATURES)
    _ = evaluate_signature_observation("SIM-LATTICE-UHECR", 0.0)
    _ = evaluate_signature_observation("SIM-HOLOGRAPHIC-SATURATION", 0.0)
    after = tuple(s.signature_id for s in CANONICAL_SIGNATURES)
    assert before == after


def test_point_eval_signature_evaluation_is_frozen() -> None:
    """SignatureEvaluation is immutable post-construction."""
    eval_result = evaluate_signature_observation("SIM-LATTICE-UHECR", 0.0)
    with pytest.raises(AttributeError):
        eval_result.hardware_class_ruled_out = True  # type: ignore[misc]


def test_point_eval_accepts_custom_ladder() -> None:
    """Optional `ladder` argument allows evaluating against a non-canonical
    ladder without monkey-patching CANONICAL_SIGNATURES."""
    custom = FalsificationLadder(
        signatures=(CANONICAL_SIGNATURES[0],),  # subset
    )
    sig = CANONICAL_SIGNATURES[0]
    eval_result = evaluate_signature_observation(
        sig.signature_id,
        observed_value=sig.detectability_threshold + 0.1,
        ladder=custom,
    )
    assert eval_result.signature_id == sig.signature_id
    assert eval_result.hardware_class_ruled_out is True
