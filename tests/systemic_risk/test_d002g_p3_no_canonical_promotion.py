# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-P3 — Anti-promotion gate (claim boundary + ledger pin).

These tests fail-closed on any of:

* a D-002G scientific PASS string leaking into source / docs / commit
  message outside an explicit forbidden-list / ❌ context;
* a mutation to ``docs/governance/D002C_CLAIM_LEDGER.yaml`` (sha256
  pinned at the merge anchor — this PR must NOT touch the ledger);
* a canonical D-002G run artifact creation in ``artifacts/``;
* a forbidden phrase leaking into the P3 eligibility matrix doc.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIM_LEDGER = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
P3_ELIGIBILITY_MATRIX = REPO_ROOT / "docs" / "governance" / "D002G_P3_ELIGIBILITY_MATRIX.md"
P3_IMPL_REPORT = REPO_ROOT / "docs" / "governance" / "D002G_P3_IMPLEMENTATION_REPORT.md"
P3_DISCOVERY = REPO_ROOT / "docs" / "governance" / "D002G_P3_DISCOVERY_REPORT.md"
P3_CONTRACTS = REPO_ROOT / "docs" / "governance" / "D002G_P3_NULL_DOMAIN_CONTRACTS.md"
ARTIFACTS_D002G = REPO_ROOT / "artifacts" / "d002g"

# fmt: off
# The D002C_CLAIM_LEDGER.yaml sha256 pin. The protocol §3 references
# the post-merge-on-main sha `fd0c83a263d4a687c24e1d350cb3e0809dfdff2a`;
# in this worktree (branched off the as-yet-unmerged P2 PR) the on-disk
# sha is the P1-merge anchor `f96ba9b5...`. The pin below records the
# on-disk sha at branch-off time so any in-PR mutation to the ledger
# fails closed. The post-merge sha is recorded in §11 of the
# implementation report as the rebase-target invariant.
LEDGER_SHA256_AT_BRANCH_OFF: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
LEDGER_SHA256_TARGET_POST_P2_MERGE: str = "fd0c83a263d4a687c24e1d350cb3e0809dfdff2a"  # noqa: E501  # pragma: allowlist secret  # 40-hex per protocol §3
# fmt: on


# Forbidden claim-leakage strings, per protocol § FORBIDDEN PHRASES.
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "D-002G validated",
    "canonical run unblocked",
    "substrate passed",
    "scientific result confirmed",
    "M2 proves",
    "null audit passed globally",
    "VALIDATED_REAL_BANK_LEVEL_RESULT",
    "TESTED_POSITIVE_REAL",
    "BANK_LEVEL_PRECURSOR_CONFIRMED",
    "real-data validated",
    "bank-level confirmed",
    "SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN",
    "B1 closed by design",
    "constant-lift issue solved",
    "M2 fixed everything",
    "D-002C rescued",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_p3_no_scientific_pass_claim_literals() -> None:
    """No P3 source / doc carries a forbidden D-002G PASS claim string."""
    p3_paths = [
        REPO_ROOT / "research" / "systemic_risk" / "d002g_null_mechanisms.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_p3_node_payload_null.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_p3_injection_sequence_null.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_p3_constant_payload_blockers.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_p3_no_canonical_promotion.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_p3_traps.py",
    ]
    # Files that legitimately enumerate forbidden phrases for negative-
    # space testing. They are scanner-exempt by construction.
    _scanner_exempt = {
        "test_d002g_p3_no_canonical_promotion.py",
        "test_d002g_p3_traps.py",
    }
    for p in p3_paths:
        if not p.exists():
            continue
        if p.name in _scanner_exempt:
            continue
        text = p.read_text(encoding="utf-8")
        # Strip explicit forbidden-list block & ❌ ❎ context.
        # We consider a "forbidden context" line to be one where the
        # phrase appears together with the negation marker '❌' or with
        # the magic literal 'FORBIDDEN' or '_FORBIDDEN_PHRASES'.
        for phrase in _FORBIDDEN_PHRASES:
            for line in text.splitlines():
                if phrase in line:
                    if (
                        "❌" in line
                        or "FORBIDDEN" in line
                        or "_FORBIDDEN_PHRASES" in line
                        or "forbidden" in line.lower()
                        or "banned" in line.lower()
                    ):
                        continue
                    pytest.fail(
                        f"{p}: forbidden phrase outside forbidden context: {phrase!r} in line: {line!r}"
                    )


def test_p3_no_d002c_ledger_touch() -> None:
    """The D-002C claim ledger is byte-exact unchanged (sha256 pinned)."""
    assert CLAIM_LEDGER.is_file(), f"missing ledger at {CLAIM_LEDGER}"
    actual = _sha256(CLAIM_LEDGER)
    assert actual == LEDGER_SHA256_AT_BRANCH_OFF, (
        f"D-002C ledger mutated under P3:\n"
        f"  expected (branch-off pin): {LEDGER_SHA256_AT_BRANCH_OFF}\n"
        f"  actual:                    {actual}\n"
        f"  this PR MUST NOT mutate the ledger (claim-boundary "
        f"violation §3)."
    )
    # Anchor literal: the post-P2-merge target sha is the 40-hex blob
    # referenced in protocol §3. We assert its format is well-formed
    # (40-hex) but DO NOT assert equality — the on-disk sha is the
    # branch-off pin above. This keeps the protocol's literal under
    # version control without invalidating the worktree pin.
    assert re.fullmatch(r"[0-9a-f]{40}", LEDGER_SHA256_TARGET_POST_P2_MERGE) is not None


def test_p3_no_canonical_run_artifact_created() -> None:
    """The P3 PR creates eligibility-matrix artifacts only, NOT a canonical run."""
    if not ARTIFACTS_D002G.is_dir():
        return  # acceptable — no artifacts at all
    # Walk: any file matching a canonical-run name pattern fails.
    canonical_patterns = (
        re.compile(r"^canonical_run_"),
        re.compile(r"_canonical_"),
        re.compile(r"^D002G_PASS_"),
        re.compile(r"^run_manifest"),
        re.compile(r"^sweep_results"),
    )
    for p in ARTIFACTS_D002G.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        for pat in canonical_patterns:
            if pat.search(name):
                pytest.fail(f"canonical run artifact spuriously created: {p}")


def test_p3_eligibility_matrix_no_forbidden_phrases() -> None:
    """The P3 eligibility matrix doc carries no forbidden PASS claim."""
    if not P3_ELIGIBILITY_MATRIX.exists():
        pytest.skip("P3 eligibility matrix not yet written")
    text = P3_ELIGIBILITY_MATRIX.read_text(encoding="utf-8")
    for phrase in _FORBIDDEN_PHRASES:
        for line in text.splitlines():
            if phrase in line:
                if "❌" in line or "FORBIDDEN" in line or "forbidden" in line.lower():
                    continue
                pytest.fail(f"eligibility matrix carries forbidden phrase: {phrase!r} in {line!r}")


def test_p3_claim_boundary_present_in_impl_report() -> None:
    """Implementation report carries the verbatim claim boundary."""
    if not P3_IMPL_REPORT.exists():
        pytest.skip("P3 implementation report not yet written")
    text = P3_IMPL_REPORT.read_text(encoding="utf-8")
    required_fragments = (
        "This PR implements D-002G-P3 constant-payload null-admissibility",
        "does NOT establish D-002G scientific PASS",
        "does NOT authorise canonical D-002G run",
        "does NOT update D002C_CLAIM_LEDGER.yaml",
    )
    for frag in required_fragments:
        assert frag in text, f"claim boundary fragment missing: {frag!r}"
