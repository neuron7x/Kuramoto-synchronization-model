# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the DS-11 remediation-ledger gate.

Stdlib + jsonschema. Loads the gate by path (tests/ci/pytest.ini keeps these
helper tests independent of the heavy repo-level conftest) and drives it over
isolated fixture copies of the ledger so both polarities are deterministic.

The real repo root is used to resolve source_evidence paths and baseline_tree
(the git object only exists in the real working tree); only the ledger JSON is
a mutable fixture copy.

Polarity:
  POSITIVE — the real committed (fixed) ledger -> exit 0.
  NEGATIVE — closed-without-PASS -> RED; dangling closed source_evidence -> RED;
             bad baseline_tree -> RED; schema-invalid status -> RED.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GATE_PATH = _REPO / "scripts" / "ci" / "check_remediation_ledger.py"
_LEDGER_PATH = _REPO / "governance" / "remediation_ledger.v1.json"
_SCHEMA_PATH = _REPO / "governance" / "remediation_ledger.v1.schema.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_remediation_ledger", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


def _committed_ledger() -> dict:
    return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))


def _run(tmp_path: Path, ledger: dict) -> int:
    """Write a fixture ledger copy and run the gate against the REAL repo root."""
    lpath = tmp_path / "ledger.json"
    lpath.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return GATE.main(
        [
            "--ledger", str(lpath),
            "--schema", str(_SCHEMA_PATH),
            "--root", str(_REPO),
            "--git-root", str(_REPO),
        ]
    )


def _first_closed(ledger: dict) -> dict:
    for item in ledger["items"]:
        if item.get("status") == "closed":
            return item
    raise AssertionError("no closed item in ledger fixture")


# --------------------------------------------------------------------------- #
# POSITIVE
# --------------------------------------------------------------------------- #
def test_positive_committed_ledger_is_green(tmp_path: Path) -> None:
    """The real (fixed) committed ledger passes clean -> exit 0."""
    assert _run(tmp_path, _committed_ledger()) == 0


def test_committed_ledger_has_no_partial_env_limited_status() -> None:
    """Regression: TST-001 must no longer carry the invalid enum value."""
    ledger = _committed_ledger()
    statuses = {i["status"] for i in ledger["items"]}
    valid = {"open", "in_progress", "closed", "waived"}
    assert statuses <= valid, f"invalid statuses present: {statuses - valid}"
    tst001 = next(i for i in ledger["items"] if i["id"] == "TST-001")
    assert tst001["status"] == "in_progress"  # env-limited partial, NOT closed


# --------------------------------------------------------------------------- #
# NEGATIVE
# --------------------------------------------------------------------------- #
def test_negative_closed_without_pass_is_red(tmp_path: Path) -> None:
    """A closed item whose reviewer_signoff.verdict != PASS -> RED."""
    ledger = copy.deepcopy(_committed_ledger())
    item = _first_closed(ledger)
    item["reviewer_signoff"] = {"reviewer": "x", "verdict": "FAIL", "date": "2026-07-19"}
    assert _run(tmp_path, ledger) == 1


def test_negative_closed_missing_signoff_is_red(tmp_path: Path) -> None:
    """A closed item with no reviewer_signoff at all -> RED (fail-closed)."""
    ledger = copy.deepcopy(_committed_ledger())
    item = _first_closed(ledger)
    item.pop("reviewer_signoff", None)
    assert _run(tmp_path, ledger) == 1


def test_negative_dangling_closed_source_evidence_is_red(tmp_path: Path) -> None:
    """A closed item citing a non-existent repo-rooted path -> RED."""
    ledger = copy.deepcopy(_committed_ledger())
    item = _first_closed(ledger)
    item["source_evidence"] = "docs/this_evidence_does_not_exist_ds11.json"
    assert _run(tmp_path, ledger) == 1


def test_negative_bad_baseline_tree_is_red(tmp_path: Path) -> None:
    """A baseline_tree that resolves to no git object -> RED."""
    ledger = copy.deepcopy(_committed_ledger())
    ledger["baseline_tree"] = "0" * 40
    assert _run(tmp_path, ledger) == 1


def test_negative_invalid_status_enum_is_red(tmp_path: Path) -> None:
    """The original DS-11 defect: a status outside the enum -> schema RED."""
    ledger = copy.deepcopy(_committed_ledger())
    _first_closed(ledger)  # ensure structure intact
    ledger["items"][0]["status"] = "partial-env-limited"
    assert _run(tmp_path, ledger) == 1


def test_negative_missing_ledger_is_config_error(tmp_path: Path) -> None:
    """A missing ledger file is a misconfiguration -> exit 2."""
    rc = GATE.main(
        [
            "--ledger", str(tmp_path / "nope.json"),
            "--schema", str(_SCHEMA_PATH),
            "--root", str(_REPO),
            "--git-root", str(_REPO),
        ]
    )
    assert rc == 2


def test_open_item_planned_evidence_is_not_required(tmp_path: Path) -> None:
    """An OPEN item may cite planned (not-yet-existing) evidence -> still GREEN."""
    ledger = copy.deepcopy(_committed_ledger())
    # Find an open item and point it at a non-existent path; must not fail.
    opened = next(i for i in ledger["items"] if i.get("status") == "open")
    opened["source_evidence"] = "artifacts/not/produced/yet_ds11.json"
    assert _run(tmp_path, ledger) == 0
