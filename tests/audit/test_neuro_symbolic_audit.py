# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the NEURO_OPERATIONALIZATION_LEDGER validator.

The audit machinery is the safety net: any future ledger edit that breaks
the schema, lies about its evidence, or duplicates an id MUST fail closed.
These tests pin that contract.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

from tools.audit.neuro_symbolic_audit import (
    DEFAULT_LEDGER,
    load_ledger,
    main,
    validate_ledger,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _operational_entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "test-operational",
        "term": "kuramoto",
        "file": "core/kuramoto/engine.py",
        "line_range": [1, 100],
        "current_usage": "Test entry",
        "classification": "OPERATIONAL",
        "claimed_role": "Test role",
        "actual_algorithmic_role": "Test algo",
        "input_contract": "Test inputs",
        "output_contract": "Test outputs",
        "falsifier": "Test falsifier",
        "existing_tests": ["tests/unit/test_x.py"],
        "missing_tests": [],
        "runtime_path": "YES",
        "remediation_action": "KEEP",
        "priority": "P0",
        "reason": "Test reason",
        "inv_refs": ["INV-K1"],
    }
    base.update(overrides)
    return base


def _ledger(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {"version": 1, "entries": [dict(e) for e in entries]}


# ── Test 1: OPERATIONAL without falsifier fails ──────────────────────────


def test_operational_without_falsifier_fails() -> None:
    entry = _operational_entry(falsifier="")
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "falsifier" and "OPERATIONAL" in e.message]
    assert hits, errors


# ── Test 2: OPERATIONAL without test path fails ─────────────────────────-


def test_operational_without_existing_tests_fails() -> None:
    entry = _operational_entry(existing_tests=[])
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "existing_tests" and "OPERATIONAL" in e.message]
    assert hits, errors


# ── Test 3: DECORATIVE in runtime without non-claim fails ────────────────


def test_decorative_runtime_without_non_claim_fails() -> None:
    entry = _operational_entry(
        id="test-decorative",
        classification="DECORATIVE",
        runtime_path="YES",
        falsifier="no biological mechanism modelled",
        reason="decorative naming on runtime path",
        inv_refs=[],
        existing_tests=[],
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "falsifier" and "non-claim" in e.message.lower()]
    assert hits, errors


# ── Test 4: OVERCLAIM without remediation fails ──────────────────────────


def test_overclaim_keep_remediation_fails() -> None:
    entry = _operational_entry(
        id="test-overclaim",
        classification="OVERCLAIM",
        remediation_action="KEEP",
        runtime_path="NO",
        existing_tests=[],
        inv_refs=[],
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "remediation_action" and "OVERCLAIM" in e.message]
    assert hits, errors


# ── Test 5: PARTIAL without remediation fails ────────────────────────────


def test_partial_keep_remediation_fails() -> None:
    entry = _operational_entry(
        id="test-partial",
        classification="PARTIAL",
        remediation_action="KEEP",
        runtime_path="YES",
        existing_tests=[],
        inv_refs=[],
        falsifier="some falsifier",
        missing_tests=[],
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "remediation_action" and "PARTIAL" in e.message]
    assert hits, errors


# ── Test 6: missing line_range fails ─────────────────────────────────────


def test_missing_line_range_fails() -> None:
    entry = _operational_entry()
    del entry["line_range"]
    errors = validate_ledger(_ledger(entry))
    assert any(e.field == "line_range" for e in errors), errors


def test_invalid_line_range_fails() -> None:
    entry = _operational_entry(line_range=[10, 5])
    errors = validate_ledger(_ledger(entry))
    assert any(e.field == "line_range" for e in errors), errors


# ── Test 7: unknown classification fails ─────────────────────────────────


def test_unknown_classification_fails() -> None:
    entry = _operational_entry(classification="MAGIC")
    errors = validate_ledger(_ledger(entry))
    assert any(e.field == "classification" for e in errors), errors


# ── Test 8: unknown remediation_action fails ─────────────────────────────


def test_unknown_remediation_action_fails() -> None:
    entry = _operational_entry(remediation_action="WAVE_HANDS")
    errors = validate_ledger(_ledger(entry))
    assert any(e.field == "remediation_action" for e in errors), errors


# ── Test 9: duplicate id fails ───────────────────────────────────────────


def test_duplicate_id_fails() -> None:
    a = _operational_entry(id="dup")
    b = _operational_entry(id="dup")
    errors = validate_ledger(_ledger(a, b))
    assert any(e.field == "id" and "duplicate" in e.message for e in errors), errors


# ── Test 10: live ledger passes ──────────────────────────────────────────


def test_live_ledger_is_valid() -> None:
    """The committed ledger must validate cleanly."""

    ledger = load_ledger(DEFAULT_LEDGER)
    errors = validate_ledger(ledger)
    assert errors == [], "\n".join(e.render() for e in errors)


def test_live_ledger_has_minimum_coverage() -> None:
    """At least 25 entries covering the required terms (audit protocol §9)."""

    required_terms = {
        "dopamine",
        "serotonin",
        "gaba",
        "kuramoto",
        "ricci",
        "plasticity",
        "free energy",
        "cryptobiosis",
        "basal_ganglia",
        "neuro",
    }
    ledger = load_ledger(DEFAULT_LEDGER)
    entries = cast(list[Mapping[str, Any]], ledger.get("entries", []))
    assert len(entries) >= 25, f"ledger must hold ≥ 25 entries, got {len(entries)}"
    seen_terms = {str(e.get("term", "")).lower() for e in entries if isinstance(e, Mapping)} | {
        str(e.get("id", "")).lower() for e in entries if isinstance(e, Mapping)
    }
    missing = {t for t in required_terms if not any(t in s for s in seen_terms)}
    assert not missing, f"missing required term coverage: {sorted(missing)}"


# ── Falsifier round-trip ─────────────────────────────────────────────────
#
# Inject a deliberately broken OPERATIONAL entry, confirm validator exits 1,
# remove it, confirm exit 0. This guarantees the validator is not vacuous.


def test_falsifier_roundtrip(tmp_path: Path) -> None:
    """Inject a broken entry, confirm validator fails; remove it, confirm pass.

    Mirrors the protocol: 'create temporary ledger entry — classification:
    OPERATIONAL, term: dopamine, falsifier: "" — validator exits 1; restore;
    validator exits 0'.
    """

    original = load_ledger(DEFAULT_LEDGER)
    bad = _operational_entry(
        id="dopamine-injected-broken",
        term="dopamine",
        file="core/neuro/signal_bus.py",
        falsifier="",
        existing_tests=[],
        input_contract="",
    )
    poisoned = copy.deepcopy(cast(dict[str, Any], original))
    poisoned["entries"] = list(poisoned.get("entries", [])) + [bad]

    poisoned_path = tmp_path / "ledger_broken.yaml"
    poisoned_path.write_text(yaml.safe_dump(poisoned, sort_keys=False))

    rc_bad = main([str(poisoned_path)])
    assert rc_bad == 1

    clean_path = tmp_path / "ledger_clean.yaml"
    clean_path.write_text(yaml.safe_dump(original, sort_keys=False))

    rc_good = main([str(clean_path)])
    assert rc_good == 0


# ── CLI entry point ──────────────────────────────────────────────────────


def test_main_returns_zero_on_live_ledger() -> None:
    assert main([str(DEFAULT_LEDGER)]) == 0


def test_main_returns_two_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    assert main([str(missing)]) == 2
