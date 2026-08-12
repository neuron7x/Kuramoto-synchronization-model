# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the ACTION_RESULT_ACCEPTOR_LEDGER validator.

Pin every fail-closed rule plus a falsifier round-trip. The acceptor law
(action → observed → error → update / rollback) is enforced by the
validator; these tests are the watchdog on the watchdog.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

from tools.archive.validate_action_result_acceptor import (
    DEFAULT_LEDGER,
    DEFAULT_OUTPUT,
    build_summary,
    load_ledger,
    main,
    validate_ledger,
)


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "test-entry",
        "old_path": "old/path.py",
        "new_path": "new/path.py",
        "mechanism_type": "EXECUTION_RESULT_ACCEPTOR",
        "status": "OPERATIONAL",
        "importance": "HIGH",
        "action_source": "act()",
        "expected_result": "exp",
        "observed_result": "obs",
        "error_signal": "delta",
        "update_rule": "weights += eta",
        "rollback_rule": "",
        "memory_effect": "store",
        "existing_tests": ["tests/x.py"],
        "missing_tests": [],
        "falsifier": "mutate update; test fails",
        "migration_action": "KEEP_NEW",
        "reason": "test reason",
    }
    base.update(overrides)
    return base


def _ledger(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {"version": 1, "entries": [dict(e) for e in entries]}


# ── Test 1: valid ledger passes ──────────────────────────────────────────


def test_valid_minimal_ledger_passes() -> None:
    errors = validate_ledger(_ledger(_entry()))
    assert errors == [], errors


# ── Test 2: duplicate id fails ───────────────────────────────────────────


def test_duplicate_id_fails() -> None:
    a = _entry(id="dup")
    b = _entry(id="dup")
    errors = validate_ledger(_ledger(a, b))
    hits = [e for e in errors if e.rule == "DUPLICATE_ID"]
    assert hits, errors


# ── Test 3: OPERATIONAL without observed_result fails ────────────────────


def test_operational_without_observed_result_fails() -> None:
    errors = validate_ledger(_ledger(_entry(observed_result="")))
    hits = [e for e in errors if e.rule == "OPERATIONAL_NO_OBSERVED"]
    assert hits, errors


# ── Test 4: OPERATIONAL without error_signal fails ───────────────────────


def test_operational_without_error_signal_fails() -> None:
    errors = validate_ledger(_ledger(_entry(error_signal="")))
    hits = [e for e in errors if e.rule == "OPERATIONAL_NO_ERROR"]
    assert hits, errors


# ── Test 5: OPERATIONAL without update or rollback fails ─────────────────


def test_operational_without_update_or_rollback_fails() -> None:
    errors = validate_ledger(_ledger(_entry(update_rule="", rollback_rule="")))
    hits = [e for e in errors if e.rule == "OPERATIONAL_NO_UPDATE_OR_ROLLBACK"]
    assert hits, errors


# ── Test 6: OPERATIONAL without falsifier fails ──────────────────────────


def test_operational_without_falsifier_fails() -> None:
    errors = validate_ledger(_ledger(_entry(falsifier="")))
    hits = [e for e in errors if e.rule == "OPERATIONAL_NO_FALSIFIER"]
    assert hits, errors


# ── Test 7: OPERATIONAL without existing_tests fails ─────────────────────


def test_operational_without_existing_tests_fails() -> None:
    errors = validate_ledger(_ledger(_entry(existing_tests=[])))
    hits = [e for e in errors if e.rule == "OPERATIONAL_NO_TESTS"]
    assert hits, errors


# ── Test 8: PARTIAL with KEEP_NEW fails ──────────────────────────────────


def test_partial_keep_new_fails() -> None:
    bad = _entry(
        status="PARTIAL",
        migration_action="KEEP_NEW",
        existing_tests=[],
    )
    errors = validate_ledger(_ledger(bad))
    hits = [e for e in errors if e.rule == "PARTIAL_KEEP_NEW_FORBIDDEN"]
    assert hits, errors


# ── Test 9: DECORATIVE with PORT fails ───────────────────────────────────


def test_decorative_port_fails() -> None:
    bad = _entry(
        status="DECORATIVE",
        mechanism_type="DECORATIVE_LABEL",
        migration_action="PORT",
        missing_tests=["tests/x.py"],
    )
    errors = validate_ledger(_ledger(bad))
    hits = [e for e in errors if e.rule == "DECORATIVE_PORT_FORBIDDEN"]
    assert hits, errors


# ── Test 10: OVERCLAIM with KEEP_NEW fails ───────────────────────────────


def test_overclaim_keep_new_fails() -> None:
    bad = _entry(status="OVERCLAIM", migration_action="KEEP_NEW")
    errors = validate_ledger(_ledger(bad))
    hits = [e for e in errors if e.rule == "OVERCLAIM_REQUIRES_REMEDIATION"]
    assert hits, errors


# ── Test 11: PORT without test path fails ────────────────────────────────


def test_port_without_test_path_fails() -> None:
    bad = _entry(
        status="MISSING_IN_NEW",
        migration_action="PORT",
        missing_tests=[],
    )
    errors = validate_ledger(_ledger(bad))
    hits = [e for e in errors if e.rule == "PORT_NO_TEST_PATH"]
    assert hits, errors


# ── Test 12: unknown mechanism_type fails ────────────────────────────────


def test_unknown_mechanism_type_fails() -> None:
    errors = validate_ledger(_ledger(_entry(mechanism_type="MAGIC")))
    hits = [e for e in errors if e.rule == "UNKNOWN_MECHANISM_TYPE"]
    assert hits, errors


# ── Test 13: unknown migration_action fails ──────────────────────────────


def test_unknown_migration_action_fails() -> None:
    errors = validate_ledger(_ledger(_entry(migration_action="HOPE")))
    hits = [e for e in errors if e.rule == "UNKNOWN_MIGRATION_ACTION"]
    assert hits, errors


# ── Test 14: MISSING_IN_NEW without action fails ─────────────────────────


def test_missing_in_new_without_action_fails() -> None:
    bad = _entry(
        status="MISSING_IN_NEW",
        migration_action="bogus",
        existing_tests=[],
    )
    errors = validate_ledger(_ledger(bad))
    hits = [e for e in errors if e.rule == "MISSING_IN_NEW_NO_ACTION"]
    assert hits, errors


# ── Test 15: live ledger passes ──────────────────────────────────────────


def test_live_ledger_is_valid() -> None:
    ledger = load_ledger(DEFAULT_LEDGER)
    errors = validate_ledger(ledger)
    assert errors == [], "\n".join(e.render() for e in errors)


def test_live_ledger_minimum_coverage() -> None:
    """At least 15 entries; required acceptor anchors covered."""

    required_anchors = {
        "PromptOutcome".lower(),
        "PromptExecutionRecord".lower(),
        "record_outcome".lower(),
        "HNCMAdapter".lower(),
        "HNCMNeuro".lower(),
        "learned_weights".lower(),
        "eligibility".lower(),
        "metaplasticity".lower(),
        "StrategyRecord".lower(),
        "StrategyMemory".lower(),
        "EvaluationResult".lower(),
        "TradePulseV21".lower(),
        "kill_switch".lower(),
        "safe_mode".lower(),
        "claim".lower(),
    }
    ledger = load_ledger(DEFAULT_LEDGER)
    entries = cast(list[Mapping[str, Any]], ledger.get("entries", []))
    assert len(entries) >= 15, f"ledger must hold ≥ 15 entries, got {len(entries)}"
    blob_fields = (
        "id",
        "old_path",
        "new_path",
        "action_source",
        "expected_result",
        "observed_result",
        "error_signal",
        "update_rule",
        "rollback_rule",
        "memory_effect",
        "falsifier",
        "reason",
    )
    blob = "\n".join(
        "|".join(str(e.get(f, "")) for f in blob_fields) for e in entries if isinstance(e, Mapping)
    ).lower()
    missing = {a for a in required_anchors if a not in blob}
    assert not missing, f"missing anchors: {sorted(missing)}"


# ── Falsifier round-trip ─────────────────────────────────────────────────


def test_falsifier_roundtrip(tmp_path: Path) -> None:
    """Inject the canonical broken acceptor; expect exit 1.

    Then restore and expect exit 0. Mirrors the protocol's TEMP_BAD_ACTION_ACCEPTOR
    fixture exactly.
    """

    original = load_ledger(DEFAULT_LEDGER)
    bad = {
        "id": "TEMP_BAD_ACTION_ACCEPTOR",
        "old_path": "old/bad.py",
        "new_path": "new/bad.py",
        "mechanism_type": "CONSENSUS_FEEDBACK_ACCEPTOR",
        "status": "OPERATIONAL",
        "importance": "CRITICAL",
        "action_source": "decision",
        "expected_result": "expected outcome",
        "observed_result": "",
        "error_signal": "",
        "update_rule": "",
        "rollback_rule": "",
        "memory_effect": "",
        "existing_tests": [],
        "missing_tests": ["tests/x.py"],
        "falsifier": "",
        "migration_action": "PORT",
        "reason": "injected break for round-trip test",
    }
    poisoned = copy.deepcopy(cast(dict[str, Any], original))
    poisoned["entries"] = list(poisoned.get("entries", [])) + [bad]
    poisoned_path = tmp_path / "poisoned.yaml"
    poisoned_path.write_text(yaml.safe_dump(poisoned, sort_keys=False))
    out_path = tmp_path / "out.json"
    assert main([str(poisoned_path), "--output", str(out_path)]) == 1

    summary = json.loads(out_path.read_text(encoding="utf-8"))
    rules = {e["rule"] for e in summary["errors"]}
    # The injected entry breaks at least: NO_OBSERVED, NO_ERROR,
    # NO_UPDATE_OR_ROLLBACK, NO_FALSIFIER, NO_TESTS.
    assert "OPERATIONAL_NO_OBSERVED" in rules, summary
    assert "OPERATIONAL_NO_FALSIFIER" in rules, summary

    clean_path = tmp_path / "clean.yaml"
    clean_path.write_text(yaml.safe_dump(original, sort_keys=False))
    out_clean = tmp_path / "out_clean.json"
    assert main([str(clean_path), "--output", str(out_clean)]) == 0


# ── JSON output determinism ──────────────────────────────────────────────


def test_summary_is_deterministic_json() -> None:
    ledger = load_ledger(DEFAULT_LEDGER)
    summary_a = build_summary(ledger, [])
    summary_b = build_summary(ledger, [])
    assert summary_a == summary_b
    assert {
        "valid",
        "entry_count",
        "errors",
        "warnings",
        "critical_count",
        "high_count",
        "missing_in_new_count",
        "port_count",
        "rewrite_count",
        "archive_count",
        "reject_count",
    } <= summary_a.keys()


def test_default_output_path_is_under_tmp() -> None:
    assert DEFAULT_OUTPUT.name == "action_result_acceptor_validation.json"
    assert DEFAULT_OUTPUT.parent.name == "tmp"


# ── CLI ──────────────────────────────────────────────────────────────────


def test_cli_returns_zero_on_live_ledger(tmp_path: Path) -> None:
    out = tmp_path / "summary.json"
    assert main([str(DEFAULT_LEDGER), "--output", str(out)]) == 0
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["valid"] is True
    assert summary["entry_count"] >= 15


def test_cli_returns_two_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    out = tmp_path / "summary.json"
    assert main([str(missing), "--output", str(out)]) == 2
