# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative regression tests proving the evidence-integrity gate has teeth.

The gate (``scripts/ci/check_evidence_integrity.py``) must REJECT a fabricated
promotion that the purely-structural neuro audit would let through: an
OPERATIONAL entry citing a non-existent invariant or a test file that was never
written, a PARTIAL claiming an operational INV binding, or a DECORATIVE runtime
entry that was never quarantined. Each test below builds a minimal in-memory
ledger and asserts the violation is caught — and that the real ledger is clean.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.check_evidence_integrity import (
    LEDGER,
    integrity_errors,
    known_invariant_ids,
)

KNOWN = {"INV-K1", "INV-RC1", "INV-DA8"}


def _ledger(entry: dict[str, object]) -> dict[str, object]:
    return {"entries": [entry]}


def _operational(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "demo-op",
        "classification": "OPERATIONAL",
        "inv_refs": ["INV-K1"],
        "existing_tests": ["scripts/ci/check_evidence_integrity.py"],  # a real file
        "falsifier": "R outside [0,1] ⇒ violation.",
        "runtime_path": "YES",
        "remediation_action": "KEEP",
        "reason": "ok",
    }
    base.update(overrides)
    return base


def test_clean_operational_passes() -> None:
    assert integrity_errors(_ledger(_operational()), KNOWN) == []


def test_operational_with_unknown_inv_is_rejected() -> None:
    errs = integrity_errors(_ledger(_operational(inv_refs=["INV-FAKE"])), KNOWN)
    assert any("unknown invariant" in e for e in errs)


def test_operational_with_no_inv_is_rejected() -> None:
    errs = integrity_errors(_ledger(_operational(inv_refs=[])), KNOWN)
    assert any("no inv_ref" in e for e in errs)


def test_operational_with_missing_test_file_is_rejected() -> None:
    errs = integrity_errors(
        _ledger(_operational(existing_tests=["tests/unit/does_not_exist_xyz.py"])), KNOWN
    )
    assert any("missing on disk" in e for e in errs)


def test_operational_with_no_test_is_rejected() -> None:
    errs = integrity_errors(_ledger(_operational(existing_tests=[])), KNOWN)
    assert any("no existing_test" in e for e in errs)


def test_operational_with_empty_falsifier_is_rejected() -> None:
    errs = integrity_errors(_ledger(_operational(falsifier="   ")), KNOWN)
    assert any("no falsifier" in e for e in errs)


def test_partial_claiming_inv_is_rejected_as_fake_promotion() -> None:
    partial: dict[str, object] = {
        "id": "demo-partial",
        "classification": "PARTIAL",
        "inv_refs": ["INV-DA8"],  # PARTIAL must NOT cite an operational INV
        "existing_tests": [],
        "falsifier": "x",
        "runtime_path": "YES",
        "remediation_action": "ADD_FALSIFIER",
        "reason": "y",
    }
    errs = integrity_errors(_ledger(partial), KNOWN)
    assert any("PARTIAL cites INV" in e for e in errs)


def test_decorative_runtime_without_quarantine_is_rejected() -> None:
    deco: dict[str, object] = {
        "id": "demo-deco",
        "classification": "DECORATIVE",
        "inv_refs": [],
        "existing_tests": [],
        "falsifier": "non-claim: pure label.",
        "runtime_path": "YES",
        "remediation_action": "KEEP",  # not a quarantine action
        "reason": "z",
    }
    errs = integrity_errors(_ledger(deco), KNOWN)
    assert any("must be quarantined" in e for e in errs)


def test_decorative_runtime_without_non_claim_is_rejected() -> None:
    deco: dict[str, object] = {
        "id": "demo-deco2",
        "classification": "DECORATIVE",
        "inv_refs": [],
        "existing_tests": [],
        "falsifier": "labels carry no algorithmic content.",  # no 'non-claim'
        "runtime_path": "YES",
        "remediation_action": "RENAME",
        "reason": "rename it",
    }
    errs = integrity_errors(_ledger(deco), KNOWN)
    assert any("non-claim" in e for e in errs)


def test_real_ledger_is_clean() -> None:
    """The shipped ledger passes the gate with the real known-invariant set."""
    ledger = yaml.safe_load(LEDGER.read_text(encoding="utf-8"))
    assert integrity_errors(ledger, known_invariant_ids()) == []


def test_registry_is_sole_authority_claude_md_token_is_not_known(tmp_path: Path) -> None:
    """A stray INV-FAKE in CLAUDE.md prose must NOT become a known invariant.

    known_invariant_ids reads ONLY the registry — there is no CLAUDE.md parameter
    anymore. A registry that lacks INV-FAKE yields a known-set without it even if
    CLAUDE.md elsewhere mentions the token.
    """
    reg = tmp_path / "INVARIANTS.yaml"
    reg.write_text("    id: INV-REAL\n", encoding="utf-8")
    known = known_invariant_ids(registry=reg)
    assert known == {"INV-REAL"}
    assert "INV-FAKE" not in known


def test_operational_citing_claude_only_fake_inv_is_rejected_without_naming_claude() -> None:
    """ledger cites INV-FAKE (the kind a CLAUDE.md mention used to legitimise) ⇒
    the gate rejects it, and the error names the registry — NOT CLAUDE.md as an
    authority."""
    errs = integrity_errors(_ledger(_operational(inv_refs=["INV-FAKE"])), KNOWN)
    assert errs, "fabricated INV-FAKE must be rejected"
    assert any("unknown invariant" in e for e in errs)
    assert all("CLAUDE.md" not in e for e in errs), (
        f"error must not present CLAUDE.md as authority: {errs}"
    )
