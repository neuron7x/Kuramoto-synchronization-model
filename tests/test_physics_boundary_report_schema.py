from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "physics_boundary_report.schema.json"
REPORT_PATH = ROOT / "data" / "physics_boundary_report.json"


class SchemaError(AssertionError):
    """Raised when the minimal schema validator rejects the report."""


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _type_matches(value, expected_type):
        raise SchemaError(f"{path}: expected {expected_type}")

    if "const" in schema and value != schema["const"]:
        raise SchemaError(f"{path}: expected const {schema['const']!r}")

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise SchemaError(f"{path}: value {value!r} not in enum")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise SchemaError(f"{path}: string shorter than {min_length}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            raise SchemaError(f"{path}: integer below minimum")
        if isinstance(maximum, int) and value > maximum:
            raise SchemaError(f"{path}: integer above maximum")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise SchemaError(f"{path}: array shorter than {min_items}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item_schema, item, f"{path}[{index}]")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [key for key in required if key not in value]
            if missing:
                raise SchemaError(f"{path}: missing required keys {missing}")

        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    _validate(child_schema, value[key], f"{path}.{key}")

        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaError(f"{path}: unexpected keys {extra}")


def test_physics_boundary_report_matches_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    try:
        import jsonschema
    except Exception:
        _validate(schema, report)
    else:
        jsonschema.Draft202012Validator(schema).validate(report)

    assert "total" in report["quality_score"]
    assert report["verdict"] in {"PASS", "FAIL"}
    assert report["first_missing_condition"].strip()
    assert report["role_2_handoff"]["files_to_create"]
    assert report["role_2_handoff"]["validation_commands"]
    assert not report["claim_audit"]["forbidden_claims_detected"], (
        "forbidden claims must be blocked before Role 1 can pass"
    )
