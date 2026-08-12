# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guards for the physics module reliability contract (Well-Architected gate).

These tests pin the fail-closed behaviour: declared entries must be grounded in
invariants that are literally present in the module source, recovery commands
must be executable-shaped, the coverage ratchet must hold, and the checker must
name its own uncovered backlog rather than implying full coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.physics.check_physics_reliability import (
    _INV_TOKEN,
    _RECOVERY_ACTION,
    _modules_with_invariants,
    _schema_validate,
    check,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_real_contract_passes_and_names_its_backlog() -> None:
    """The shipped contract is clean AND explicitly reports uncovered modules."""
    result = check()
    assert result["passed"] is True, result["hard_violations"]
    assert result["covered_count"] >= result["coverage_floor"]
    assert result["in_scope_count"] >= result["covered_count"]
    # The contract must not imply full coverage: the backlog is named, not hidden.
    assert result["uncovered_modules"], "expected uncovered modules to be reported by name"


def test_declared_invariants_are_present_in_module_source() -> None:
    """Every bound invariant must literally appear in its module — no phantom links.

    This is the core anti-overclaim guarantee: a failure_mode cannot cite an
    invariant the code does not actually carry.
    """
    result = check()
    assert result["hard_violations"] == []
    # Direct re-derivation per entry, independent of check()'s own loop.
    import yaml

    contract = yaml.safe_load((REPO_ROOT / "governance" / "PHYSICS_RELIABILITY.yaml").read_text())
    for entry in contract["modules"]:
        source = (REPO_ROOT / entry["module"]).read_text(encoding="utf-8")
        present = set(_INV_TOKEN.findall(source))
        for inv in entry["invariants"]:
            assert inv in present, f"{entry['module']} does not reference {inv}"


def test_phantom_invariant_is_rejected_by_checker() -> None:
    """check() must flag a declared invariant absent from the module source.

    Mutation-killing guard: this exercises the checker LOGIC (not just the data),
    so disabling the ``inv not in present`` branch makes this test fail.
    """
    phantom = {
        "version": 1,
        "coverage_floor": 0,
        "scope_roots": ["core/kuramoto"],
        "modules": [
            {
                "module": "core/kuramoto/second_order.py",
                "invariants": ["INV-K8", "INV-FAKE999"],  # second is phantom
                "role": "generator",
                "layer": "L4",
                "failure_mode": "synthetic entry for the phantom-invariant guard test only",
                "blast_radius": "synthetic entry for the phantom-invariant guard test only",
                "degradation_mode": "synthetic guard-test entry",
                "recovery_command": "raise on contract violation",
                "fail_closed": True,
            }
        ],
    }
    result = check(contract=phantom)
    assert result["passed"] is False
    assert any("INV-FAKE999" in v for v in result["hard_violations"]), result["hard_violations"]


def test_ratchet_floor_does_not_exceed_covered() -> None:
    result = check()
    assert result["coverage_floor"] <= result["covered_count"]


def test_strict_coverage_fails_closed_on_backlog() -> None:
    """--strict-coverage turns the named backlog into a hard failure."""
    result = check(strict_coverage=True)
    assert result["passed"] is False
    assert any("strict-coverage" in v for v in result["hard_violations"])


def test_recovery_command_must_be_executable_shaped() -> None:
    assert _RECOVERY_ACTION.search("raise SecondOrderDivergenceError; rerun with smaller dt")
    assert _RECOVERY_ACTION.search("return status INFEASIBLE")
    assert _RECOVERY_ACTION.search("regenerate the replay manifest and re-verify the hash")
    # Pure prose with no runnable action must be rejected.
    assert _RECOVERY_ACTION.search("be more careful next time") is None
    assert _RECOVERY_ACTION.search("the operator should look into it") is None


def test_inv_token_is_word_bounded() -> None:
    assert _INV_TOKEN.findall("guards INV-K8 and INV-HPC2 here") == ["INV-K8", "INV-HPC2"]
    assert _INV_TOKEN.findall("INVK8 inv-k8 INV_K8") == []


def test_scope_scan_finds_known_module() -> None:
    found = _modules_with_invariants(REPO_ROOT / "core" / "kuramoto")
    assert "core/kuramoto/second_order.py" in found
    assert "INV-K8" in found["core/kuramoto/second_order.py"]


def test_schema_rejects_entry_missing_required_field() -> None:
    pytest.importorskip("jsonschema")
    bad = {
        "version": 1,
        "coverage_floor": 0,
        "scope_roots": ["core/physics"],
        "modules": [
            {
                # missing failure_mode / blast_radius / degradation_mode / etc.
                "module": "core/physics/determinism_kit.py",
                "invariants": ["INV-DET1"],
                "role": "protector",
                "layer": "L2",
            }
        ],
    }
    errors = _schema_validate(bad)
    assert errors, "schema should reject an entry missing required fields"


def test_schema_file_is_valid_json() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "physics" / "reliability_contract.schema.json").read_text())
    assert schema["title"] == "Physics Module Reliability Contract"
