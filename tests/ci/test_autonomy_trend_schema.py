from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_trend_schema_version_and_digest_field() -> None:
    schema = json.loads((ROOT / "schemas" / "autonomy_trend.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "autonomy_trend.v1"
    entry = schema["properties"]["entries"]["items"]
    assert "cycle_sha256" in entry["required"]
    assert entry["properties"]["cycle_sha256"]["pattern"] == "^[0-9a-f]{64}$"
