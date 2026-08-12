# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-M3 — Anti-promotion gate (claim boundary + ledger pin).

These tests fail-closed on:

* a D-002G scientific PASS string in M3 source / docs / tests outside
  an explicit forbidden-list / ❌ context;
* any canonical-run authorisation literal anywhere in M3 artifacts;
* a mutation to ``docs/governance/D002C_CLAIM_LEDGER.yaml``;
* a mutation to ``docs/governance/D002G_P3_M3_PREREGISTRATION.md``
  (touching = fresh M4 PR, not this M3 implementation).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIM_LEDGER = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
M3_PREREG = REPO_ROOT / "docs" / "governance" / "D002G_P3_M3_PREREGISTRATION.md"
M3_IMPL_REPORT = REPO_ROOT / "docs" / "governance" / "D002G_M3_IMPLEMENTATION_REPORT.md"
M3_ELIGIBILITY_MATRIX = REPO_ROOT / "docs" / "governance" / "D002G_M3_ELIGIBILITY_MATRIX.md"
ARTIFACTS_D002G = REPO_ROOT / "artifacts" / "d002g"

# fmt: off
_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
_M3_PREREG_SHA256_PIN: str = "0f11a0c890374c35e4dedecc66caec52ae867f49a8f8b3be2374f1464712c1f8"  # noqa: E501  # pragma: allowlist secret
# fmt: on


_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "D-002G validated",
    "canonical run unblocked",
    "canonical run authorised",
    "canonical run authorized",
    "D-002C rescued",
    "ledger promoted",
    "tier PASS",
    "tier promoted",
    "scientific validation complete",
    "scientific PASS achieved",
    "M3 proves",
    "topology proves",
    "null audit passed globally",
    "VALIDATED_REAL_BANK_LEVEL_RESULT",
    "TESTED_POSITIVE_REAL",
    "BANK_LEVEL_PRECURSOR_CONFIRMED",
    "real-data validated",
    "bank-level confirmed",
    "gamma universality",
    "SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN",
    "B1 closed by design",
    "constant-lift solved",
    "M3 fixed everything",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_m3_no_scientific_pass_string_in_docs_or_module() -> None:
    """No M3 source / doc carries a forbidden PASS-claim string outside an
    explicit negation / forbidden-list / D-002C-reference context."""
    scan_paths = [
        REPO_ROOT / "research" / "systemic_risk" / "d002g_null_mechanisms.py",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_IMPLEMENTATION_REPORT.md",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_ELIGIBILITY_MATRIX.md",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_m3_verdicts.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_m3_invariants.py",
        REPO_ROOT / "tests" / "systemic_risk" / "test_d002g_m3_negative_controls.py",
    ]
    for p in scan_paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for phrase in _FORBIDDEN_PHRASES:
            for line in text.splitlines():
                if phrase not in line:
                    continue
                lo = line.lower()
                if (
                    "❌" in line
                    or "❎" in line
                    or "forbidden" in lo
                    or "_forbidden_phrases" in lo
                    or "must not" in lo
                    or " no " in f" {lo} "
                    or "never" in lo
                    or "cannot" in lo
                    or "out-of-scope" in lo
                    or "out of scope" in lo
                    or "d-002c" in lo
                    or "d002c" in lo
                    or "rejected" in lo
                ):
                    continue
                raise AssertionError(
                    f"forbidden phrase {phrase!r} leaked outside forbidden "
                    f"context in {p.name}: {line!r}"
                )


def test_m3_no_canonical_run_authorisation_anywhere() -> None:
    """No M3 artifact authorises a canonical D-002G run."""
    canonical_literals = (
        "canonical_run_authorized = true",
        "canonical_run_authorized: true",
        "canonical run authorized: yes",
        "canonical run authorised: yes",
        "AUTHORISE_CANONICAL_D002G",
        "AUTHORIZE_CANONICAL_D002G",
    )
    scan_paths = [
        REPO_ROOT / "research" / "systemic_risk" / "d002g_null_mechanisms.py",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_IMPLEMENTATION_REPORT.md",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_ELIGIBILITY_MATRIX.md",
        REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md",
    ]
    for p in scan_paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for lit in canonical_literals:
            assert lit not in text, (
                f"canonical-run authorisation literal {lit!r} leaked into "
                f"{p.name}; this PR must NOT authorise a canonical run."
            )


def test_m3_d002c_ledger_sha256_unchanged() -> None:
    """D002C_CLAIM_LEDGER.yaml sha256 byte-exact unchanged."""
    actual = _sha256(CLAIM_LEDGER)
    assert actual == _LEDGER_SHA256_PIN, (
        f"D002C_CLAIM_LEDGER.yaml sha drifted: expected {_LEDGER_SHA256_PIN}, "
        f"got {actual}. M3 PR forbidden to touch the ledger."
    )


def test_m3_p3_m3_prereg_unchanged() -> None:
    """M3 pre-registration sha256 byte-exact unchanged at #680 merge anchor."""
    actual = _sha256(M3_PREREG)
    assert actual == _M3_PREREG_SHA256_PIN, (
        f"D002G_P3_M3_PREREGISTRATION.md sha drifted: expected "
        f"{_M3_PREREG_SHA256_PIN}, got {actual}. Touching the M3 pre-reg "
        "constitutes a fresh M4 pre-registration, NOT this M3 PR."
    )


def test_m3_no_b2_closure_claim() -> None:
    """No M3 artifact claims B2 closure (B2 is a separate, untouched blocker)."""
    b2_closure_literals = (
        "B2 closed",
        "B2_CLOSED",
        "B2 resolved",
        "B2 fixed",
        "B2 mitigated by M3",
    )
    scan_paths = [
        REPO_ROOT / "docs" / "governance" / "D002G_M3_IMPLEMENTATION_REPORT.md",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_ELIGIBILITY_MATRIX.md",
        REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md",
    ]
    for p in scan_paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for lit in b2_closure_literals:
            msg = f"B2 closure claim {lit!r} leaked into {p.name}; B2 is OUT-OF-SCOPE for this PR."
            assert lit not in text, msg
