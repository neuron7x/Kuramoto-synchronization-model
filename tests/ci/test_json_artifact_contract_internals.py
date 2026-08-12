from __future__ import annotations

from tools.validate_json_artifact_contract import validate_contract


def _base() -> dict[str, object]:
    return {
        "contract_type": "repository_repair_contract",
        "objective": {
            "target_state": "ready",
            "current_state": "candidate",
            "transformation": "validate",
            "action_vector": "earn -> exit -> build systems",
            "optimization": {"minimize": [], "maximize": []},
        },
        "inputs": {"required": [], "provided": [], "missing": [], "assumptions": []},
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
        "next_deterministic_action": "run validator",
        "final_verdict": {
            "status": "CANDIDATE_NOT_VALIDATED",
            "reason": "runner evidence absent",
            "evidence_required": [],
        },
    }


def test_objective_and_inputs_have_machine_shape() -> None:
    payload = _base()
    objective = payload["objective"]
    inputs = payload["inputs"]
    assert isinstance(objective, dict)
    assert isinstance(inputs, dict)
    objective["target_state"] = " "
    objective["optimization"] = {"minimize": [], "maximize": "bad"}
    inputs["missing"] = "runner"

    errors = validate_contract(payload)
    assert "objective_target_state_must_be_nonempty_string" in errors
    assert "objective_optimization_maximize_must_be_list" in errors
    assert "inputs_missing_must_be_list" in errors


def test_execution_plan_item_shape_is_checked() -> None:
    payload = _base()
    payload["execution_plan"] = [
        {
            "step_id": "P1",
            "action": " ",
            "input": "contract.json",
            "output": "result.json",
            "tool_required": "python",
            "failure_condition": "parse error",
        }
    ]

    assert "execution_plan_0_action_must_be_nonempty_string" in validate_contract(payload)


def test_validation_test_item_shape_is_checked() -> None:
    payload = _base()
    payload["validation_tests"] = [
        {
            "test_id": "T1",
            "test_type": "unknown",
            "input": "contract.json",
            "expected_output": "ok",
            "runner": "unknown",
            "pass_criteria": "ok",
            "fail_criteria": "error",
        }
    ]

    errors = validate_contract(payload)
    assert "validation_tests_0_invalid_test_type" in errors
    assert "validation_tests_0_invalid_runner" in errors


def test_failure_register_item_shape_is_checked() -> None:
    payload = _base()
    payload["failure_register"] = [
        {
            "failure": "missing runner",
            "cause": "not supplied",
            "impact": "candidate only",
            "detection": "field check",
            "mitigation": "provide runner output",
            "severity": "SEVERE",
        }
    ]

    assert "failure_register_0_invalid_severity" in validate_contract(payload)


def test_final_reason_is_required() -> None:
    payload = _base()
    verdict = payload["final_verdict"]
    assert isinstance(verdict, dict)
    verdict["reason"] = " "

    assert "final_reason_must_be_nonempty_string" in validate_contract(payload)
