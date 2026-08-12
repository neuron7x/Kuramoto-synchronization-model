# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate D — forbidden-claim scanner tests.

These tests exercise the scanner in
``scripts/x10r_d002h_gate_d_scan.py`` and assert that, on the current
working tree, no forbidden phrase from the locked D-002H
``forbidden_claims`` list leaks outside the denial context across the
scanned surface (D-002H/D-002G governance docs, D-002G/D-002H
artifacts, D-002G/D-002H commit acceptors, D-002G/D-002H tests).

Gate D is one term of the 7-gate canonical-run authorisation
conjunction (A AND B AND C AND D AND E AND F AND G). PASS of Gate D
alone does NOT authorise canonical run; the conjunction is the
contract.

The tests also pin the locked file-shas (D-002C claim ledger and D-002H
prereg) so a silent edit to either drops Gate D from PASS in the same
run as the byte-exact ledger / prereg guards.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts.x10r_d002h_gate_d_scan import (
    ALLOWED_DENIAL_MARKERS,
    ARTIFACT_PATH,
    ARTIFACT_RELPATH,
    FORBIDDEN_CLAIMS,
    REPO_ROOT,
    SCANNER_EXEMPT_PATHS,
    SCHEMA_VERSION,
    LeakRecord,
    ScanResult,
    emit_artifact,
    run_scan,
)

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"

# Content-addressed governance anchors. ``fmt: off`` keeps the literals
# on a single line; the inline pragma silences detect-secrets
# HexHighEntropy — these are not credentials.
# fmt: off
D002C_LEDGER_SHA256: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
D002H_PREREG_SHA256: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
# fmt: on

# Lesson 4 (false-confidence C3): drift sentinels for the exempt set.
# These three files MUST stay exempt by design — they intentionally
# enumerate the forbidden phrases (scanner self-reference, prereg list
# source, ❌-block claim-boundary doc). If any of these disappears from
# the exempt set, the scanner suddenly self-leaks and Gate D drops.
EXPECTED_EXEMPT_SENTINELS: frozenset[str] = frozenset(
    {
        "scripts/x10r_d002h_gate_d_scan.py",
        "tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py",
        "docs/governance/D002H_PREREGISTRATION.yaml",
        "docs/governance/D002H_CLAIM_BOUNDARY.md",
    }
)


def _cached_result() -> ScanResult:
    """Run the scan once per test (the scan itself is sub-second)."""
    return run_scan()


# ---------------------------------------------------------------------------
# 10 contract tests (names per the Gate D brief).
# ---------------------------------------------------------------------------


def test_gate_d_artifact_exists() -> None:
    """The Gate D scan JSON is on disk and carries schema 'D002H-GATE-D-v1'.

    Emits the artifact if missing, then re-validates the schema /
    verdict / counters on disk. The emit is idempotent — re-running the
    scanner on a clean working tree yields the same JSON.
    """
    if not ARTIFACT_PATH.is_file():
        emit_artifact()
    assert ARTIFACT_PATH.is_file(), f"Gate D artifact missing at {ARTIFACT_RELPATH}"
    payload: dict[str, Any] = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["study_id"] == "D-002H"
    assert payload["gate"] == "D"
    assert payload["gate_d_verdict"] == "PASS"
    assert payload["n_leaks"] == 0
    assert payload["canonical_run_authorized"] is False
    assert payload["downstream_gates_remaining"] == ["E", "F", "G"]


def test_gate_d_scans_all_d002h_docs() -> None:
    """The scanned set covers every D-002H governance doc not in the exempt set.

    Asserts file-count health (Lesson 4 drift sentinel): there is at
    least one scanned file, at least one exempt file, and the two sets
    are disjoint. Then enumerates the four required exempt sentinels
    (scanner self, this test, prereg list source, claim-boundary doc).
    """
    result = _cached_result()
    msg_scanned = f"no files scanned; check SCAN_GLOBS (got {result.scanned_files!r})"
    assert len(result.scanned_files) > 0, msg_scanned
    msg_exempt = f"empty exempt set; check SCANNER_EXEMPT_PATHS (got {result.exempt_files!r})"
    assert len(result.exempt_files) > 0, msg_exempt
    overlap = set(result.scanned_files) & set(result.exempt_files)
    msg_overlap = f"scanned/exempt overlap (impossible by construction): {sorted(overlap)!r}"
    assert overlap == set(), msg_overlap

    # Sentinel: every required exempt file is present.
    missing_sentinels = EXPECTED_EXEMPT_SENTINELS - set(result.exempt_files)
    msg_sentinels = (
        f"required exempt sentinels missing from exempt set: {sorted(missing_sentinels)!r}; "
        "the scanner / prereg / claim-boundary doc MUST stay exempt by design"
    )
    assert missing_sentinels == set(), msg_sentinels

    # Sentinel: at least one D-002H governance doc is in the scanned set
    # (the gate-B/C reports). Negative case (Lesson 4): no D-002H prereg
    # leaked into the scanned set.
    scanned_d002h_docs = [
        relpath for relpath in result.scanned_files if relpath.startswith("docs/governance/D002H_")
    ]
    msg_d002h = f"no D-002H governance docs in scanned set: {result.scanned_files!r}"
    assert scanned_d002h_docs, msg_d002h
    assert D002H_PREREG_RELPATH not in result.scanned_files


def test_gate_d_no_cross_substrate_robustness_claim() -> None:
    """No 'cross-substrate robustness' / 'general topology robustness' leak.

    Negative case (Lesson 4): also asserts the per-phrase leak counter
    for both phrases is zero across the scanned set (not just one).
    """
    result = _cached_result()
    leaks_cross = [leak for leak in result.leaks if leak.phrase == "cross-substrate robustness"]
    leaks_topo = [leak for leak in result.leaks if leak.phrase == "general topology robustness"]
    msg_cross = (
        f"'cross-substrate robustness' leaks: {[(leak.relpath, leak.line_no) for leak in leaks_cross]!r}; "
        "Gate D forbids this claim outside denial context"
    )
    assert leaks_cross == [], msg_cross
    msg_topo = (
        f"'general topology robustness' leaks: {[(rec.relpath, rec.line_no) for rec in leaks_topo]!r}; "
        "Gate D forbids this claim outside denial context"
    )
    assert leaks_topo == [], msg_topo


def test_gate_d_no_d002g_rescue_claim() -> None:
    """No 'D-002G rescue' leak across scanned surface (Lesson 4: 2 assertions)."""
    result = _cached_result()
    leaks = [leak for leak in result.leaks if leak.phrase == "D-002G rescue"]
    msg = f"'D-002G rescue' leaks: {[(rec.relpath, rec.line_no) for rec in leaks]!r}"
    assert leaks == [], msg
    # Sentinel: the phrase IS still in the scanner's forbidden-claims
    # list (so a future leak would be caught).
    assert "D-002G rescue" in FORBIDDEN_CLAIMS


def test_gate_d_no_d002c_rescue_claim() -> None:
    """No 'D-002C rescue' leak; D-002C ledger sha byte-exact at the locked anchor.

    Two-assertion test (Lesson 4): the leak count AND the ledger sha
    must both hold. Either drift fails Gate D.
    """
    result = _cached_result()
    leaks = [leak for leak in result.leaks if leak.phrase == "D-002C rescue"]
    msg = f"'D-002C rescue' leaks: {[(rec.relpath, rec.line_no) for rec in leaks]!r}"
    assert leaks == [], msg

    ledger_path = REPO_ROOT / D002C_LEDGER_RELPATH
    assert ledger_path.is_file()
    actual = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    msg_ledger = (
        f"D-002C ledger MUTATED: expected {D002C_LEDGER_SHA256}, got {actual}; "
        "Gate D is forbidden from touching the D-002C claim ledger"
    )
    assert actual == D002C_LEDGER_SHA256, msg_ledger


def test_gate_d_no_scientific_pass_claim() -> None:
    """No 'scientific PASS before canonical run' / 'global systemic-risk conclusion' leak.

    Two distinct phrase checks (Lesson 4 C3).
    """
    result = _cached_result()
    leaks_pass = [
        leak for leak in result.leaks if leak.phrase == "scientific PASS before canonical run"
    ]
    leaks_global = [
        leak for leak in result.leaks if leak.phrase == "global systemic-risk conclusion"
    ]
    locs_pass = [(rec.relpath, rec.line_no) for rec in leaks_pass]
    locs_global = [(rec.relpath, rec.line_no) for rec in leaks_global]
    msg_pass = f"'scientific PASS before canonical run' leaks: {locs_pass!r}"
    assert leaks_pass == [], msg_pass
    msg_global = f"'global systemic-risk conclusion' leaks: {locs_global!r}"
    assert leaks_global == [], msg_global


def test_gate_d_no_canonical_run_authorisation_claim() -> None:
    """No 'canonical run authorized/authorised' as a present-state claim.

    Both spellings (US + UK) are forbidden surface per §D of the gates
    doc. Two-assertion test (Lesson 4 C3).
    """
    result = _cached_result()
    leaks_us = [leak for leak in result.leaks if leak.phrase == "canonical run authorized"]
    leaks_uk = [leak for leak in result.leaks if leak.phrase == "canonical run authorised"]
    locs_us = [(rec.relpath, rec.line_no) for rec in leaks_us]
    locs_uk = [(rec.relpath, rec.line_no) for rec in leaks_uk]
    msg_us = f"'canonical run authorized' leaks: {locs_us!r}"
    assert leaks_us == [], msg_us
    msg_uk = f"'canonical run authorised' leaks: {locs_uk!r}"
    assert leaks_uk == [], msg_uk


def test_gate_d_no_m4_inside_d002g_claim() -> None:
    """No 'M4 inside D-002G' leak; D-002H prereg sha byte-exact at anchor.

    Two-assertion (Lesson 4 C3): the leak count AND the prereg sha
    must both hold.
    """
    result = _cached_result()
    leaks = [leak for leak in result.leaks if leak.phrase == "M4 inside D-002G"]
    msg = f"'M4 inside D-002G' leaks: {[(rec.relpath, rec.line_no) for rec in leaks]!r}"
    assert leaks == [], msg

    prereg_path = REPO_ROOT / D002H_PREREG_RELPATH
    actual = hashlib.sha256(prereg_path.read_bytes()).hexdigest()
    msg_prereg = (
        f"D-002H prereg MUTATED: expected {D002H_PREREG_SHA256}, got {actual}; "
        "Gate D is forbidden from editing the locked prereg"
    )
    assert actual == D002H_PREREG_SHA256, msg_prereg


def test_gate_d_block_structured_excluded() -> None:
    """No 'block_structured remains in scope' leak; substrate stays excluded.

    Two-assertion test (Lesson 4 C3): the leak count AND the artifact-
    level downstream-gate vector ['E','F','G'] (Gate D is closed in
    this PR; the only open gates are E, F, G).
    """
    result = _cached_result()
    leaks = [leak for leak in result.leaks if leak.phrase == "block_structured remains in scope"]
    msg = (
        f"'block_structured remains in scope' leaks: "
        f"{[(rec.relpath, rec.line_no) for rec in leaks]!r}; "
        "block_structured is excluded by the locked D-002H prereg"
    )
    assert leaks == [], msg

    if not ARTIFACT_PATH.is_file():
        emit_artifact(result)
    payload: dict[str, Any] = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    msg_gates = (
        f"downstream_gates_remaining drift: expected ['E','F','G'], "
        f"got {payload['downstream_gates_remaining']!r}"
    )
    assert payload["downstream_gates_remaining"] == ["E", "F", "G"], msg_gates


def test_gate_d_temporal_coupling_excluded() -> None:
    """No 'temporal_coupling remains in scope' leak; closure verdict consistent.

    Two-assertion test (Lesson 4 C3): leak count zero AND scan-level
    verdict is PASS AND canonical_run_authorized is False.
    """
    result = _cached_result()
    leaks = [leak for leak in result.leaks if leak.phrase == "temporal_coupling remains in scope"]
    msg = (
        f"'temporal_coupling remains in scope' leaks: "
        f"{[(rec.relpath, rec.line_no) for rec in leaks]!r}; "
        "temporal_coupling is excluded by the locked D-002H prereg"
    )
    assert leaks == [], msg
    msg_verdict = f"unexpected scan verdict: {result.verdict!r} (expected 'PASS')"
    assert result.verdict == "PASS", msg_verdict

    # Sentinel: the scanner exposes the constants the brief locked.
    assert isinstance(LeakRecord, type)
    assert isinstance(FORBIDDEN_CLAIMS, tuple) and len(FORBIDDEN_CLAIMS) >= 9
    assert isinstance(ALLOWED_DENIAL_MARKERS, tuple) and len(ALLOWED_DENIAL_MARKERS) >= 5
    assert isinstance(SCANNER_EXEMPT_PATHS, frozenset)
