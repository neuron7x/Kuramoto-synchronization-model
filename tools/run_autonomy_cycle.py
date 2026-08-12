#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "autonomy_cycle.v1"

PHASES = (
    {
        "phase": "observe",
        "command": [sys.executable, "tools/mfn_surface_check.py"],
        "artifact": "artifacts/validation/mfn_surface_state.json",
    },
    {
        "phase": "validate",
        "command": [sys.executable, "tools/run_json_artifact_checks.py"],
        "artifact": "artifacts/validation/json_artifact_checks.json",
    },
    {
        "phase": "receipt",
        "command": [
            sys.executable,
            "tools/json_contract_receipt.py",
            "--out",
            "artifacts/validation/json_contract_receipt.json",
        ],
        "artifact": "artifacts/validation/json_contract_receipt.json",
    },
)


def _run(command: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, cwd=cwd
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _phase_result(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    executed = _run(spec["command"], root)
    artifact = root / spec["artifact"]
    parsed = _read_json(artifact)
    status = "OK" if executed["returncode"] == 0 else "RED"
    if parsed and isinstance(parsed.get("status"), str):
        status = parsed["status"]
    return {
        "phase": spec["phase"],
        "status": status,
        "artifact": spec["artifact"],
        "command": executed["command"],
        "returncode": executed["returncode"],
        "stderr": executed["stderr"],
    }


def _decision(phases: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(item["status"]) for item in phases]
    if "RED" in statuses or "ERROR" in statuses:
        state = "REPAIR_REQUIRED"
    elif "UNKNOWN" in statuses:
        state = "EVIDENCE_GAP"
    elif "WARN" in statuses:
        state = "OBSERVE_WITH_DEBT"
    else:
        state = "READY_FOR_NEXT_CYCLE"
    return {"state": state, "status_vector": statuses}


def build_payload(root: Path) -> dict[str, Any]:
    phases = [_phase_result(root, spec) for spec in PHASES]
    return {
        "schema_version": SCHEMA_VERSION,
        "objective": "observe_diverge_converge_artifact_validation_surface",
        "phases": phases,
        "decision": _decision(phases),
    }


def _update_trend(root: Path, cycle_path: Path, ledger_path: Path) -> dict[str, Any]:
    return _run(
        [
            sys.executable,
            "tools/update_autonomy_trend.py",
            "--cycle",
            str(cycle_path.relative_to(root)),
            "--ledger",
            str(ledger_path.relative_to(root)),
        ],
        root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="artifacts/validation/autonomy_cycle.json")
    parser.add_argument("--trend-ledger", default="artifacts/validation/autonomy_trend.json")
    parser.add_argument("--no-trend", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(root)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    trend = None if args.no_trend else _update_trend(root, out, root / args.trend_ledger)
    if trend is not None:
        payload["trend_update"] = {"returncode": trend["returncode"], "stderr": trend["stderr"]}
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if trend is not None and trend["returncode"] != 0:
        return 1
    return 0 if payload["decision"]["state"] in {"READY_FOR_NEXT_CYCLE", "OBSERVE_WITH_DEBT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
