from __future__ import annotations

import json
from pathlib import Path

from tools.generate_json_contract_validation_bundle import build, main

ROOT = Path(__file__).resolve().parents[2]


def test_bundle_accepts_fixtures() -> None:
    result = build([
        ROOT / "examples/json_artifact_contract.candidate.json",
        ROOT / "examples/json_artifact_contract.blocked.json",
    ])
    assert result["status"] == "OK"


def test_bundle_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "bundle.json"
    assert main(["--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "json_contract_validation_bundle.v1"
    assert data["status"] == "OK"
