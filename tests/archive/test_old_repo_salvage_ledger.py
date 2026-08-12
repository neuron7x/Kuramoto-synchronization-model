# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the OLD_REPO_SALVAGE_LEDGER validator.

Pin every fail-closed rule, plus a falsifier round-trip and minimum
coverage of the 8 candidates flagged by the salvage protocol.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

from tools.archive.compare_old_repo_salvage import (
    DEFAULT_LEDGER,
    load_ledger,
    main,
    validate_ledger,
)


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "test-entry",
        "old_path": "old/path.py",
        "new_path_candidate": "new/path.py",
        "artifact_type": "CODE",
        "status": "RENAMED",
        "importance": "HIGH",
        "uniqueness": "UNIQUE",
        "mechanism_summary": "summary",
        "what_is_real": "real",
        "what_is_overclaim": "",
        "migration_action": "KEEP_NEW",
        "required_non_claim": "",
        "required_tests": [],
        "falsifier": "",
        "owner_surface": "core",
        "reason": "test",
    }
    base.update(overrides)
    return base


def _ledger(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {"version": 1, "entries": [dict(e) for e in entries]}


# ── Test 1: HIGH/CRITICAL missing artifact requires migration_action ─────


def test_critical_without_migration_action_fails() -> None:
    entry = _entry(
        importance="CRITICAL",
        status="MISSING",
        migration_action="not-an-action",
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "migration_action"]
    assert hits, errors


# ── Test 2: CODE with PORT requires required_tests ───────────────────────


def test_code_port_without_tests_fails() -> None:
    entry = _entry(
        artifact_type="CODE",
        status="MISSING",
        migration_action="PORT",
        required_tests=[],
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "required_tests" and "PORT" in e.message]
    assert hits, errors


# ── Test 3: IP artifact requires ARCHIVE or QUARANTINE ───────────────────


def test_ip_with_port_action_fails() -> None:
    entry = _entry(
        id="ip-bad",
        artifact_type="IP",
        status="MISSING",
        migration_action="PORT",
        required_tests=["x"],
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "migration_action" and "IP" in e.message]
    assert hits, errors


def test_ip_with_archive_passes() -> None:
    entry = _entry(
        id="ip-good",
        artifact_type="IP",
        status="MISSING",
        migration_action="ARCHIVE",
    )
    errors = validate_ledger(_ledger(entry))
    assert errors == [], errors


# ── Test 4: OVERCLAIM requires required_non_claim ────────────────────────


def test_overclaim_without_non_claim_fails() -> None:
    entry = _entry(
        status="OVERCLAIM",
        required_non_claim="",
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "required_non_claim"]
    assert hits, errors


# ── Test 5: PRODUCT requires owner_surface ───────────────────────────────


def test_product_without_owner_surface_fails() -> None:
    entry = _entry(
        artifact_type="PRODUCT",
        owner_surface="",
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "owner_surface"]
    assert hits, errors


# ── Test 6: duplicate id fails ───────────────────────────────────────────


def test_duplicate_id_fails() -> None:
    a = _entry(id="dup")
    b = _entry(id="dup")
    errors = validate_ledger(_ledger(a, b))
    hits = [e for e in errors if e.field == "id" and "duplicate" in e.message]
    assert hits, errors


# ── Test 7: unknown status fails ─────────────────────────────────────────


def test_unknown_status_fails() -> None:
    entry = _entry(status="WAVING")
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "status"]
    assert hits, errors


# ── Test 8: unknown migration_action fails ───────────────────────────────


def test_unknown_migration_action_fails() -> None:
    entry = _entry(migration_action="HOPE")
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "migration_action"]
    assert hits, errors


# ── Test 9: missing old_path fails ───────────────────────────────────────


def test_missing_old_path_fails() -> None:
    entry = _entry(old_path="")
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "old_path"]
    assert hits, errors


# ── Test 10: TEST entry requires owner_surface ───────────────────────────


def test_test_entry_without_owner_surface_fails() -> None:
    entry = _entry(
        artifact_type="TEST",
        owner_surface="",
    )
    errors = validate_ledger(_ledger(entry))
    hits = [e for e in errors if e.field == "owner_surface"]
    assert hits, errors


# ── Test 11: live ledger passes ──────────────────────────────────────────


def test_live_ledger_is_valid() -> None:
    ledger = load_ledger(DEFAULT_LEDGER)
    errors = validate_ledger(ledger)
    assert errors == [], "\n".join(e.render() for e in errors)


def test_live_ledger_has_minimum_coverage() -> None:
    """At least 30 entries; required candidates from the audit protocol."""

    required_anchors = {
        "tradepulse_v21",
        "test_tradepulse_v21",
        "tradepulse_cli",
        "PRODUCT_PAIN_SOLUTION",
        "PATENTS",
        "SYSTEM_OPTIMIZATION_SUMMARY",
        "PHYSICS_IMPLEMENTATION_SUMMARY",
        "PROJECT_DEVELOPMENT_STAGE",
        "hbunified",
    }
    ledger = load_ledger(DEFAULT_LEDGER)
    entries = cast(list[Mapping[str, Any]], ledger.get("entries", []))
    assert len(entries) >= 30, f"ledger must hold ≥ 30 entries, got {len(entries)}"

    haystack = "\n".join(
        f"{e.get('id', '')}|{e.get('old_path', '')}|{e.get('new_path_candidate', '')}"
        for e in entries
        if isinstance(e, Mapping)
    )
    missing = {a for a in required_anchors if a not in haystack}
    assert not missing, f"missing required salvage anchors: {sorted(missing)}"


# ── Falsifier round-trip ─────────────────────────────────────────────────


def test_falsifier_roundtrip(tmp_path: Path) -> None:
    """Inject a CRITICAL CODE PORT entry with empty required_tests; expect red.
    Restore; expect green.
    """

    original = load_ledger(DEFAULT_LEDGER)
    bad = _entry(
        id="injected-broken-critical-code",
        artifact_type="CODE",
        importance="CRITICAL",
        status="MISSING",
        migration_action="PORT",
        required_tests=[],
    )
    poisoned = copy.deepcopy(cast(dict[str, Any], original))
    poisoned["entries"] = list(poisoned.get("entries", [])) + [bad]
    poisoned_path = tmp_path / "broken.yaml"
    poisoned_path.write_text(yaml.safe_dump(poisoned, sort_keys=False))
    assert main([str(poisoned_path)]) == 1

    clean_path = tmp_path / "clean.yaml"
    clean_path.write_text(yaml.safe_dump(original, sort_keys=False))
    assert main([str(clean_path)]) == 0


# ── CLI entry point ──────────────────────────────────────────────────────


def test_main_returns_zero_on_live_ledger() -> None:
    assert main([str(DEFAULT_LEDGER)]) == 0


def test_main_returns_two_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    assert main([str(missing)]) == 2
