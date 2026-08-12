# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the PhysicsEvidenceCapsuleShape binding (Task 6).

Falsifier witnesses: no dataset hash, no replay command, a law without a
witness, a missing falsifier, and a claim tier above the evidence tier. The
capsule is deterministic and its digest changes when any bound input changes.
"""

from __future__ import annotations

from typing import Any

import pytest

from physics_contracts.manifold.evidence_binding import (
    PhysicsEvidenceCapsuleShape,
    bind_physics_evidence,
)

_REAL_FP = "c" * 64
_LAWS = ("kuramoto.order_parameter_bounds", "ricci.gauss_bonnet")
_WITNESSED = frozenset(_LAWS)


def _bind(**overrides: object) -> PhysicsEvidenceCapsuleShape:
    base: dict[str, Any] = {
        "run_id": "r1",
        "dataset_fingerprint": _REAL_FP,
        "code_sha": "deadbeef",
        "config_hash": "cfg",
        "snapshot_id": "snap",
        "ricci_trace_digest": "rt",
        "sync_frame_digest": "sf",
        "comparison_report_digest": "cr",
        "laws_exercised": _LAWS,
        "falsifiers_passed": ("no_lookahead",),
        "falsifiers_failed": (),
        "claim_maturity": "REAL_DATA_SINGLE_SESSION",
        "verdict": "pass",
        "replay_command": "python -m geosync.replay --run r1",
        "nulls_survived": True,
        "witnessed_laws": _WITNESSED,
    }
    base.update(overrides)
    return bind_physics_evidence(**base)


def test_happy_path_binds_and_is_deterministic() -> None:
    a = _bind()
    b = _bind()
    assert a.capsule_digest == b.capsule_digest
    assert len(a.capsule_digest) == 64


def test_digest_changes_when_any_input_changes() -> None:
    base = _bind()
    changed = _bind(snapshot_id="snap-CHANGED")
    assert base.capsule_digest != changed.capsule_digest


def test_missing_dataset_hash_is_rejected() -> None:
    with pytest.raises(ValueError, match="dataset_fingerprint"):
        _bind(dataset_fingerprint="")


def test_missing_replay_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="replay_command"):
        _bind(replay_command="")


def test_law_without_witness_is_rejected() -> None:
    with pytest.raises(ValueError, match="no\n?\\s*registered witness|registered witness"):
        _bind(
            laws_exercised=("made.up.law",),
            claim_maturity="REPLAYABLE",
            witnessed_laws=_WITNESSED,
        )


def test_missing_falsifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="falsifiers_passed is empty"):
        _bind(falsifiers_passed=())


def test_real_data_tier_without_real_data_is_rejected() -> None:
    # Synthetic fingerprint cannot carry a REAL_DATA_* maturity tier.
    with pytest.raises(ValueError, match="DATA_UNAVAILABLE|real-data"):
        _bind(dataset_fingerprint="synthetic:0001")


def test_alternatives_eliminated_without_surviving_nulls_is_rejected() -> None:
    with pytest.raises(ValueError, match="above evidence tier"):
        _bind(claim_maturity="ALTERNATIVES_ELIMINATED", nulls_survived=False)


def test_unknown_verdict_is_rejected() -> None:
    with pytest.raises(ValueError, match="verdict"):
        _bind(verdict="definitely")


def test_claim_tier_vs_evidence_tier_conjunction() -> None:
    """`rank >= ALTERNATIVES_ELIMINATED and not nulls_survived` refuses over-claiming.

    A tier at/above ALTERNATIVES_ELIMINATED asserts the negative-control battery was survived,
    so it is refused iff nulls were NOT survived -- a conjunction. Under `And -> Or` the guard
    fires on EITHER condition: a legitimately high-tier capsule that DID survive its nulls is
    rejected, and a low-tier capsule that did not survive nulls (a perfectly honest state) is
    rejected too. Both admissible cases must bind.
    """
    # High tier + nulls survived -> admissible (the conjunction is False).
    high_ok = _bind(claim_maturity="ALTERNATIVES_ELIMINATED", nulls_survived=True)
    assert high_ok.claim_maturity == "ALTERNATIVES_ELIMINATED"

    # Low tier + nulls NOT survived -> admissible (tier does not assert the battery).
    low_ok = _bind(claim_maturity="REAL_DATA_SINGLE_SESSION", nulls_survived=False)
    assert low_ok.claim_maturity == "REAL_DATA_SINGLE_SESSION"

    # The genuinely inadmissible case still raises (high tier claims a battery it did not pass).
    with pytest.raises(ValueError, match="claim tier above evidence tier"):
        _bind(claim_maturity="ALTERNATIVES_ELIMINATED", nulls_survived=False)
