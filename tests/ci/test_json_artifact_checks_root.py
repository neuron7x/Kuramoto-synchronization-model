from __future__ import annotations

import json
from pathlib import Path

from tools import run_json_artifact_checks as checks


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_runner_uses_supplied_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    examples = root / "examples"
    tools = root / "tools"
    _write(examples / "json_artifact_contract.candidate.json", "{}")
    _write(examples / "json_artifact_contract.blocked.json", "{}")
    _write(tools / "validate_json_artifact_contract.py", "import sys\nsys.exit(0)\n")
    _write(tools / "check_json_contract_evidence_policy.py", "import sys\nsys.exit(0)\n")
    _write(tools / "json_contract_receipt.py", "import argparse, pathlib\np=argparse.ArgumentParser(); p.add_argument('--out'); a=p.parse_args(); pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True); pathlib.Path(a.out).write_text('{}')\n")
    monkeypatch.chdir(tmp_path)
    out = "artifacts/validation/checks.json"
    assert checks.main(["--root", str(root), "--out", out]) == 0
    payload = json.loads((root / out).read_text(encoding="utf-8"))
    assert payload["status"] == "OK"
    assert len(payload["results"]) == 5
