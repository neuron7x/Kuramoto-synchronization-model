# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Calibration sensitivity-drift gate — self-falsification proof.

``scripts/ci/check_calibration_drift.py`` must PASS on the shipped
``governance/CALIBRATIONS.yaml`` and FAIL CLOSED on every kind of silent
drift: a changed source hash, a missing sweep, a missing selected value, a
missing failure policy, or an acceptor that does not bind the calibration
module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_calibration_drift.py"
REGISTRY_PATH = ROOT / "governance" / "CALIBRATIONS.yaml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_calibration_drift", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_calibration_drift"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load()


@pytest.fixture(scope="module")
def live() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


def _entry(live: dict[str, Any]) -> dict[str, Any]:
    return dict(live["calibrations"][0])


def _write(tmp_path: Path, cals: list[dict[str, Any]]) -> Path:
    p = tmp_path / "CALIBRATIONS.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 1, "calibrations": cals}, sort_keys=False), encoding="utf-8")
    return p


def _run(gate: Any, path: Path) -> int:
    return gate.main(["--registry", str(path)])


def test_live_registry_passes(gate: Any) -> None:
    assert _run(gate, REGISTRY_PATH) == 0


def test_source_drift_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["source_sha256"] = "0" * 64
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_sweep_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["sweep"] = ""
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_selected_value_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    del e["selected_value"]
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_failure_policy_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    del e["failure_policy"]
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_acceptor_not_binding_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    # an acceptor that exists but binds a different module
    e["acceptor"] = ".claude/commit_acceptors/null-baseline-fixtures.yaml"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_module_fails(gate: Any, live: dict[str, Any], tmp_path: Path) -> None:
    e = _entry(live)
    e["module"] = "analytics/signals/does_not_exist.py"
    assert _run(gate, _write(tmp_path, [e])) == 1


def test_missing_registry_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, tmp_path / "absent.yaml") == 2


def test_empty_calibrations_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [])) == 2
