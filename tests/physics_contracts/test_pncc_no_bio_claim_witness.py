# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the PNCC no-bio-claim gate.

Binds the catalog law ``pncc.no_bio_claim`` to its EXISTING checker —
``tacl.evidence_ledger.scan_source_for_bio_claims`` — via ``@law``. No new
scanner is invented; the witness exercises the real gate's contract:

* ``pncc.no_bio_claim`` (INV-NO-BIO-CLAIM) — cognitive-performance language in
  non-test source raises a violation UNLESS it is paired, in scope, with an
  allowed disclaimer phrase (same line) or an evidence reference token within
  the reference window. Test-path source is exempt.

The witness writes tiny synthetic source files and asserts the scanner flags the
unpaired claim, clears the disclaimer-paired and evidence-paired claims, raises
nothing on clean source, and exempts test paths — proving the gate both fires
and clears for the right reasons.

Nothing here is a market claim. These are claim-governance-gate facts.
"""

from __future__ import annotations

from pathlib import Path

from physics_contracts.law import law
from tacl.evidence_ledger import DEFAULT_FORBIDDEN_PATTERNS, scan_source_for_bio_claims

_FORBIDDEN_LINE = "# this supplement improves memory and focus"


@law("pncc.no_bio_claim", n_patterns=len(DEFAULT_FORBIDDEN_PATTERNS))
def test_bio_claim_gate_fires_and_clears_correctly(tmp_path: Path) -> None:
    """INV-NO-BIO-CLAIM: unpaired cognitive claims are flagged; paired ones clear.

    The witness drives the real scanner over four synthetic source files and one
    test-path file, requiring: an unpaired bio-claim raises ≥ 1 violation; a
    same-line disclaimer clears it; an evidence reference token in window clears
    it; clean source raises none; and a test-path file is exempt. Several
    independent checks pin the gate's contract on both sides.
    """
    n_patterns = len(DEFAULT_FORBIDDEN_PATTERNS)

    unpaired = tmp_path / "unpaired.py"
    unpaired.write_text(_FORBIDDEN_LINE + "\nx = 1\n", encoding="utf-8")

    disclaimed = tmp_path / "disclaimed.py"
    disclaimed.write_text(_FORBIDDEN_LINE + " -- we make no claim of causation\n", encoding="utf-8")

    evidenced = tmp_path / "evidenced.py"
    evidenced.write_text("# anchored by EvidenceClaim HYP-1\n" + _FORBIDDEN_LINE + "\n", encoding="utf-8")

    clean = tmp_path / "clean.py"
    clean.write_text("# computes the Kuramoto order parameter R\nx = 1\n", encoding="utf-8")

    test_path = tmp_path / "test_exempt.py"
    test_path.write_text(_FORBIDDEN_LINE + "\n", encoding="utf-8")

    unpaired_hits = len(scan_source_for_bio_claims([unpaired]))
    disclaimed_hits = len(scan_source_for_bio_claims([disclaimed]))
    evidenced_hits = len(scan_source_for_bio_claims([evidenced]))
    clean_hits = len(scan_source_for_bio_claims([clean]))
    test_path_hits = len(scan_source_for_bio_claims([test_path]))

    assert unpaired_hits >= 1, (
        "INV-NO-BIO-CLAIM violated: observed unpaired_hits = "
        f"{unpaired_hits} must be ≥ 1 with n_patterns={n_patterns}; an unpaired "
        "cognitive-performance claim must be flagged by the gate"
    )
    assert disclaimed_hits == 0, (
        "INV-NO-BIO-CLAIM violated: observed disclaimed_hits = "
        f"{disclaimed_hits} must be 0 with n_patterns={n_patterns}; a same-line "
        "disclaimer must clear the claim"
    )
    assert evidenced_hits == 0, (
        "INV-NO-BIO-CLAIM violated: observed evidenced_hits = "
        f"{evidenced_hits} must be 0 with n_patterns={n_patterns}; an evidence "
        "reference token in window must clear the claim"
    )
    assert clean_hits == 0 and test_path_hits == 0, (
        "INV-NO-BIO-CLAIM violated: observed clean_hits = "
        f"{clean_hits} and test_path_hits = {test_path_hits} must both be 0 with "
        f"n_patterns={n_patterns}; clean source must not false-positive and test "
        "paths must be exempt"
    )
