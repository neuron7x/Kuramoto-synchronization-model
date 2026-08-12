# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the executable claim-maturity ladder.

Covers the maturity-promotion contract: determinism, single-rung and
multi-rung allowed promotions, blocked promotions with preserved
negative-evidence ledger, the no-skip rule, the three hard governance
rules (no real-data rung without a real-data artifact + provenance, no
ALTERNATIVES_ELIMINATED without null + simpler-baseline comparison, no
BOUNDED_CLAIM_ALLOWED without the replay/provenance/falsifier/negative-
evidence conjunction), fail-closed rejection of unknown states, non-upward
targets, and unknown evidence tokens, and the descriptor-only boundary on
every verdict.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from analytics.signals.claim_maturity import (
    CLAIM_BOUNDARY,
    EVIDENCE_REQUIREMENTS,
    EVIDENCE_VOCABULARY,
    LADDER,
    PromotionVerdict,
    evaluate_promotion,
)

# Every evidence token in the vocabulary — a fully-evidenced claim.
_ALL_EVIDENCE = set(EVIDENCE_VOCABULARY)


def _evidence_through(target: str) -> set[str]:
    """Union of evidence required by every rung up to and including target."""
    idx = LADDER.index(target)
    tokens: set[str] = set()
    for rung in LADDER[: idx + 1]:
        tokens.update(EVIDENCE_REQUIREMENTS[rung])
    return tokens


# ── structural sanity ────────────────────────────────────────────────────
def test_ladder_has_fourteen_unique_rungs() -> None:
    assert len(LADDER) == 14
    assert len(set(LADDER)) == 14
    assert LADDER[0] == "UNOBSERVED"
    assert LADDER[-1] == "BOUNDED_CLAIM_ALLOWED"


# ── determinism ──────────────────────────────────────────────────────────
def test_deterministic_for_same_arguments() -> None:
    a = evaluate_promotion("UNOBSERVED", "BOUNDED_CLAIM_ALLOWED", _ALL_EVIDENCE)
    b = evaluate_promotion("UNOBSERVED", "BOUNDED_CLAIM_ALLOWED", _ALL_EVIDENCE)
    assert a == b
    assert a.as_dict() == b.as_dict()


def test_missing_evidence_is_sorted() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "BOUNDED_CLAIM_ALLOWED", set())
    assert list(verdict.missing_evidence) == sorted(verdict.missing_evidence)


# ── allowed promotions ───────────────────────────────────────────────────
def test_single_rung_promotion_allowed_with_its_evidence() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "OBSERVABLE", {"observability"})
    assert verdict.allowed is True
    assert verdict.blocked_at is None
    assert verdict.missing_evidence == ()
    assert verdict.satisfied_rungs == ("OBSERVABLE",)


def test_full_ladder_promotion_allowed_with_all_evidence() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "BOUNDED_CLAIM_ALLOWED", _ALL_EVIDENCE)
    assert verdict.allowed is True
    assert verdict.blocked_at is None
    # every rung above the base is satisfied
    assert verdict.satisfied_rungs == LADDER[1:]


def test_mid_ladder_promotion_allowed() -> None:
    evidence = _evidence_through("CALIBRATED")
    verdict = evaluate_promotion("DISCRIMINATING_TEST_DEFINED", "CALIBRATED", evidence)
    assert verdict.allowed is True
    assert verdict.satisfied_rungs == ("FALSIFIER_EXECUTED", "CALIBRATED")


# ── blocked promotions (negative evidence preserved) ─────────────────────
def test_blocked_when_intermediate_rung_evidence_missing() -> None:
    # Aim for REAL_DATA_SINGLE_SESSION but withhold the calibration record.
    evidence = _evidence_through("REAL_DATA_SINGLE_SESSION") - {"calibration_record"}
    verdict = evaluate_promotion("UNOBSERVED", "REAL_DATA_SINGLE_SESSION", evidence)
    assert verdict.allowed is False
    assert verdict.blocked_at == "CALIBRATED"
    assert ("CALIBRATED", "calibration_record") in verdict.missing_evidence


def test_blocked_promotion_preserves_every_gap() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "FALSIFIER_EXECUTED", set())
    # rungs OBSERVABLE..FALSIFIER_EXECUTED each contribute their unmet token
    blocked_states = {state for state, _ in verdict.missing_evidence}
    assert blocked_states == {
        "OBSERVABLE",
        "MEASURED_SYNTHETIC",
        "ALTERNATIVES_ENUMERATED",
        "DISCRIMINATING_TEST_DEFINED",
        "FALSIFIER_EXECUTED",
    }
    assert verdict.allowed is False


# ── hard rule 1: no real-data rung without artifact + provenance ─────────
def test_real_data_single_session_requires_artifact_and_provenance() -> None:
    base = _evidence_through("REPLAYABLE")
    # artifact present, provenance withheld → blocked
    verdict = evaluate_promotion(
        "REPLAYABLE", "REAL_DATA_SINGLE_SESSION", base | {"real_data_artifact"}
    )
    assert verdict.allowed is False
    assert ("REAL_DATA_SINGLE_SESSION", "provenance") in verdict.missing_evidence
    # both present → allowed
    ok = evaluate_promotion(
        "REPLAYABLE", "REAL_DATA_SINGLE_SESSION", base | {"real_data_artifact", "provenance"}
    )
    assert ok.allowed is True


# ── hard rule 2: alternatives-eliminated needs null + simpler baseline ───
def test_alternatives_eliminated_requires_null_and_simpler_baseline() -> None:
    base = _evidence_through("REAL_DATA_MULTI_SESSION")
    # only null comparison, no simpler baseline → blocked
    verdict = evaluate_promotion(
        "REAL_DATA_MULTI_SESSION", "ALTERNATIVES_ELIMINATED", base | {"null_comparison"}
    )
    assert verdict.allowed is False
    assert ("ALTERNATIVES_ELIMINATED", "simpler_baseline_comparison") in verdict.missing_evidence


# ── hard rule 3: bounded claim conjunction ───────────────────────────────
def test_bounded_claim_requires_full_conjunction() -> None:
    # Everything to reach NEGATIVE_EVIDENCE_PRESERVED, then drop the falsifier
    # so the top-rung conjunction (replay+provenance+falsifier+neg-evidence)
    # fails even though the lower rungs were once cleared.
    evidence = _ALL_EVIDENCE - {"falsifier_executed"}
    verdict = evaluate_promotion("NEGATIVE_EVIDENCE_PRESERVED", "BOUNDED_CLAIM_ALLOWED", evidence)
    assert verdict.allowed is False
    assert ("BOUNDED_CLAIM_ALLOWED", "falsifier_executed") in verdict.missing_evidence


def test_bounded_claim_allowed_with_full_conjunction() -> None:
    evidence = {"replay_digest", "provenance", "falsifier_executed", "negative_evidence_path"}
    verdict = evaluate_promotion("NEGATIVE_EVIDENCE_PRESERVED", "BOUNDED_CLAIM_ALLOWED", evidence)
    assert verdict.allowed is True
    assert verdict.satisfied_rungs == ("BOUNDED_CLAIM_ALLOWED",)


# ── fail-closed: invalid skip / states / evidence ────────────────────────
def test_failclosed_unknown_current_state() -> None:
    with pytest.raises(ValueError, match="ladder states"):
        evaluate_promotion("NOT_A_STATE", "OBSERVABLE", {"observability"})


def test_failclosed_unknown_target_state() -> None:
    with pytest.raises(ValueError, match="ladder states"):
        evaluate_promotion("UNOBSERVED", "MATURE_ENOUGH", set())


def test_failclosed_non_upward_target_rejected() -> None:
    # equal
    with pytest.raises(ValueError, match="strictly up"):
        evaluate_promotion("CALIBRATED", "CALIBRATED", _ALL_EVIDENCE)
    # downward
    with pytest.raises(ValueError, match="strictly up"):
        evaluate_promotion("CALIBRATED", "OBSERVABLE", _ALL_EVIDENCE)


def test_failclosed_unknown_evidence_token() -> None:
    with pytest.raises(ValueError, match="unknown evidence token"):
        evaluate_promotion("UNOBSERVED", "OBSERVABLE", {"observability", "replay_diget"})


def test_failclosed_evidence_as_string_rejected() -> None:
    with pytest.raises(ValueError, match="collection of tokens, not a string"):
        evaluate_promotion("UNOBSERVED", "OBSERVABLE", cast(Any, "observability"))


# ── boundary disclaimer + immutability ───────────────────────────────────
def test_claim_boundary_present_on_every_verdict() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "OBSERVABLE", {"observability"})
    assert verdict.claim_boundary == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert verdict.as_dict()["claim_boundary"] == "descriptor_only_not_predictor"


def test_verdict_is_frozen() -> None:
    verdict = evaluate_promotion("UNOBSERVED", "OBSERVABLE", {"observability"})
    assert isinstance(verdict, PromotionVerdict)
    with pytest.raises(AttributeError):
        cast(Any, verdict).allowed = True
