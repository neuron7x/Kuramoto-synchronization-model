# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the executable resolution auditor.

Covers the resolution-discipline contract: determinism for identical
metadata, the three verdict regimes (sufficient / insufficient / unknown),
correct ratio derivation, per-dimension blocked-claim reporting,
preservation of blocked claims as negative evidence under an unknown
verdict, fail-closed rejection of missing / malformed / inconsistent
metadata, the not-applicable graph dimension, and the descriptor-only
boundary disclaimer on every verdict.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from analytics.signals.resolution_auditor import (
    CLAIM_BOUNDARY,
    MIN_INPUT_COUNT,
    ResolutionAudit,
    audit_resolution,
)


def _sufficient_meta(**overrides: Any) -> dict[str, Any]:
    """A metadata record that passes every resolution floor by default."""
    meta: dict[str, Any] = {
        "input_count": 256,
        "finite_count": 256,
        "invalid_count": 0,
        "session_count": 3,
        "temporal_resolution": "1min",
        "replayable": True,
        "artifact_complete": True,
        "graph_density": 0.5,
    }
    meta.update(overrides)
    return meta


# ── determinism ──────────────────────────────────────────────────────────
def test_p1_deterministic_for_same_metadata() -> None:
    a = audit_resolution(_sufficient_meta())
    b = audit_resolution(_sufficient_meta())
    assert a == b
    assert a.as_dict() == b.as_dict()


def test_blocked_claims_are_sorted_and_stable() -> None:
    # Two failing dimensions delivered in a metadata dict — order of the
    # report must be sorted, not insertion- or dict-order dependent.
    verdict = audit_resolution(
        _sufficient_meta(input_count=4, finite_count=4, invalid_count=0, replayable=False)
    )
    assert verdict.blocked_claims == ("input_depth", "replayability")
    assert list(verdict.blocked_claims) == sorted(verdict.blocked_claims)


# ── sufficient ───────────────────────────────────────────────────────────
def test_sufficient_when_every_floor_cleared() -> None:
    verdict = audit_resolution(_sufficient_meta())
    assert verdict.resolution_status == "sufficient"
    assert verdict.blocked_claims == ()
    assert verdict.finite_ratio == 1.0
    assert verdict.invalid_ratio == 0.0


def test_graph_density_none_is_not_applicable_not_a_block() -> None:
    # A non-graph descriptor (graph_density=None) must still be able to
    # reach "sufficient": the dimension is skipped, not failed.
    verdict = audit_resolution(_sufficient_meta(graph_density=None))
    assert verdict.graph_density is None
    assert verdict.resolution_status == "sufficient"
    assert "graph_density" not in verdict.blocked_claims


# ── insufficient (negative evidence preserved per dimension) ─────────────
def test_insufficient_on_shallow_input_depth() -> None:
    verdict = audit_resolution(
        _sufficient_meta(input_count=MIN_INPUT_COUNT - 1, finite_count=MIN_INPUT_COUNT - 1, invalid_count=0)
    )
    assert verdict.resolution_status == "insufficient"
    assert "input_depth" in verdict.blocked_claims


def test_insufficient_on_high_invalid_ratio() -> None:
    # 200 finite + 56 invalid = 256 total => invalid_ratio ~0.219 > 0.05.
    verdict = audit_resolution(_sufficient_meta(finite_count=200, invalid_count=56))
    assert verdict.resolution_status == "insufficient"
    assert "invalid_ratio" in verdict.blocked_claims
    assert "finite_ratio" in verdict.blocked_claims
    assert verdict.invalid_ratio is not None and verdict.invalid_ratio > 0.05


def test_insufficient_on_missing_replay_and_provenance() -> None:
    verdict = audit_resolution(_sufficient_meta(replayable=False, artifact_complete=False))
    assert verdict.resolution_status == "insufficient"
    assert "replayability" in verdict.blocked_claims
    assert "artifact_completeness" in verdict.blocked_claims


def test_insufficient_on_degenerate_graph_density() -> None:
    verdict = audit_resolution(_sufficient_meta(graph_density=0.0))
    assert verdict.resolution_status == "insufficient"
    assert "graph_density" in verdict.blocked_claims


# ── unknown (dominates; still preserves negative evidence) ───────────────
def test_unknown_when_no_samples() -> None:
    verdict = audit_resolution(
        _sufficient_meta(input_count=0, finite_count=0, invalid_count=0)
    )
    assert verdict.resolution_status == "unknown"
    assert verdict.finite_ratio is None
    assert verdict.invalid_ratio is None
    # input_depth still fails and is preserved as negative evidence.
    assert "input_depth" in verdict.blocked_claims


def test_unknown_when_temporal_cadence_undeclared() -> None:
    verdict = audit_resolution(_sufficient_meta(temporal_resolution="unknown"))
    assert verdict.resolution_status == "unknown"
    # Every other floor is cleared, so no dimension blocks — but the verdict
    # is still "unknown" because the cadence is undeclared.
    assert verdict.blocked_claims == ()


def test_unknown_dominates_insufficient() -> None:
    # No samples AND a missing replay command: the verdict is "unknown"
    # (cannot assess), not "insufficient", but both failures are recorded.
    verdict = audit_resolution(
        _sufficient_meta(input_count=0, finite_count=0, invalid_count=0, replayable=False)
    )
    assert verdict.resolution_status == "unknown"
    assert "input_depth" in verdict.blocked_claims
    assert "replayability" in verdict.blocked_claims


# ── fail-closed on malformed metadata ────────────────────────────────────
@pytest.mark.parametrize(
    "key",
    [
        "input_count",
        "finite_count",
        "invalid_count",
        "session_count",
        "temporal_resolution",
        "replayable",
        "artifact_complete",
    ],
)
def test_failclosed_missing_required_key(key: str) -> None:
    meta = _sufficient_meta()
    del meta[key]
    with pytest.raises(ValueError, match="missing required metadata key"):
        audit_resolution(meta)


def test_failclosed_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="inconsistent counts"):
        audit_resolution(_sufficient_meta(finite_count=100, invalid_count=100))  # 200 != 256


def test_failclosed_negative_count() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        audit_resolution(_sufficient_meta(session_count=-1))


def test_failclosed_bool_count_rejected() -> None:
    with pytest.raises(ValueError, match="must be a non-negative int"):
        audit_resolution(_sufficient_meta(session_count=cast(int, True)))


def test_failclosed_empty_temporal_token() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        audit_resolution(_sufficient_meta(temporal_resolution="   "))


def test_failclosed_non_bool_flag() -> None:
    with pytest.raises(ValueError, match="must be a bool"):
        audit_resolution(_sufficient_meta(replayable=cast(bool, 1)))


def test_failclosed_graph_density_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        audit_resolution(_sufficient_meta(graph_density=1.5))


def test_failclosed_graph_density_non_finite() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        audit_resolution(_sufficient_meta(graph_density=float("nan")))


def test_failclosed_metadata_not_a_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        audit_resolution(cast(Any, ["input_count", 1]))


# ── boundary disclaimer present on every verdict ─────────────────────────
def test_claim_boundary_present_and_correct() -> None:
    verdict = audit_resolution(_sufficient_meta())
    assert verdict.claim_boundary == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert verdict.as_dict()["claim_boundary"] == "descriptor_only_not_predictor"


def test_audit_returns_frozen_dataclass() -> None:
    verdict = audit_resolution(_sufficient_meta())
    assert isinstance(verdict, ResolutionAudit)
    with pytest.raises(AttributeError):
        cast(Any, verdict).resolution_status = "sufficient"
