#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FIXTURES = ("candidate", "blocked")
SCHEMA_VERSION = "json_artifact_checks.v1"


def run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, cwd=cwd
    )
    return {"cmd": cmd, "code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def build_payload(root: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name in FIXTURES:
        fixture = f"examples/json_artifact_contract.{name}.json"
        results.append(
            run([sys.executable, "tools/validate_json_artifact_contract.py", fixture], root)
        )
        results.append(
            run([sys.executable, "tools/check_json_contract_evidence_policy.py", fixture], root)
        )
    receipt_cmd = [
        sys.executable,
        "tools/json_contract_receipt.py",
        "--out",
        "artifacts/validation/json_contract_receipt.json",
    ]
    results.append(run(receipt_cmd, root))
    status = "OK" if all(item["code"] == 0 for item in results) else "ERROR"
    return {"schema_version": SCHEMA_VERSION, "status": status, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="artifacts/validation/json_artifact_checks.json")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(root)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
