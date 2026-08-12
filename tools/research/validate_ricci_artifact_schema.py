#!/usr/bin/env python3
"""Validate Ricci microstructure inference artifacts against the canonical schema."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

DEFAULT_SCHEMA = Path("schemas/research/research_inference_artifact.schema.json")
DEFAULT_ARTIFACT = Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json")
CRITICAL_RICCI_FIELDS = {
    "conforms_to": str,
    "schema_version": str,
    "research_line": str,
    "run_id": str,
    "git_sha": str,
    "git_dirty": bool,
    "data_sha256": str,
    "config_sha256": str,
    "seed": int,
    "timestamp_utc": str,
    "input_window_sec": int,
    "score": (int, float),
    "uncertainty": (int, float),
    "decision": str,
    "claim_tier": str,
    "falsification_status": str,
}
CRITICAL_ENUMS = {
    "decision": {"ABSTAIN", "OBSERVE", "REJECT"},
    "claim_tier": {
        "HYPOTHESIS",
        "INSTRUMENTED",
        "MEASURED_SINGLE",
        "MEASURED_MULTI",
        "LIMITED_EMPIRICAL",
        "REJECTED",
        "BLOCKED_COST_MODEL",
    },
    "falsification_status": {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"},
}
HEX64_FIELDS = {"data_sha256", "config_sha256"}


def _die(message: str) -> NoReturn:
    print(f"ricci-artifact-schema: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _die(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        _die(f"invalid JSON in {path}: {exc}")


def _json_type_matches(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return True


def _format_path(parts: list[str]) -> str:
    return "/".join(parts) if parts else "<root>"


def _validate_datetime_z(value: str) -> bool:
    if not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _hardcoded_critical_validate(artifact: object, artifact_path: Path) -> list[str]:
    if not isinstance(artifact, dict):
        return [f"{artifact_path}: <root>: expected object"]
    errors: list[str] = []
    for field, expected_type in CRITICAL_RICCI_FIELDS.items():
        if field not in artifact:
            errors.append(f"{artifact_path}: {field}: critical property is missing")
            continue
        value = artifact[field]
        if expected_type is int:
            valid_type = isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == (int, float):
            valid_type = isinstance(value, int | float) and not isinstance(value, bool)
        else:
            valid_type = isinstance(value, expected_type)
        if not valid_type:
            errors.append(f"{artifact_path}: {field}: critical type mismatch")
            continue
        if (
            field in HEX64_FIELDS
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is None
        ):
            errors.append(f"{artifact_path}: {field}: expected lowercase sha256 hex")
        if (
            field == "git_sha"
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{40}", value) is None
        ):
            errors.append(f"{artifact_path}: {field}: expected lowercase git sha")
        if field == "timestamp_utc" and isinstance(value, str) and not _validate_datetime_z(value):
            errors.append(f"{artifact_path}: {field}: expected UTC date-time")
        enum = CRITICAL_ENUMS.get(field)
        if enum is not None and value not in enum:
            errors.append(f"{artifact_path}: {field}: {value!r} is not one of {sorted(enum)!r}")
    return errors


def _fallback_validate(schema: dict[str, Any], artifact: object, artifact_path: Path) -> list[str]:
    """Validate the repository's simple Ricci schema without third-party deps."""
    errors: list[str] = []
    if not _json_type_matches(artifact, str(schema.get("type", "object"))):
        return [f"{artifact_path}: <root>: expected {schema.get('type')}"]
    if not isinstance(artifact, dict):
        return [f"{artifact_path}: <root>: expected object"]

    errors.extend(_hardcoded_critical_validate(artifact, artifact_path))

    required = schema.get("required", [])
    if isinstance(required, list):
        for field in required:
            if field not in artifact:
                errors.append(f"{artifact_path}: {field}: required property is missing")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return errors

    if schema.get("additionalProperties") is False:
        for field in sorted(set(artifact) - set(properties)):
            errors.append(f"{artifact_path}: {field}: additional property is not allowed")

    for field, rules in properties.items():
        if field not in artifact or not isinstance(rules, dict):
            continue
        value = artifact[field]
        expected_type = rules.get("type")
        if isinstance(expected_type, str) and not _json_type_matches(value, expected_type):
            errors.append(f"{artifact_path}: {field}: expected {expected_type}")
            continue
        pattern = rules.get("pattern")
        if (
            isinstance(pattern, str)
            and isinstance(value, str)
            and re.search(pattern, value) is None
        ):
            errors.append(f"{artifact_path}: {field}: {value!r} does not match {pattern!r}")
        enum = rules.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"{artifact_path}: {field}: {value!r} is not one of {enum!r}")
        minimum = rules.get("minimum")
        if isinstance(minimum, int | float) and isinstance(value, int | float) and value < minimum:
            errors.append(f"{artifact_path}: {field}: {value!r} is less than {minimum!r}")
        maximum = rules.get("maximum")
        if isinstance(maximum, int | float) and isinstance(value, int | float) and value > maximum:
            errors.append(f"{artifact_path}: {field}: {value!r} is greater than {maximum!r}")
        if (
            rules.get("format") == "date-time"
            and isinstance(value, str)
            and not _validate_datetime_z(value)
        ):
            errors.append(f"{artifact_path}: {field}: {value!r} is not a UTC date-time")
    return errors


def _jsonschema_validate(
    schema: dict[str, Any], artifact: object, artifact_path: Path
) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{artifact_path}: {_format_path([str(part) for part in error.absolute_path])}: {error.message}"
        for error in sorted(validator.iter_errors(artifact), key=lambda item: item.path)
    ]


def validate_artifact(schema_path: Path, artifact_path: Path) -> list[str]:
    """Return schema validation errors for one artifact path."""
    schema = _load_json(schema_path)
    artifact = _load_json(artifact_path)
    if not isinstance(schema, dict):
        _die(f"schema root must be an object: {schema_path}")

    if importlib.util.find_spec("jsonschema") is not None:
        return _jsonschema_validate(schema, artifact, artifact_path)
    return _fallback_validate(schema, artifact, artifact_path)


def _load_truth_gate() -> Any:
    """Path-load the canonical semantic-truth gate (single source of rules)."""
    gate_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_research_artifact_truth.py"
    )
    spec = importlib.util.spec_from_file_location("_research_artifact_truth", gate_path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        _die(f"cannot load semantic-truth gate at {gate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_artifact_semantics(schema_path: Path, artifact_path: Path) -> list[str]:
    """Validate an artifact for SHAPE (schema) then TRUTH (semantics).

    Schema validity proves the artifact has the right fields; it cannot stop a
    hand-typed score with a zero data hash and ``falsification_status: PASS``.
    This runs schema validation first (short-circuiting on shape errors) and
    then the canonical semantic-truth rules so that schema-valid fakes are
    rejected. An evidence-bearing artifact may not use zero hashes; a zero-hash
    artifact must label itself an honest, non-PASS placeholder.
    """
    schema_errors = validate_artifact(schema_path, artifact_path)
    if schema_errors:
        return schema_errors
    artifact = _load_json(artifact_path)
    if not isinstance(artifact, dict):  # pragma: no cover - schema already guards this
        return [f"{artifact_path}: <root>: expected object"]
    gate = _load_truth_gate()
    semantic_errors: list[str] = gate.evaluate_artifact(artifact_path, artifact)
    return semantic_errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        default=None,
        help="Artifact JSON to validate. May be passed more than once.",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Also enforce semantic-truth rules (schema-valid is not enough).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    artifacts = args.artifact or [DEFAULT_ARTIFACT]

    failures: list[str] = []
    for artifact_path in artifacts:
        if args.semantic:
            failures.extend(validate_artifact_semantics(args.schema, artifact_path))
        else:
            failures.extend(validate_artifact(args.schema, artifact_path))

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    mode = "semantically + schema" if args.semantic else "schema"
    print(f"Validated {len(artifacts)} Ricci artifact(s) ({mode}) against {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
