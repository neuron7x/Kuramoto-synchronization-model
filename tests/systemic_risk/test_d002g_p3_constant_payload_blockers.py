# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-P3 — Constant-payload blocker invariants.

These tests assert structural facts that MUST hold after P3 is
merged:

* `block_structured` is NOT promoted to ELIGIBLE by either the
  edge-weight, node-payload, or injection-sequence sub-domain.
* `temporal_coupling` is NOT promoted to ELIGIBLE by any sub-domain.
* B1 (substrate eligibility) is NOT CLOSED — every substrate must
  have at least one ELIGIBLE strategy for B1 to close per §11; the
  two constant-payload substrates remain INELIGIBLE.
* B2 (percentile-CI limitation) is NOT touched by this PR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.systemic_risk.d002c_substrates import SUBSTRATE_BY_ID
from research.systemic_risk.d002g_null_mechanisms import (
    verify_m2_eligibility,
    verify_m2_injection_sequence_eligibility,
    verify_m2_node_payload_eligibility,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCKERS_DOC = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"

_PREREG_SUBSTRATES = ("ricci_flow", "block_structured", "temporal_coupling")


def _all_sub_domain_verdicts(sub_id: str) -> dict[str, str]:
    sub = SUBSTRATE_BY_ID[sub_id]
    return {
        "edge_weight": verify_m2_eligibility(
            sub, N=50, lambda_value=0.4, base_seed=42, null_seed=12345
        ).status,
        "node_payload": verify_m2_node_payload_eligibility(
            sub, N=50, lambda_value=0.4, base_seed=42, null_seed=12345
        ).status,
        "injection_sequence": verify_m2_injection_sequence_eligibility(
            sub, N=50, lambda_value=0.4, base_seed=42, null_seed=12345
        ).status,
    }


def test_p3_block_structured_not_promoted_by_edge_weight() -> None:
    """block_structured remains INELIGIBLE across ALL sub-domains."""
    verdicts = _all_sub_domain_verdicts("block_structured")
    for domain, status in verdicts.items():
        ok = status.startswith("INELIGIBLE_") or status.startswith("INDETERMINATE_")
        assert ok, f"block_structured spuriously ELIGIBLE under {domain}: {status}"


def test_p3_temporal_coupling_not_promoted_by_edge_weight() -> None:
    """temporal_coupling remains INELIGIBLE across ALL sub-domains."""
    verdicts = _all_sub_domain_verdicts("temporal_coupling")
    for domain, status in verdicts.items():
        ok = status.startswith("INELIGIBLE_") or status.startswith("INDETERMINATE_")
        assert ok, f"temporal_coupling spuriously ELIGIBLE under {domain}: {status}"


def test_p3_b1_not_closed_without_full_substrate_coverage() -> None:
    """B1 closure rule: NO closure unless every substrate has >=1 ELIGIBLE."""
    coverage: dict[str, list[str]] = {}
    for sub_id in _PREREG_SUBSTRATES:
        verdicts = _all_sub_domain_verdicts(sub_id)
        eligible = [d for d, s in verdicts.items() if s.startswith("ELIGIBLE_")]
        coverage[sub_id] = eligible
    # B1 may only CLOSE if every substrate has >= 1 ELIGIBLE domain.
    uncovered = [sub for sub, dom in coverage.items() if not dom]
    msg = (
        f"B1 closure precondition spuriously satisfied; uncovered={uncovered}, coverage={coverage}"
    )
    assert len(uncovered) > 0, msg
    # The blockers doc must still record B1 as NOT CLOSED as an ACTIVE
    # state declaration. Rule statements like "Until B1 is CLOSED..."
    # or "B1 CLOSED — M2 mechanism implemented..." (a precondition
    # bullet) are legitimate; an active declaration would read
    # "Status: B1 CLOSED" or "B1 is now CLOSED" without the rule
    # framing. The active-state declarations are filtered below.
    text = BLOCKERS_DOC.read_text(encoding="utf-8")
    forbidden_state_decls = (
        "**Status.** B1 is CLOSED",
        "Status: B1 CLOSED",
        "B1 is now CLOSED",
        "canonical_run_authorized = true",
        "canonical_run_authorized: true",
    )
    for phrase in forbidden_state_decls:
        if phrase in text:
            pytest.fail(f"Blockers doc declares B1 spuriously CLOSED: {phrase!r}")
    # Positive assertion: the doc must explicitly record B1 as NOT
    # closed. Either the existing P2 wording is preserved OR P3
    # appends a §B1.P3 subsection that affirms the same.
    must_contain_one_of = (
        "B1 is **NOT** CLOSED",
        "B1 is NOT CLOSED",
        "B1 is **PARTIALLY MITIGATED**",
        "B1 is PARTIALLY MITIGATED",
        "B1 is OPEN_PARTIAL",
        "B1 remains OPEN_PARTIAL",
        "B1 remains OPEN",
    )
    has_open_affirmation = any(s in text for s in must_contain_one_of)
    msg = f"Blockers doc does not affirm B1 as still open; need one of {must_contain_one_of}"
    assert has_open_affirmation, msg


def test_p3_b2_remains_open_after_p3() -> None:
    """B2 (percentile-CI limitation) section is untouched by P3."""
    text = BLOCKERS_DOC.read_text(encoding="utf-8")
    b2_header = "### B2 — Phase 0b CI is percentile bootstrap, not BCa — OPEN"
    assert b2_header in text, "B2 section header drifted under P3"
    # B2 must NOT be reported as CLOSED anywhere
    bad = ("B2 CLOSED", "B2 is CLOSED", "B2_CLOSED")
    for phrase in bad:
        assert phrase not in text, f"B2 spuriously closed: {phrase}"
