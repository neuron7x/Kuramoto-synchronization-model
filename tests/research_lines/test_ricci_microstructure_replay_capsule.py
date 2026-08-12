# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""External-reproducibility replay capsule for the ricci_microstructure_v1 line.

This is the credential-free public fallback for the line. It does **not** promote
any claim. It proves one thing, deterministically and without private data:

    the committed synthetic placeholder replays to a *stable, negative* promotion
    decision, and that negative evidence is preserved byte-for-byte.

Why this matters: ``EXTERNALLY_REPRODUCIBLE`` for the L2 Ricci *market* claim is
BLOCKED — it needs a real, hash-pinned order-book session plus a human-witness
review. But the *pipeline and its blocked verdict* can be reproduced by anyone,
right now, with no venue credentials. That is what this capsule pins.

Reproduction (Phase-8 envelope)
-------------------------------
- input fixtures:
    research_lines/ricci_microstructure_v1/preregistration/dataset.example.json
    research_lines/ricci_microstructure_v1/preregistration/config.example.json
- data_sha256:    b1da972d910a7ed5897e2a28461f6cf238652d6150c9e8c771b4b7dcfc4f0d5e
- config_sha256:  ca499750aa18d54f2bf152eed40333b2198ee1aa7abde6d4c2bc97a93a3cfc6e
- replay command: python -m pytest tests/research_lines/test_ricci_microstructure_replay_capsule.py -q
- expected schema: tools.research.ricci_preregistration_guard.PromotionDecision
- known limits:   synthetic placeholder only; proves determinism + the blocked
                  verdict, never a market signal. Caps maturity at INSTRUMENTED.
- failure interp: if any pin below drifts, either the committed fixture changed
                  or the guard logic changed — both must be reviewed before any
                  artifact built on this line is trusted. Fail closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools.research.ricci_preregistration_guard import evaluate_promotion

_REPO = Path(__file__).resolve().parents[2]
_BASE = _REPO / "research_lines" / "ricci_microstructure_v1"
_DATASET = _BASE / "preregistration" / "dataset.example.json"
_CONFIG = _BASE / "preregistration" / "config.example.json"
_MANIFEST = _REPO / "artifacts" / "runs" / "ricci_microstructure_v1" / "replay_capsule_manifest.json"

# Provenance pins over the committed synthetic fixtures (Phase-2 evidence).
# These are sha256 content hashes of public synthetic fixtures, not secrets.
EXPECTED_DATA_SHA256 = "b1da972d910a7ed5897e2a28461f6cf238652d6150c9e8c771b4b7dcfc4f0d5e"  # pragma: allowlist secret
EXPECTED_CONFIG_SHA256 = "ca499750aa18d54f2bf152eed40333b2198ee1aa7abde6d4c2bc97a93a3cfc6e"  # pragma: allowlist secret

# Deterministic-replay pin over the canonical serialization of the decision.
EXPECTED_DECISION_SHA256 = "2686e7687c75e7bbe991a987353f7f5abfca6a19eb369413bc9637c1eceb8427"  # pragma: allowlist secret

# Negative-evidence pin: the exact, preserved blocked verdict (Phase-4 fallback).
EXPECTED_BLOCKERS = (
    "no real data hash (placeholder/zero data_sha256)",
    "synthetic data caps state at INSTRUMENTED; cannot promote claim tier",
    "insufficient data depth (< 3600s)",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_decision_hash(decision: Any) -> str:
    payload = {
        "allowed": decision.allowed,
        "claim_tier": decision.claim_tier,
        "decision": decision.decision,
        "falsification_status": decision.falsification_status,
        "reasons": list(decision.reasons),
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def test_fixture_provenance_is_pinned() -> None:
    """The synthetic input fixtures must match their recorded hashes."""
    assert _sha256(_DATASET) == EXPECTED_DATA_SHA256, "dataset fixture drifted; re-review"
    assert _sha256(_CONFIG) == EXPECTED_CONFIG_SHA256, "config fixture drifted; re-review"


def test_replay_is_deterministic_and_blocked() -> None:
    """Replaying the guard on the committed fixtures yields the pinned negative verdict."""
    dataset = json.loads(_DATASET.read_text(encoding="utf-8"))
    config = json.loads(_CONFIG.read_text(encoding="utf-8"))

    first = evaluate_promotion(dataset, config, None)
    second = evaluate_promotion(dataset, config, None)

    # Determinism: two replays produce the identical canonical hash.
    assert _canonical_decision_hash(first) == _canonical_decision_hash(second)
    assert _canonical_decision_hash(first) == EXPECTED_DECISION_SHA256

    # The verdict is, and stays, fail-closed at HYPOTHESIS.
    assert first.allowed is False
    assert first.claim_tier == "HYPOTHESIS"
    assert first.decision == "OBSERVE"
    assert first.falsification_status == "NOT_RUN"


def test_negative_evidence_is_preserved() -> None:
    """The exact blocking reasons are preserved, not collapsed or hidden."""
    dataset = json.loads(_DATASET.read_text(encoding="utf-8"))
    config = json.loads(_CONFIG.read_text(encoding="utf-8"))
    decision = evaluate_promotion(dataset, config, None)
    assert tuple(decision.reasons) == EXPECTED_BLOCKERS


@pytest.mark.parametrize("field", ["is_synthetic", "data_sha256"])
def test_capsule_is_synthetic_and_credential_free(field: str) -> None:
    """The capsule must be reproducible without real/credentialed data."""
    dataset = json.loads(_DATASET.read_text(encoding="utf-8"))
    if field == "is_synthetic":
        assert dataset["is_synthetic"] is True
    else:
        assert dataset["data_sha256"] == "0" * 64, "capsule must not embed real data hash"


def test_manifest_is_consistent_with_capsule() -> None:
    """The published manifest must pin exactly what this capsule already asserts.

    The manifest is the externally-reproducible front door; it must not drift
    from the in-test pins, and it must keep the claim ceiling at INSTRUMENTED
    while declaring the capsule synthetic-only. Fail closed on any mismatch.
    """
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    # Provenance and decision pins must match the capsule's pins exactly.
    assert manifest["data_sha256"] == EXPECTED_DATA_SHA256
    assert manifest["config_sha256"] == EXPECTED_CONFIG_SHA256
    assert manifest["decision_sha256"] == EXPECTED_DECISION_SHA256
    assert tuple(manifest["expected_blockers"]) == EXPECTED_BLOCKERS

    # The pinned negative verdict must match what the guard actually returns.
    dataset = json.loads(_DATASET.read_text(encoding="utf-8"))
    config = json.loads(_CONFIG.read_text(encoding="utf-8"))
    decision = evaluate_promotion(dataset, config, None)
    assert manifest["expected_decision"]["allowed"] == decision.allowed is False
    assert manifest["expected_decision"]["claim_tier"] == decision.claim_tier == "HYPOTHESIS"
    assert manifest["expected_decision"]["decision"] == decision.decision == "OBSERVE"
    assert (
        manifest["expected_decision"]["falsification_status"]
        == decision.falsification_status
        == "NOT_RUN"
    )

    # Claim boundary: never promoted, never pretends to be real-data evidence.
    assert manifest["claim_ceiling"] == "INSTRUMENTED"
    assert manifest["synthetic_only"] is True
    assert manifest["credential_free"] is True

    # The one-command replay path must point back at this very capsule.
    assert manifest["replay_command"] == (
        "python -m pytest tests/research_lines/"
        "test_ricci_microstructure_replay_capsule.py -q"
    )

    # The note must keep the limitation explicit (no market/edge promotion).
    note = manifest["note"].lower()
    assert "does not prove" in note
    assert "market" in note
