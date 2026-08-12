#!/usr/bin/env python3
"""Validate a deterministic JSON artifact contract.

The validator is intentionally stdlib-only. It checks structure and evidence
semantics; it does not execute repository tests and does not assign scores.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL = (
    "contract_type",
    "objective",
    "inputs",
    "execution_plan",
    "python_runner_contract",
    "validation_tests",
    "failure_register",
    "evidence_status",
    "output_constraints",
    "next_deterministic_action",
    "final_verdict",
)

VALID_CONTRACT_TYPES = {
    "executable_task_contract",
    "external_validation_contract",
    "system_prompt_contract",
    "repository_repair_contract",
    "scoring_contract",
    "blocked_contract",
}

VALID_STATUSES = {
    "EXTERNAL_VERIFIED",
    "CI_VERIFIED",
    "TOOL_VERIFIED",
    "HUMAN_REVIEWED",
    "CANDIDATE_NOT_VALIDATED",
    "BLOCKED",
    "REJECTED",
}

VALID_EVIDENCE_SOURCES = {
    "unavailable",
    "python_runner",
    "tool_log",
    "ci_log",
    "parser_output",
    "benchmark_output",
    "human_review",
}

VALIDATED_STATUSES = {
    "EXTERNAL_VERIFIED",
    "CI_VERIFIED",
    "TOOL_VERIFIED",
    "HUMAN_REVIEWED",
}

VALID_TEST_TYPES = {
    "schema",
    "unit",
    "integration",
    "regression",
    "parser",
    "repository",
    "security",
    "artifact",
    "behavioral",
}

VALID_RUNNERS = {
    "python",
    "pytest",
    "jsonschema",
    "ruff",
    "mypy",
    "shell",
    "ci",
    "human_review",
}

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

OBJECT_FIELDS = (
    "objective",
    "inputs",
    "python_runner_contract",
    "evidence_status",
    "output_constraints",
    "final_verdict",
)

LIST_FIELDS = (
    "execution_plan",
    "validation_tests",
    "failure_register",
)

RUNNER_LIST_FIELDS = (
    "commands",
    "expected_artifacts",
    "success_criteria",
    "failure_criteria",
)

PLAN_FIELDS = (
    "step_id",
    "action",
    "input",
    "output",
    "tool_required",
    "failure_condition",
)

TEST_FIELDS = (
    "test_id",
    "test_type",
    "input",
    "expected_output",
    "runner",
    "pass_criteria",
    "fail_criteria",
)

FAILURE_FIELDS = (
    "failure",
    "cause",
    "impact",
    "detection",
    "mitigation",
    "severity",
)

DEFINITION_FIELDS = (
    "term",
    "operational_definition",
    "failure_condition",
    "validation_method",
)


def _load(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json:{exc.lineno}:{exc.colno}"]
    except OSError as exc:
        return None, [f"read_error:{exc}"]
    if not isinstance(data, dict):
        return None, ["root_must_be_object"]
    return data, []


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_string_fields(
    prefix: str, obj: dict[str, Any], fields: tuple[str, ...], errors: list[str]
) -> None:
    for field in fields:
        if not _is_nonempty_string(obj.get(field)):
            errors.append(f"{prefix}_{field}_must_be_nonempty_string")


def _validate_top_level_shape(data: dict[str, Any], errors: list[str]) -> None:
    contract_type = data.get("contract_type")
    if contract_type not in VALID_CONTRACT_TYPES:
        errors.append("invalid_contract_type")

    for key in OBJECT_FIELDS:
        if key in data and not isinstance(data[key], dict):
            errors.append(f"{key}_must_be_object")

    for key in LIST_FIELDS:
        if key in data and not isinstance(data[key], list):
            errors.append(f"{key}_must_be_list")

    definitions = data.get("definitions")
    if definitions is not None and not isinstance(definitions, list):
        errors.append("definitions_must_be_list")

    if not _is_nonempty_string(data.get("next_deterministic_action")):
        errors.append("next_deterministic_action_must_be_nonempty_string")


def _validate_objective(data: dict[str, Any], errors: list[str]) -> None:
    objective = data.get("objective")
    if not isinstance(objective, dict):
        return

    _require_string_fields(
        "objective",
        objective,
        ("target_state", "current_state", "transformation", "action_vector"),
        errors,
    )

    optimization = objective.get("optimization")
    if not isinstance(optimization, dict):
        errors.append("objective_optimization_must_be_object")
        return
    for key in ("minimize", "maximize"):
        if not isinstance(optimization.get(key), list):
            errors.append(f"objective_optimization_{key}_must_be_list")


def _validate_inputs(data: dict[str, Any], errors: list[str]) -> None:
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        return
    for key in ("required", "provided", "missing", "assumptions"):
        if not isinstance(inputs.get(key), list):
            errors.append(f"inputs_{key}_must_be_list")


def _validate_definitions(data: dict[str, Any], errors: list[str]) -> None:
    definitions = data.get("definitions")
    if definitions is None:
        return
    if not isinstance(definitions, list):
        return
    for idx, item in enumerate(definitions):
        if not isinstance(item, dict):
            errors.append(f"definitions_{idx}_must_be_object")
            continue
        _require_string_fields(f"definitions_{idx}", item, DEFINITION_FIELDS, errors)


def _validate_execution_plan(data: dict[str, Any], errors: list[str]) -> None:
    plan = data.get("execution_plan")
    if not isinstance(plan, list):
        return
    for idx, step in enumerate(plan):
        if not isinstance(step, dict):
            errors.append(f"execution_plan_{idx}_must_be_object")
            continue
        _require_string_fields(f"execution_plan_{idx}", step, PLAN_FIELDS, errors)


def _validate_tests(data: dict[str, Any], errors: list[str]) -> None:
    tests = data.get("validation_tests")
    if not isinstance(tests, list):
        return
    for idx, test in enumerate(tests):
        if not isinstance(test, dict):
            errors.append(f"validation_tests_{idx}_must_be_object")
            continue
        _require_string_fields(f"validation_tests_{idx}", test, TEST_FIELDS, errors)
        if test.get("test_type") not in VALID_TEST_TYPES:
            errors.append(f"validation_tests_{idx}_invalid_test_type")
        if test.get("runner") not in VALID_RUNNERS:
            errors.append(f"validation_tests_{idx}_invalid_runner")


def _validate_failure_register(data: dict[str, Any], errors: list[str]) -> None:
    register = data.get("failure_register")
    if not isinstance(register, list):
        return
    for idx, item in enumerate(register):
        if not isinstance(item, dict):
            errors.append(f"failure_register_{idx}_must_be_object")
            continue
        _require_string_fields(f"failure_register_{idx}", item, FAILURE_FIELDS, errors)
        if item.get("severity") not in VALID_SEVERITIES:
            errors.append(f"failure_register_{idx}_invalid_severity")


def _validate_runner_contract(data: dict[str, Any], errors: list[str]) -> None:
    runner = data.get("python_runner_contract")
    if not isinstance(runner, dict):
        return

    if not isinstance(runner.get("required"), bool):
        errors.append("runner_required_must_be_bool")
    if not _is_nonempty_string(runner.get("entrypoint")):
        errors.append("runner_entrypoint_must_be_nonempty_string")

    for key in RUNNER_LIST_FIELDS:
        if not isinstance(runner.get(key), list):
            errors.append(f"runner_{key}_must_be_list")

    timeout = runner.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        errors.append("runner_timeout_seconds_must_be_positive_int")


def validate_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"missing_top_level:{key}")

    _validate_top_level_shape(data, errors)
    _validate_objective(data, errors)
    _validate_inputs(data, errors)
    _validate_definitions(data, errors)
    _validate_execution_plan(data, errors)
    _validate_tests(data, errors)
    _validate_failure_register(data, errors)
    _validate_runner_contract(data, errors)

    contract_type = data.get("contract_type")
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    missing_inputs = inputs.get("missing") if isinstance(inputs, dict) else None

    evidence = data.get("evidence_status")
    verdict = data.get("final_verdict")

    if not isinstance(evidence, dict):
        errors.append("evidence_status_must_be_object")
        evidence = {}
    if not isinstance(verdict, dict):
        errors.append("final_verdict_must_be_object")
        verdict = {}

    external = evidence.get("external_evidence_available")
    if not isinstance(external, bool):
        errors.append("external_evidence_available_must_be_bool")
        external = False

    source = evidence.get("evidence_source")
    if source not in VALID_EVIDENCE_SOURCES:
        errors.append("invalid_evidence_source")

    score = evidence.get("score")
    confidence = evidence.get("confidence")
    evidence_status = evidence.get("status")
    final_status = verdict.get("status")
    tests_executed = evidence.get("tests_executed")
    tests_not_executed = evidence.get("tests_not_executed")
    evidence_required = verdict.get("evidence_required")

    if evidence_status not in VALID_STATUSES:
        errors.append("invalid_evidence_status")
    if final_status not in VALID_STATUSES:
        errors.append("invalid_final_status")
    if not isinstance(evidence_required, list):
        errors.append("final_evidence_required_must_be_list")
    if not _is_nonempty_string(verdict.get("reason")):
        errors.append("final_reason_must_be_nonempty_string")

    if not isinstance(tests_executed, list):
        errors.append("tests_executed_must_be_list")
    if not isinstance(tests_not_executed, list):
        errors.append("tests_not_executed_must_be_list")

    if score is not None and (not isinstance(score, (int, float)) or isinstance(score, bool)):
        errors.append("score_must_be_number_or_null")

    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        errors.append("confidence_must_be_number")
    elif not 0 <= float(confidence) <= 1:
        errors.append("confidence_out_of_range")

    if contract_type == "blocked_contract":
        if not isinstance(missing_inputs, list) or not missing_inputs:
            errors.append("blocked_contract_requires_missing_inputs")
        if evidence_status != "BLOCKED":
            errors.append("blocked_contract_evidence_status_must_be_blocked")
        if final_status != "BLOCKED":
            errors.append("blocked_contract_final_status_must_be_blocked")
        if score is not None:
            errors.append("score_requires_external_evidence")
    elif not external:
        if score is not None:
            errors.append("score_requires_external_evidence")
        if (
            confidence is not None
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
        ):
            if float(confidence) > 0.65:
                errors.append("confidence_too_high_without_evidence")
        if evidence_status != "CANDIDATE_NOT_VALIDATED":
            errors.append("evidence_status_must_be_candidate_without_evidence")
        if final_status != "CANDIDATE_NOT_VALIDATED":
            errors.append("final_status_must_be_candidate_without_evidence")

    if external:
        if source == "unavailable":
            errors.append("external_evidence_source_required")
        if final_status in VALIDATED_STATUSES and not tests_executed:
            errors.append("validated_status_requires_tests_executed")

    constraints = data.get("output_constraints")
    if not isinstance(constraints, dict):
        errors.append("output_constraints_must_be_object")
    else:
        for key in (
            "json_only",
            "no_markdown",
            "no_prose",
            "no_self_scoring",
            "no_simulated_tests",
            "no_validation_without_evidence",
            "minimize_tokens",
        ):
            if constraints.get(key) is not True:
                errors.append(f"constraint_not_true:{key}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a JSON artifact contract")
    parser.add_argument("path", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    data, errors = _load(args.path)
    if data is not None:
        errors.extend(validate_contract(data))

    result = {
        "schema_version": "json_artifact_contract_validator.v1",
        "input": str(args.path),
        "status": "OK" if not errors else "ERROR",
        "errors": errors,
    }

    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
