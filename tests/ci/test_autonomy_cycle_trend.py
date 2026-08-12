from __future__ import annotations

import json
from pathlib import Path

from tools.run_autonomy_cycle import main


def test_cycle_writes_trend_update_marker(tmp_path: Path, monkeypatch) -> None:
    def fake_phase(root: Path, spec: dict[str, object]) -> dict[str, object]:
        return {
            "phase": spec["phase"],
            "status": "OK",
            "artifact": spec["artifact"],
            "command": spec["command"],
            "returncode": 0,
            "stderr": "",
        }

    def fake_trend(root: Path, cycle_path: Path, ledger_path: Path) -> dict[str, object]:
        assert cycle_path.name == "cycle.json"
        assert ledger_path.name == "trend.json"
        return {"returncode": 0, "stderr": ""}

    monkeypatch.setattr("tools.run_autonomy_cycle._phase_result", fake_phase)
    monkeypatch.setattr("tools.run_autonomy_cycle._update_trend", fake_trend)
    assert main(["--root", str(tmp_path), "--out", "cycle.json", "--trend-ledger", "trend.json"]) == 0
    payload = json.loads((tmp_path / "cycle.json").read_text(encoding="utf-8"))
    assert payload["trend_update"]["returncode"] == 0


def test_cycle_can_skip_trend(tmp_path: Path, monkeypatch) -> None:
    def fake_phase(root: Path, spec: dict[str, object]) -> dict[str, object]:
        return {
            "phase": spec["phase"],
            "status": "OK",
            "artifact": spec["artifact"],
            "command": spec["command"],
            "returncode": 0,
            "stderr": "",
        }

    monkeypatch.setattr("tools.run_autonomy_cycle._phase_result", fake_phase)
    assert main(["--root", str(tmp_path), "--out", "cycle.json", "--no-trend"]) == 0
    payload = json.loads((tmp_path / "cycle.json").read_text(encoding="utf-8"))
    assert "trend_update" not in payload
