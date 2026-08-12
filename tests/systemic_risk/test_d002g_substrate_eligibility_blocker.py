# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P1-4 Codex review fix — substrate ineligibility is a canonical-run BLOCKER.

Attack
------
Prior to this elevation, the P1 implementation report mentioned the
substrate ineligibility of ``block_structured`` and ``temporal_coupling``
as a "design decision" footnote. That language under-stated the
operational consequence: the canonical D-002G run cannot proceed on 2 of
3 stock substrates until mechanism M2 (topology-preserving shuffle, per
prereg §4 fallback) is implemented in a downstream PR.

Fix
---
The implementation report now carries a top-level section
"SUBSTRATE ELIGIBILITY DISCOVERY (CANONICAL-RUN BLOCKER)" with:
  * eligibility table (M1-ELIGIBLE vs M1-INELIGIBLE per substrate);
  * explanation of seed-determinism at λ=0;
  * explicit "canonical D-002G run is BLOCKED" phrase;
  * downstream task pointer (D-002G-P2/M2 / M2 topology-preserving
    shuffle).

A consolidated blockers doc ``D002G_CANONICAL_RUN_BLOCKERS.md`` carries
the same eligibility table + B2 (percentile-CI limitation) +
canonical-run-NOT-ALLOWED rule.

This test enforces the elevation programmatically.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "docs" / "governance" / "D002G_P1_IMPLEMENTATION_REPORT.md"
BLOCKERS = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_report_marks_block_structured_M1_INELIGIBLE() -> None:
    body = _read(REPORT)
    # The eligibility table must pair the substrate id with M1-INELIGIBLE.
    # Tolerate either an inline ``...block_structured ... M1-INELIGIBLE`` or
    # table-row ordering — both must coexist in the report body.
    bs_missing_msg = "P1-4 VIOLATED: report missing 'block_structured' substrate id."
    assert "block_structured" in body, bs_missing_msg
    elig_tag_msg = "P1-4 VIOLATED: report missing 'M1-INELIGIBLE' eligibility tag."
    assert "M1-INELIGIBLE" in body, elig_tag_msg
    # Stronger: the same line that names block_structured must contain
    # M1-INELIGIBLE (no easy markdown table parse — search row-wise).
    lines_with_bs = [ln for ln in body.splitlines() if "block_structured" in ln]
    has_ineligible_pairing = any("M1-INELIGIBLE" in ln for ln in lines_with_bs)
    assert has_ineligible_pairing, (
        "P1-4 VIOLATED: no line in the report pairs 'block_structured' "
        f"with 'M1-INELIGIBLE'. Lines mentioning block_structured: "
        f"{lines_with_bs!r}"
    )


def test_report_marks_temporal_coupling_M1_INELIGIBLE() -> None:
    body = _read(REPORT)
    tc_missing_msg = "P1-4 VIOLATED: report missing 'temporal_coupling' substrate id."
    assert "temporal_coupling" in body, tc_missing_msg
    lines_with_tc = [ln for ln in body.splitlines() if "temporal_coupling" in ln]
    has_ineligible_pairing = any("M1-INELIGIBLE" in ln for ln in lines_with_tc)
    assert has_ineligible_pairing, (
        "P1-4 VIOLATED: no line in the report pairs 'temporal_coupling' "
        f"with 'M1-INELIGIBLE'. Lines mentioning temporal_coupling: "
        f"{lines_with_tc!r}"
    )


def test_report_declares_canonical_run_BLOCKED() -> None:
    """Pinned fail-loud phrase: canonical D-002G run is BLOCKED."""
    body = _read(REPORT)
    pinned = "canonical D-002G run is BLOCKED"
    assert pinned in body, (
        f"P1-4 VIOLATED: report missing pinned fail-loud phrase {pinned!r}. "
        f"Substrate ineligibility is not elevated to canonical-run blocker."
    )


def test_report_pins_substrate_eligibility_section_heading() -> None:
    body = _read(REPORT)
    pinned = "SUBSTRATE ELIGIBILITY DISCOVERY (CANONICAL-RUN BLOCKER)"
    assert pinned in body, f"P1-4 VIOLATED: report missing pinned section heading {pinned!r}."


def test_report_references_M2_downstream_task() -> None:
    """Downstream task pointer must reference M2 topology-preserving shuffle."""
    body = _read(REPORT)
    # Tolerate either "D-002G-P2/M2" or "M2 topology-preserving shuffle".
    a = "D-002G-P2/M2" in body
    b = "M2 topology-preserving shuffle" in body
    assert a or b, (
        "P1-4 VIOLATED: report does not reference the downstream task. "
        "Expected one of 'D-002G-P2/M2' or 'M2 topology-preserving "
        "shuffle' to be present."
    )


def test_blockers_doc_exists_with_required_content() -> None:
    """Consolidated blockers doc must exist and carry the canonical-run rule."""
    assert BLOCKERS.exists(), (
        f"P1-4 VIOLATED: {BLOCKERS} not found. Consolidated blockers "
        f"doc is required by the P1-4 fix."
    )
    body = _read(BLOCKERS)
    # Must carry both blockers (B1 substrate eligibility, B2 percentile CI).
    must_contain = [
        "CANONICAL D-002G RUN BLOCKED",
        "M1-INELIGIBLE",
        "block_structured",
        "temporal_coupling",
        "percentile bootstrap",
        "M2",
    ]
    missing = [s for s in must_contain if s not in body]
    assert not missing, f"P1-4 VIOLATED: blockers doc missing required fragments {missing!r}."


def test_report_does_not_claim_D002G_scientific_PASS() -> None:
    """Sanity guard: P1 implementation report must NOT claim D-002G PASS."""
    body = _read(REPORT)
    forbidden_phrases = [
        "D-002G PASS",
        "D-002G scientific PASS",
        "canonical D-002G PASS",
    ]
    # Allow phrases that explicitly NEGATE (e.g. "does NOT establish
    # D-002G scientific PASS"). Only catch the unqualified positive
    # claim by requiring the phrase NOT to be immediately preceded by
    # one of the negation tokens.
    for phrase in forbidden_phrases:
        idx = 0
        while True:
            pos = body.find(phrase, idx)
            if pos < 0:
                break
            window_before = body[max(0, pos - 120) : pos]
            negated = any(
                tok in window_before.lower()
                for tok in (
                    "does not",
                    "no claim",
                    "not establish",
                    "not claim",
                    "not a scientific",
                )
            )
            assert negated, (
                f"P1-4 VIOLATED: unqualified D-002G scientific PASS claim at "
                f"offset {pos}: ...{body[max(0, pos - 60) : pos + len(phrase) + 60]!r}..."
            )
            idx = pos + len(phrase)
