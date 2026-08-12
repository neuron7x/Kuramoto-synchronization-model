# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for company-grade value-function governance."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "tools" / "governance" / "check_company_value_functions.py"
MANIFEST = ROOT / "data" / "governance" / "company_value_functions.json"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("value_gate", GATE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["value_gate"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_live_company_value_function_manifest_is_valid() -> None:
    gate = _load_gate()
    assert gate.check(MANIFEST) == []


def test_live_company_value_function_self_test_is_clean() -> None:
    gate = _load_gate()
    assert gate.self_test(MANIFEST, ROOT) == []


def test_gate_rejects_weight_drift(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    value_functions = data["value_functions"]
    assert isinstance(value_functions, list)
    value_functions[0]["weight"] = 0.50
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("weights must sum to 1.0" in error for error in errors)


def test_gate_rejects_softening_hard_constraint_policy(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    decision_rule = data["decision_rule"]
    assert isinstance(decision_rule, dict)
    decision_rule["fail_closed_on_missing_evidence"] = False
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("fail_closed_on_missing_evidence" in error for error in errors)


def test_gate_rejects_value_without_executable_evidence(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    value_functions = data["value_functions"]
    assert isinstance(value_functions, list)
    value_functions[0]["evidence_surfaces"] = ["docs/only_prose.md"]
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("executable/CI" in error for error in errors)


def test_gate_rejects_missing_failure_modes(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    value_functions = data["value_functions"]
    assert isinstance(value_functions, list)
    value_functions[1]["failure_modes"] = []
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("failure_modes must be a non-empty list" in error for error in errors)


def test_gate_rejects_missing_evidence_surface(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    value_functions = data["value_functions"]
    assert isinstance(value_functions, list)
    value_functions[0]["evidence_surfaces"].append("tools/missing_value_gate.py")
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("evidence surface does not exist" in error for error in errors)
    assert any("tools/missing_value_gate.py" in error for error in errors)


def test_gate_rejects_hard_constraint_without_ci_surface(tmp_path: Path) -> None:
    gate = _load_gate()
    data = deepcopy(_manifest())
    value_functions = data["value_functions"]
    assert isinstance(value_functions, list)
    value_functions[0]["evidence_surfaces"] = [
        "constraints/security.txt",
        "requirements-scan.txt",
        "tools/deps/check_operational_dependency_determinism.py",
    ]
    manifest = tmp_path / "company_value_functions.json"
    _write(manifest, data)
    errors = gate.check(manifest)
    assert any("hard constraints must include a CI workflow surface" in error for error in errors)
