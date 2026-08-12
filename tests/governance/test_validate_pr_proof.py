# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/governance/validate_pr_proof.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "tools" / "governance" / "validate_pr_proof.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vpp", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vpp"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vpp() -> ModuleType:
    return _load()


def _good_proof(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pr_number": 999,
        "lie_blocked": "missing data = true absence",
        "files_changed": ["geosync_hpc/regimes/structured_absence.py"],
        "tests_run": ["pytest tests/unit/regimes/test_structured_absence.py"],
        "falsifier_command": "sed -i 's/if bias_present:/if False:/' geosync_hpc/regimes/structured_absence.py",
        "falsifier_expected_failure": [
            "tests/unit/regimes/test_structured_absence.py::test_active_selection_bias_returns_selection_bias"
        ],
        "restore_command": "git checkout -- geosync_hpc/regimes/structured_absence.py",
        "evidence_paths": [".claude/research/PHYSICS_2026_TRANSLATION.yaml"],
        "remaining_uncertainty": "selection_bias_flags shape is caller's contract, not enforced.",
        "closure_status": "CLOSED",
    }
    base.update(overrides)
    return base


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_good_proof_validates_clean(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof())
    report = vpp.validate_proofs_dir(proofs_dir)
    assert report.valid, [str(e) for e in report.errors]
    assert report.proof_count == 1


def test_missing_lie_blocked_fails(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    bad = _good_proof()
    del bad["lie_blocked"]
    _write(proofs_dir / "PR999.yaml", bad)
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("lie_blocked" in str(e) for e in report.errors)


def test_missing_falsifier_command_fails(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    bad = _good_proof()
    del bad["falsifier_command"]
    _write(proofs_dir / "PR999.yaml", bad)
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("falsifier_command" in str(e) for e in report.errors)


def test_missing_restore_command_fails(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    bad = _good_proof()
    del bad["restore_command"]
    _write(proofs_dir / "PR999.yaml", bad)
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("restore_command" in str(e) for e in report.errors)


def test_empty_tests_run_fails(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof(tests_run=[]))
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("tests_run" in str(e) for e in report.errors)


def test_closed_without_evidence_paths_fails(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof(evidence_paths=[]))
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("evidence_paths" in str(e) for e in report.errors)


def test_partial_status_allowed_with_uncertainty(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(
        proofs_dir / "PR999.yaml",
        _good_proof(
            closure_status="PARTIAL",
            remaining_uncertainty="P10 module exists but the chain only wires P1..P6 mandatorily",
        ),
    )
    report = vpp.validate_proofs_dir(proofs_dir)
    assert report.valid


def test_blocked_status_allowed(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(
        proofs_dir / "PR999.yaml",
        _good_proof(
            closure_status="BLOCKED",
            remaining_uncertainty="upstream stub fix required before this PR can advance",
        ),
    )
    report = vpp.validate_proofs_dir(proofs_dir)
    assert report.valid


def test_invalid_closure_status_rejected(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof(closure_status="DONE"))
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("closure_status" in str(e) for e in report.errors)


def test_pr_number_must_be_positive_int(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof(pr_number=0))
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any("pr_number" in str(e).lower() for e in report.errors)


def test_yaml_parse_error_reported(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    (proofs_dir / "PR1.yaml").write_text("not: valid: yaml: ::: {", encoding="utf-8")
    report = vpp.validate_proofs_dir(proofs_dir)
    assert not report.valid
    assert any(e.rule == "YAML_PARSE_ERROR" for e in report.errors)


def test_empty_dir_validates_clean(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    report = vpp.validate_proofs_dir(proofs_dir)
    assert report.valid
    assert report.proof_count == 0


def test_main_exits_zero_on_clean(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    _write(proofs_dir / "PR999.yaml", _good_proof())
    output = tmp_path / "report.json"
    rc = vpp.main(["--proofs-dir", str(proofs_dir), "--output", str(output)])
    assert rc == 0


def test_main_exits_one_on_bad_proof(vpp: ModuleType, tmp_path: Path) -> None:
    proofs_dir = tmp_path / "pr_proofs"
    proofs_dir.mkdir()
    bad = _good_proof()
    del bad["falsifier_command"]
    _write(proofs_dir / "PR999.yaml", bad)
    output = tmp_path / "report.json"
    rc = vpp.main(["--proofs-dir", str(proofs_dir), "--output", str(output)])
    assert rc == 1
