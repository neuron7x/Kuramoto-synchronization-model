#!/usr/bin/env python3
"""Validate a CME operator contract.

The validator is intentionally standard-library only. It checks that an operator
is not just a term definition but a runnable engineering contract with inputs,
outputs, acceptance gates, failure modes, validation commands, and evidence
policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "operator_id",
    "name",
    "ukrainian_name",
    "repository",
    "status_tags",
    "definition",
    "operator_form",
    "inputs",
    "outputs",
    "acceptance_gates",
    "failure_modes",
    "validation_commands",
    "next_target",
    "evidence_policy",
}

ALLOWED_STATUS_TAGS = {
    "S0_REPO_FACT",
    "S1_TESTED",
    "S2_LITERATURE",
    "S5_PROXY",
    "S6_SPECULATIVE",
    "X_FORBIDDEN",
}

REQUIRED_LIST_FIELDS = {
    "inputs",
    "outputs",
    "acceptance_gates",
    "failure_modes",
    "validation_commands",
}

OPERATOR_REQUIRED_OUTPUTS = {
    "integrate": {"integration_contract", "smoke_path", "rollback_path"},
    "validate": {"validation_report", "pass_fail_decision", "evidence_record"},
    "normalize": {"normalized_values", "normalization_metadata", "loss_report"},
}

OPERATOR_REQUIRED_INPUTS = {
    "integrate": {"modules_or_services", "input_output_contracts", "validation_commands"},
    "validate": {"candidate_result", "expected_contract", "validation_method"},
    "normalize": {"raw_values", "scale_contract", "provenance_record"},
}


def _require_non_empty_string(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-empty string")


def _require_named_items(
    payload: dict[str, Any],
    field_name: str,
    expected: dict[str, set[str]],
    errors: list[str],
) -> None:
    operator_name = payload.get("name")
    required_items = expected.get(operator_name)
    if not required_items:
        return

    values = payload.get(field_name)
    if not isinstance(values, list):
        return

    missing_items = sorted(required_items - set(values))
    if missing_items:
        errors.append(f"{operator_name} operator missing {field_name}: {', '.join(missing_items)}")


def validate_operator_contract(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "FAIL", "errors": [f"missing file: {path}"]}
    except json.JSONDecodeError as exc:
        return {"status": "FAIL", "errors": [f"invalid json: {exc}"]}

    if not isinstance(payload, dict):
        return {"status": "FAIL", "errors": ["top-level contract must be a JSON object"]}

    missing = sorted(REQUIRED_FIELDS - payload.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")

    for key in (
        "operator_id",
        "name",
        "ukrainian_name",
        "repository",
        "definition",
        "operator_form",
        "next_target",
        "evidence_policy",
    ):
        _require_non_empty_string(payload, key, errors)

    status_tags = payload.get("status_tags")
    if not isinstance(status_tags, list) or not status_tags:
        errors.append("status_tags must be a non-empty list")
    else:
        invalid_tags = sorted(tag for tag in status_tags if tag not in ALLOWED_STATUS_TAGS)
        if invalid_tags:
            errors.append(f"invalid status tags: {', '.join(invalid_tags)}")

    if isinstance(status_tags, list) and "S1_TESTED" in status_tags:
        evidence = payload.get("evidence", {})
        if not isinstance(evidence, dict) or not evidence.get("commands_ran"):
            errors.append("S1_TESTED requires evidence.commands_ran")

    for key in REQUIRED_LIST_FIELDS:
        value = payload.get(key)
        if not isinstance(value, list) or not value:
            errors.append(f"{key} must be a non-empty list")
        elif not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{key} must contain only non-empty strings")

    commands = payload.get("validation_commands")
    if isinstance(commands, list) and not any(
        "validate_operator_contract.py" in cmd for cmd in commands
    ):
        errors.append("validation_commands must include validate_operator_contract.py")

    _require_named_items(payload, "inputs", OPERATOR_REQUIRED_INPUTS, errors)
    _require_named_items(payload, "outputs", OPERATOR_REQUIRED_OUTPUTS, errors)

    return {
        "status": "FAIL" if errors else "PASS",
        "contract": str(path),
        "required_fields": sorted(REQUIRED_FIELDS),
        "status_tags": status_tags,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate CME operator contract JSON.")
    parser.add_argument(
        "path",
        nargs="?",
        default="docs/operators/integrate_operator.json",
        help="Path to CME operator contract JSON.",
    )
    args = parser.parse_args(argv)

    result = validate_operator_contract(Path(args.path))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
