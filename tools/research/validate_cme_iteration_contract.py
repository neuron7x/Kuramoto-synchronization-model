#!/usr/bin/env python3
"""Validate a CME iteration contract.

The validator is intentionally standard-library only. It checks structure,
status-tag discipline, minimum command surface, and release-evidence honesty.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "iteration_id",
    "repository",
    "status_tags",
    "intent",
    "final_state",
    "first_missing_condition",
    "agent_plan",
    "files_to_create_modify",
    "implementation_tasks",
    "validation_commands",
    "benchmark_ablation",
    "failure_modes",
    "verdict_criteria",
    "next_cycle",
}

ALLOWED_STATUS_TAGS = {
    "S0_REPO_FACT",
    "S1_TESTED",
    "S2_LITERATURE",
    "S5_PROXY",
    "S6_SPECULATIVE",
    "X_FORBIDDEN",
}

REQUIRED_GOVERNANCE_KEYS = {
    "allowed_claims",
    "blocked_claim_phrase_policy",
}


def _require_non_empty_string(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-empty string")


def validate_contract(path: Path) -> dict[str, Any]:
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

    for key in ("intent", "final_state", "first_missing_condition", "next_cycle"):
        _require_non_empty_string(payload, key, errors)

    status_tags = payload.get("status_tags")
    if not isinstance(status_tags, list) or not status_tags:
        errors.append("status_tags must be a non-empty list")
    else:
        invalid_tags = sorted(tag for tag in status_tags if tag not in ALLOWED_STATUS_TAGS)
        if invalid_tags:
            errors.append(f"invalid status tags: {', '.join(invalid_tags)}")

    if isinstance(status_tags, list) and "S1_TESTED" in status_tags:
        evidence_fields = payload.get("evidence", {})
        if not isinstance(evidence_fields, dict) or not evidence_fields.get("commands_ran"):
            errors.append("S1_TESTED requires evidence.commands_ran")

    for list_key in (
        "agent_plan",
        "files_to_create_modify",
        "implementation_tasks",
        "validation_commands",
        "failure_modes",
        "verdict_criteria",
    ):
        value = payload.get(list_key)
        if not isinstance(value, list) or not value:
            errors.append(f"{list_key} must be a non-empty list")

    commands = payload.get("validation_commands")
    if isinstance(commands, list) and not any(
        "validate_cme_iteration_contract.py" in cmd for cmd in commands
    ):
        errors.append("validation_commands must include validate_cme_iteration_contract.py")

    first_missing = payload.get("first_missing_condition")
    if isinstance(first_missing, str) and " and " in first_missing.lower():
        errors.append(
            "first_missing_condition must stay singular and should not chain priorities with 'and'"
        )

    governance = payload.get("claim_governance")
    if not isinstance(governance, dict):
        errors.append("claim_governance must be present as an object")
    else:
        missing_governance = sorted(REQUIRED_GOVERNANCE_KEYS - governance.keys())
        if missing_governance:
            errors.append(f"missing claim_governance keys: {', '.join(missing_governance)}")
        allowed = governance.get("allowed_claims")
        if not isinstance(allowed, list) or not allowed:
            errors.append("claim_governance.allowed_claims must be a non-empty list")

    return {
        "status": "FAIL" if errors else "PASS",
        "contract": str(path),
        "required_fields": sorted(REQUIRED_FIELDS),
        "status_tags": status_tags,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate CME iteration contract JSON.")
    parser.add_argument(
        "path",
        nargs="?",
        default="docs/CME_ITERATION_0001.json",
        help="Path to CME iteration contract JSON.",
    )
    args = parser.parse_args(argv)

    result = validate_contract(Path(args.path))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
