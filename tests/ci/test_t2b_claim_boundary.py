# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guard the T2b claim boundary.

T2b has two live implementation bounds (INV-SL1/INV-SL2) and one rejected
empirical lead hypothesis. This test prevents future edits from silently
promoting the rejected OOS lead claim back into validation evidence — on any
of its three surfaces: the acceptor prose, the invariant registry, and the
frozen out-of-sample (OOS) artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTOR = ROOT / ".claude" / "commit_acceptors" / "T2b-stuart-landau-es.yaml"
REGISTRY = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
PREREG = ROOT / "results" / "cross_asset_kuramoto" / "SL_ES_PREREGISTRATION.md"
OOS = ROOT / "artifacts" / "rolling_es_proximity_oos.json"


def test_t2b_acceptor_prose_records_rejection() -> None:
    acceptor = ACCEPTOR.read_text(encoding="utf-8")

    assert "INV-SL1" in acceptor
    assert "INV-SL2" in acceptor
    assert "REJECTED_DO_NOT_PROMOTE" in acceptor
    assert "No T2b signal is wired into the shadow rail" in acceptor
    assert "not an active physics invariant" in acceptor

    forbidden_promotions = [
        "The leads claim itself is left as INV-T2b open hypothesis",
        "Kept as open hypothesis pending different substrate",
        "validation evidence for the shadow rail",
    ]
    for phrase in forbidden_promotions:
        assert phrase not in acceptor


def test_t2b_registry_marks_lead_claim_rejected_not_active() -> None:
    """The invariant registry must not present INV-T2b as an active claim.

    Guards the registry surface: without this, the acceptor prose can say
    ``REJECTED_DO_NOT_PROMOTE`` while ``.claude/physics/INVARIANTS.yaml`` still
    declares INV-T2b as an asserted invariant, so any generator reading the
    registry would keep treating the refuted lead hypothesis as live.
    """
    registry = REGISTRY.read_text(encoding="utf-8")

    assert "id: INV-T2b" in registry
    idx = registry.index("id: INV-T2b")
    block = registry[idx : idx + 1200]

    assert "REJECTED_DO_NOT_PROMOTE" in block
    assert "REFUTED" in block or "not an active physics invariant" in block
    # The registry must not assert the lead as a plain, holding statement.
    assert 'statement: "Rolling ES proximity peak precedes R(t) peak' not in registry


def test_t2b_oos_artifact_is_the_frozen_rejection() -> None:
    """Pin the rejection to the OOS artifact itself, not to acceptor prose.

    Parses the frozen artifact and asserts its recorded decision and p-value
    fail the pre-registered criterion, so editing the artifact to a different
    outcome (while keeping a ``p_value`` key) can no longer pass this guard.
    """
    oos = json.loads(OOS.read_text(encoding="utf-8"))
    prereg = PREREG.read_text(encoding="utf-8")

    assert prereg.count("REJECT H1") >= 1

    decision = str(oos["decision"]).upper()
    p_value = float(oos["p_value"])
    threshold = float(oos["config"]["p_value_threshold"])

    assert decision == "REJECT"
    assert p_value > threshold  # criterion fired: 0.765 > 0.05 -> rejected
