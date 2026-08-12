# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P1-3 Codex review fix — Phase 0b BCa↔percentile contract consistency.

Attack
------
The original Phase 0b implementation advertised a BCa (bias-corrected
accelerated) bootstrap CI in its docstring + adversarial audit narrative,
but actually used a simple percentile quantile of bootstrap means. That
mismatch is itself a contract bug: downstream consumers reading the
Phase 0b verdict under the "BCa" promise would make decisions under a
stronger assumption than the code provides.

User decision (Path 2): downgrade the contract. Phase 0b uses
percentile bootstrap CI. True BCa is future hardening.

This test enforces the contract consistency programmatically:
  1. ``d002g_phase0_verification.py`` source contains NO "BCa" /
     "bias-corrected" / "accelerated" tokens outside the explicit
     P1-3 limitation paragraph.
  2. ``D002G_P1_IMPLEMENTATION_REPORT.md`` contains the verbatim
     limitation fragment "percentile bootstrap CI, not BCa".
  3. ``D002G_P1_DESIGN_ADVERSARIAL_AUDIT.md`` marks Strike-R3 as
     DOWNGRADED with the limitation.

A test-suite drift in either direction (re-introducing the BCa claim
without an implementation, OR implementing BCa without updating the
contract) immediately surfaces as a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE0_SRC = REPO_ROOT / "research" / "systemic_risk" / "d002g_phase0_verification.py"
REPORT = REPO_ROOT / "docs" / "governance" / "D002G_P1_IMPLEMENTATION_REPORT.md"
AUDIT = REPO_ROOT / "docs" / "governance" / "D002G_P1_DESIGN_ADVERSARIAL_AUDIT.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_phase0_source_only_mentions_BCa_inside_P1_3_limitation_paragraph() -> None:
    """The source file may mention BCa ONLY inside the explicit limitation."""
    src = _read(PHASE0_SRC)
    # Every BCa / bias-corrected / accelerated mention must live in the
    # limitation paragraph that explicitly references the Codex P1-3 fix.
    pat = re.compile(r"(BCa|bias-corrected|accelerated)", re.IGNORECASE)
    for m in pat.finditer(src):
        # Window: ±600 chars around the match so the limitation paragraph
        # context (which carries the P1-3 marker) is fully captured even
        # when the matched token appears later in the paragraph than the
        # opening "P1-3" marker.
        start = max(0, m.start() - 600)
        end = min(len(src), m.end() + 600)
        window = src[start:end]
        has_p13 = "P1-3" in window or "Codex review fix" in window
        has_downgrade = "percentile" in window.lower()
        msg = (
            f"P1-3 VIOLATED: Phase 0b source mentions {m.group()!r} at offset "
            f"{m.start()} OUTSIDE the explicit P1-3 limitation paragraph. "
            f"Window:\n---\n{window}\n---"
        )
        assert has_p13 and has_downgrade, msg


def test_report_contains_verbatim_percentile_bootstrap_limitation() -> None:
    """Report must contain the verbatim limitation fragment."""
    body = _read(REPORT)
    fragment = "percentile bootstrap CI, not BCa"
    assert fragment in body, (
        f"P1-3 VIOLATED: D002G_P1_IMPLEMENTATION_REPORT.md missing the "
        f"verbatim limitation fragment {fragment!r}. The P1-3 contract "
        f"downgrade is not visible in the report."
    )


def test_report_pins_p1_3_section_title() -> None:
    """The report must carry the P1-3 section heading."""
    body = _read(REPORT)
    pinned = "## P1-3 percentile bootstrap CI"
    assert pinned in body, f"P1-3 VIOLATED: report missing pinned section heading {pinned!r}."


def test_audit_marks_R3_as_downgraded() -> None:
    """Adversarial audit doc must mark Strike-R3 as DOWNGRADED."""
    body = _read(AUDIT)
    has_downgraded = "DOWNGRADED" in body
    has_percentile = "percentile bootstrap CI" in body or "percentile bootstrap" in body
    has_r3 = "R3" in body or "Strike-R3" in body
    assert has_downgraded and has_percentile and has_r3, (
        "P1-3 VIOLATED: D002G_P1_DESIGN_ADVERSARIAL_AUDIT.md must mark "
        "Strike-R3 as DOWNGRADED and reference 'percentile bootstrap CI'. "
        f"has_downgraded={has_downgraded} has_percentile={has_percentile} "
        f"has_r3={has_r3}"
    )


def _phase0b_bca_leak(body: str) -> bool:
    """Return True iff ``body`` mentions BOTH a Phase 0b context AND a BCa token.

    The locked design doc references BCa CI for the CANONICAL sweep R1
    (not Phase 0b), so the rule is the CONJUNCTION: a Phase-0b context
    string must not co-occur with any BCa/bias-corrected/accelerated
    token in the same file.
    """
    lo = body.lower()
    if "phase 0b" not in lo and "phase_0b" not in lo:
        return False
    return bool(re.search(r"(BCa|bias-corrected|accelerated)", body))


def test_locked_files_never_mention_bca_for_phase0b() -> None:
    """Locked governance MUST NOT carry a Phase-0b BCa claim.

    Positive path: every real locked file is leak-free (the contract
    downgrade lives in the modifiable report + audit, never in the
    locked anchors). Negative path: the leak detector itself is
    instrumented against a synthetic body that DOES contain both
    "Phase 0b" and "BCa" — if the detector fails to flag it, the
    positive path is meaningless and the gate is a no-op.
    """
    # Positive path — every locked governance file must be leak-free.
    locked_files = [
        REPO_ROOT / "docs" / "governance" / "D002G_PREREGISTRATION.yaml",
        REPO_ROOT / "docs" / "governance" / "D002G_NONDEGENERATE_NULL_DESIGN.md",
        REPO_ROOT / "docs" / "governance" / "D002G_ACCEPTANCE_RULES.md",
    ]
    for fp in locked_files:
        if not fp.exists():
            continue
        body = _read(fp)
        assert not _phase0b_bca_leak(body), (
            f"P1-3 LOCKED-FILE LEAK: {fp} mentions BOTH Phase 0b and "
            f"BCa/bias-corrected/accelerated. Locked files must not "
            f"carry a Phase-0b BCa claim — this PR is forbidden from "
            f"modifying them. Report and ABORT."
        )

    # Negative path — the detector must actually flag a constructed leak.
    # If this assertion fails, the positive path above is vacuous: the
    # detector would silently pass even on a contaminated locked file.
    synthetic_leak = (
        "Phase 0b verification uses BCa bootstrap CI with bias-corrected accelerated quantiles."
    )
    assert _phase0b_bca_leak(synthetic_leak), (
        "Phase-0b BCa leak detector is broken: failed to flag a "
        "synthetic body that mentions both 'Phase 0b' and 'BCa'. "
        "The positive path is a no-op until this is fixed."
    )

    # Negative-of-negative — a clean body must not be flagged.
    synthetic_clean = (
        "Phase 0b verification uses percentile bootstrap CI; BCa is "
        "future hardening, not the current contract."
    )
    # The clean body co-mentions both tokens but in a documented
    # downgrade context. The detector is intentionally substring-based
    # (no contract-vs-claim NLP), so it WILL flag this — confirming the
    # detector's known limitation. We assert the flag fires here only
    # to pin that limitation in the test, not because the body is
    # actually a leak.
    assert _phase0b_bca_leak(synthetic_clean), (
        "Detector lost its substring-based conjunction behaviour. "
        "If the detector grew NLP smarts, update this test and the "
        "implementation report's known-limitations section together."
    )
