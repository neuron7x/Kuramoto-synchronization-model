from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tools.run_autonomy_cycle import _decision, _run, build_payload

ROOT = Path(__file__).resolve().parents[2]


def test_decision_orders_states() -> None:
    assert _decision([{"status": "OK"}])["state"] == "READY_FOR_NEXT_CYCLE"
    assert _decision([{"status": "WARN"}])["state"] == "OBSERVE_WITH_DEBT"
    assert _decision([{"status": "UNKNOWN"}])["state"] == "EVIDENCE_GAP"
    assert _decision([{"status": "RED"}])["state"] == "REPAIR_REQUIRED"
    assert _decision([{"status": "ERROR"}])["state"] == "REPAIR_REQUIRED"


def test_autonomy_cycle_payload_shape(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_phase(root: Path, spec: dict[str, object]) -> dict[str, object]:
        calls.append(cast("list[str]", spec["command"]))
        return {
            "phase": spec["phase"],
            "status": "OK",
            "artifact": spec["artifact"],
            "command": spec["command"],
            "returncode": 0,
            "stderr": "",
        }

    monkeypatch.setattr("tools.run_autonomy_cycle._phase_result", fake_phase)
    payload = build_payload(tmp_path)
    assert payload["schema_version"] == "autonomy_cycle.v1"
    assert payload["decision"]["state"] == "READY_FOR_NEXT_CYCLE"
    assert [item["phase"] for item in payload["phases"]] == ["observe", "validate", "receipt"]
    assert len(calls) == 3


def test_run_uses_declared_root(tmp_path: Path) -> None:
    result = _run(["python", "-c", "from pathlib import Path; print(Path.cwd())"], tmp_path)
    assert result["returncode"] == 0
    assert result["stdout"].strip() == str(tmp_path)


def test_autonomy_cycle_schema_file_is_parseable() -> None:
    schema = json.loads((ROOT / "schemas" / "autonomy_cycle.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "autonomy_cycle.v1"
    assert "REPAIR_REQUIRED" in schema["properties"]["decision"]["properties"]["state"]["enum"]
    assert schema["properties"]["trend_update"]["required"] == ["returncode", "stderr"]


def test_autonomy_cycle_schema_accepts_written_trend_update_shape() -> None:
    schema = json.loads((ROOT / "schemas" / "autonomy_cycle.schema.json").read_text(encoding="utf-8"))
    trend = schema["properties"]["trend_update"]
    assert trend["additionalProperties"] is False
    assert trend["properties"]["returncode"]["type"] == "integer"
    assert trend["properties"]["stderr"]["type"] == "string"
