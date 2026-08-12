from __future__ import annotations

from typing import Any, cast

import pytest

from runtime.hyperdirect_veto import HyperdirectConfig, HyperdirectVetoError
from runtime.hyperdirect_veto_falsifier import run_battery
from runtime.inference_promotion_brake import (
    InferenceClaim,
    InferencePromotionBrake,
    PromotionVerdict,
)


def test_strong_claim_low_conflict_promotes() -> None:
    brake = InferencePromotionBrake(HyperdirectConfig(conflict_gain=1.0))
    claim = InferenceClaim(
        hypothesis_score=0.9,
        null_scores=[0.3, 0.4, 0.35],
        falsifier_disagreement=0.05,
        witness_uncertainty=0.0,
    )
    verdict = brake.assess(claim)
    assert isinstance(verdict, PromotionVerdict)
    assert verdict.promote is True
    assert verdict.advisory is True
    assert verdict.evidence_margin == pytest.approx(0.5)


def test_single_saturated_residual_channel_vetoes_despite_huge_margin() -> None:
    brake = InferencePromotionBrake()
    claim = InferenceClaim(
        hypothesis_score=1e9,
        null_scores=[0.0],
        falsifier_disagreement=0.95,
    )
    verdict = brake.assess(claim)
    assert verdict.promote is False
    assert verdict.decision.reason.startswith("single_channel_stop")


def test_null_beating_hypothesis_cannot_promote() -> None:
    brake = InferencePromotionBrake(HyperdirectConfig(conflict_gain=0.0))
    claim = InferenceClaim(hypothesis_score=0.2, null_scores=[0.5])
    verdict = brake.assess(claim)
    assert verdict.evidence_margin == pytest.approx(-0.3)
    assert verdict.promote is False


def test_absent_channels_are_not_invented() -> None:
    brake = InferencePromotionBrake(HyperdirectConfig(conflict_gain=1.0))
    claim = InferenceClaim(hypothesis_score=0.6, null_scores=[0.1])
    verdict = brake.assess(claim)
    # No conflict channels supplied -> empty conflict vector, not zeros.
    assert dict(verdict.decision.conflict_vector) == {}
    assert verdict.promote is True


def test_empty_nulls_fail_closed() -> None:
    brake = InferencePromotionBrake()
    with pytest.raises(HyperdirectVetoError):
        brake.assess(InferenceClaim(hypothesis_score=1.0, null_scores=[]))


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_score_fails_closed(bad: float) -> None:
    brake = InferencePromotionBrake()
    with pytest.raises(HyperdirectVetoError):
        brake.assess(InferenceClaim(hypothesis_score=bad, null_scores=[0.1]))
    with pytest.raises(HyperdirectVetoError):
        brake.assess(InferenceClaim(hypothesis_score=0.5, null_scores=[bad]))


@pytest.mark.parametrize("truthy", [True, False])
def test_boolean_score_fails_closed(truthy: bool) -> None:
    """`isinstance(value, bool) or not isinstance(value, Real)` — the bool clause is the whole
    point of the guard, and nothing exercised it.

    A mutation probe left `Or -> And` alive on this line. Under that mutant the guard never
    fires for a bool, because `bool` IS a `numbers.Real` subclass — so `not isinstance(True,
    Real)` is False and the conjunction is always False. The effect is that `True` would be
    accepted as an evidence score worth 1.0 and `False` as 0.0, silently, on the brake that
    decides whether an inference may be promoted. A P0 fail-closed guard that no test can
    make fire is not a guard.
    """
    brake = InferencePromotionBrake()
    with pytest.raises(HyperdirectVetoError):
        brake.assess(InferenceClaim(hypothesis_score=truthy, null_scores=[0.1]))
    with pytest.raises(HyperdirectVetoError):
        brake.assess(InferenceClaim(hypothesis_score=0.5, null_scores=[truthy]))


def test_out_of_range_residual_channel_fails_closed() -> None:
    brake = InferencePromotionBrake()
    with pytest.raises(HyperdirectVetoError):
        brake.assess(
            InferenceClaim(
                hypothesis_score=0.9,
                null_scores=[0.1],
                purpose_drift=1.5,
            )
        )


def test_non_claim_input_fails_closed() -> None:
    brake = InferencePromotionBrake()
    with pytest.raises(HyperdirectVetoError):
        brake.assess(cast(Any, {"hypothesis_score": 1.0}))


def test_verdict_is_immutable() -> None:
    brake = InferencePromotionBrake()
    verdict = brake.assess(InferenceClaim(hypothesis_score=0.9, null_scores=[0.1]))
    with pytest.raises(Exception):
        cast(Any, verdict).promote = False


def test_assessment_is_deterministic() -> None:
    brake = InferencePromotionBrake(HyperdirectConfig(conflict_gain=1.3))
    claim = InferenceClaim(
        hypothesis_score=0.55,
        null_scores=[0.2, 0.31],
        falsifier_disagreement=0.2,
        purpose_drift=0.15,
    )
    first = brake.assess(claim)
    for _ in range(25):
        assert brake.assess(claim) == first


# --------------------------------------------------------------------------
# The adversarial reverse pass must hold no broken invariant. Documented
# boundaries (A2 channel-split) are allowed; broken invariants are not.
# --------------------------------------------------------------------------


def test_falsifier_battery_has_no_broken_invariant() -> None:
    results = run_battery()
    broken = [r.rung for r in results if r.broken]
    assert broken == [], f"falsifier broke invariants: {broken}"
    # A2 is the known, deliberately-surfaced boundary.
    boundaries = {r.rung for r in results if r.boundary}
    assert boundaries <= {"A2-channel-split"}
