from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "physics_validation" / "maturity_calibration_2026.json"
SCHEMA = ROOT / "schemas" / "physics_maturity_calibration.schema.json"


def test_maturity_calibration_artifact_shape() -> None:
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert payload["score_credit_allowed"] is False
    assert len(payload["adaptations"]) == 7
    assert len(payload["intentions"]) == 7
    assert len(payload["evolutions"]) == 7


def test_maturity_calibration_identifiers() -> None:
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert [item["id"] for item in payload["adaptations"]] == [
        "ADAPT-1",
        "ADAPT-2",
        "ADAPT-3",
        "ADAPT-4",
        "ADAPT-5",
        "ADAPT-6",
        "ADAPT-7",
    ]
    assert [item["id"] for item in payload["intentions"]] == [
        "INTENT-1",
        "INTENT-2",
        "INTENT-3",
        "INTENT-4",
        "INTENT-5",
        "INTENT-6",
        "INTENT-7",
    ]
    assert [item["id"] for item in payload["evolutions"]] == [
        "EVO-1",
        "EVO-2",
        "EVO-3",
        "EVO-4",
        "EVO-5",
        "EVO-6",
        "EVO-7",
    ]


def test_maturity_calibration_schema_exists() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["properties"]["score_credit_allowed"] == {"const": False}
    assert schema["properties"]["adaptations"]["minItems"] == 7
    assert schema["properties"]["intentions"]["minItems"] == 7
    assert schema["properties"]["evolutions"]["minItems"] == 7
