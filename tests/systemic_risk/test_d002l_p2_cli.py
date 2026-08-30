# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI fail-closed tests for D-002L-P2."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from scripts import x10r_d002l_p2_power_gate as cli

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_P1_STATUS = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_execution_status_v1.json"


def _event_rows() -> list[dict]:
    # Reuse test helper only as a synthetic fixture; no scientific data.
    from tests.systemic_risk.test_d002l_p2_power_gate import _registry
    return _registry()["events"]


def _write(path: Path, obj: dict) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _pass_inputs(tmp_path: Path, *, point: float = 1.0) -> dict[str, Path]:
    from tests.systemic_risk.test_d002l_p2_power_gate import _noise, _p1_pass, _prior
    status = _p1_pass()
    registry = {
        "node_id": "D002L-P1",
        "confirmatory_outcomes_ingested": False,
        "next_phase_authorized": "D002L-P2",
        "events": _event_rows(),
    }
    return {
        "status": _write(tmp_path / "status.json", status),
        "registry": _write(tmp_path / "registry.json", registry),
        "noise": _write(tmp_path / "noise.json", _noise()),
        "prior": _write(tmp_path / "prior.json", _prior(point=point)),
        "out": tmp_path / "out.json",
    }


def _set_argv(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x10r_d002l_p2_power_gate.py",
            "--p1-status", str(paths["status"]),
            "--registry", str(paths["registry"]),
            "--calibration-noise", str(paths["noise"]),
            "--effect-prior", str(paths["prior"]),
            "--out", str(paths["out"]),
        ],
    )


def test_cli_current_real_p1_blocker_exits_10_before_downstream_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.json"
    paths = {
        "status": CURRENT_P1_STATUS,
        "registry": missing,
        "noise": missing,
        "prior": missing,
        "out": tmp_path / "should-not-exist.json",
    }
    _set_argv(monkeypatch, paths)
    assert cli.main() == 10
    assert "P1_NOT_TERMINAL_PASS" in capsys.readouterr().err
    assert not paths["out"].exists()


def test_cli_synthetic_pass_writes_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _pass_inputs(tmp_path, point=1.0)
    _set_argv(monkeypatch, paths)
    assert cli.main() == 0
    result = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert result["status"] == "TERMINAL_PASS"
    assert result["canonical_run_authorized"] is False


def test_cli_synthetic_refusal_exits_11(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _pass_inputs(tmp_path, point=0.4)
    _set_argv(monkeypatch, paths)
    assert cli.main() == 11
    result = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert result["status"] == "TERMINAL_REFUSED"


def test_cli_unexpected_exception_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _pass_inputs(tmp_path)
    _set_argv(monkeypatch, paths)
    monkeypatch.setattr(cli, "execute_from_paths", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cli.main() == 10
    assert "RuntimeError:boom" in capsys.readouterr().err
    assert not paths["out"].exists()
