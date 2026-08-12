from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.validate_json_artifact_contract import main, validate_contract

ROOT = Path(__file__).resolve().parents[2]


def _candidate() -> dict[str, object]:
    return {
        "contract_type": "repository_repair_contract",
        "objective": {
            "target_state": "external validation ready",
            "current_state": "no runner evidence",
            "transformation": "emit contract",
            "action_vector": "earn -> exit -> build systems",
            "optimization": {
                "minimize": ["E_stress", "H_entropy", "epsilon_error"],
                "maximize": ["V_system", "V_autonomy", "V_verified_progress"],
            },
        },
        "inputs": {"required": [], "provided": [], "missing": [], "assumptions": []},
        "definitions": [],
        "execution_plan": [],
        "python_runner_contract": {
            "required": True,
            "entrypoint": "validate_json_artifact_contract.py",
            "commands": [],
            "expected_artifacts": [],
            "timeout_seconds": 300,
            "success_criteria": [],
            "failure_criteria": [],
        },
        "validation_tests": [],
        "failure_register": [],
        "evidence_status": {
            "external_evidence_available": False,
            "evidence_source": "unavailable",
            "tests_executed": [],
            "tests_not_executed": [],
            "score": None,
            "confidence": 0.65,
            "status": "CANDIDATE_NOT_VALIDATED",
        },
        "output_constraints": {
            "json_only": True,
            "no_markdown": True,
            "no_prose": True,
            "no_self_scoring": True,
            "no_simulated_tests": True,
            "no_validation_without_evidence": True,
            "minimize_tokens": True,
        },
        "next_deterministic_action": "run external validator",
        "final_verdict": {
            "status": "CANDIDATE_NOT_VALIDATED",
            "reason": "external evidence absent",
            "evidence_required": [],
        },
    }


def test_candidate_contract_is_accepted() -> None:
    assert validate_contract(_candidate()) == []


def test_repository_candidate_fixture_is_accepted() -> None:
    fixture = ROOT / "examples/json_artifact_contract.candidate.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))

    assert validate_contract(data) == []


def test_repository_blocked_fixture_is_accepted() -> None:
    fixture = ROOT / "examples/json_artifact_contract.blocked.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))

    assert validate_contract(data) == []


def test_missing_top_level_field_is_reported() -> None:
    payload = _candidate()
    payload.pop("execution_plan")

    assert "missing_top_level:execution_plan" in validate_contract(payload)


def test_contract_type_must_be_known() -> None:
    payload = _candidate()
    payload["contract_type"] = "invented"

    assert "invalid_contract_type" in validate_contract(payload)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("score", 99, "score_requires_external_evidence"),
        ("confidence", 0.9, "confidence_too_high_without_evidence"),
        ("status", "EXTERNAL_VERIFIED", "evidence_status_must_be_candidate_without_evidence"),
    ],
)
def test_candidate_without_evidence_rejects_self_validation(field: str, value: object, expected: str) -> None:
    payload = _candidate()
    evidence = payload["evidence_status"]
    assert isinstance(evidence, dict)
    evidence[field] = value
    assert expected in validate_contract(payload)


def test_final_verdict_without_evidence_must_remain_candidate() -> None:
    payload = _candidate()
    verdict = payload["final_verdict"]
    assert isinstance(verdict, dict)
    verdict["status"] = "CI_VERIFIED"
    assert "final_status_must_be_candidate_without_evidence" in validate_contract(payload)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("score", "high", "score_must_be_number_or_null"),
        ("tests_executed", "T1", "tests_executed_must_be_list"),
        ("tests_not_executed", "T2", "tests_not_executed_must_be_list"),
    ],
)
def test_evidence_fields_have_machine_types(field: str, value: object, expected: str) -> None:
    payload = _candidate()
    evidence = payload["evidence_status"]
    assert isinstance(evidence, dict)
    evidence[field] = value
    assert expected in validate_contract(payload)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("required", "true", "runner_required_must_be_bool"),
        ("entrypoint", " ", "runner_entrypoint_must_be_nonempty_string"),
        ("commands", "python", "runner_commands_must_be_list"),
        ("timeout_seconds", 0, "runner_timeout_seconds_must_be_positive_int"),
    ],
)
def test_python_runner_contract_has_machine_types(field: str, value: object, expected: str) -> None:
    payload = _candidate()
    runner = payload["python_runner_contract"]
    assert isinstance(runner, dict)
    runner[field] = value

    assert expected in validate_contract(payload)


def test_top_level_collection_fields_have_machine_types() -> None:
    payload = _candidate()
    payload["validation_tests"] = {}

    assert "validation_tests_must_be_list" in validate_contract(payload)


def test_next_action_must_be_nonempty_string() -> None:
    payload = _candidate()
    payload["next_deterministic_action"] = " "

    assert "next_deterministic_action_must_be_nonempty_string" in validate_contract(payload)


def test_output_constraints_are_required_true_values() -> None:
    payload = _candidate()
    constraints = payload["output_constraints"]
    assert isinstance(constraints, dict)
    constraints["json_only"] = False

    assert "constraint_not_true:json_only" in validate_contract(payload)


def test_minimize_tokens_constraint_is_required() -> None:
    payload = _candidate()
    constraints = payload["output_constraints"]
    assert isinstance(constraints, dict)
    constraints.pop("minimize_tokens")

    assert "constraint_not_true:minimize_tokens" in validate_contract(payload)


def test_main_writes_validation_result(tmp_path: Path) -> None:
    src = tmp_path / "contract.json"
    out = tmp_path / "result.json"
    src.write_text(json.dumps(_candidate()), encoding="utf-8")

    assert main([str(src), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "OK"
    assert result["errors"] == []


def test_main_rejects_non_object_json(tmp_path: Path) -> None:
    src = tmp_path / "contract.json"
    src.write_text("[]", encoding="utf-8")

    assert main([str(src)]) == 1
