from __future__ import annotations

import json
from pathlib import Path

from tools.json_contract_receipt import build


def _base_contract() -> dict[str, object]:
    return {
        "contract_type": "system_prompt_contract",
        "objective": {
            "target_state": "candidate",
            "current_state": "draft",
            "transformation": "validate",
            "action_vector": "earn -> exit -> build systems",
            "optimization": {"minimize": [], "maximize": []},
        },
        "inputs": {"required": [], "provided": [], "missing": [], "assumptions": []},
        "definitions": [],
        "execution_plan": [
            {
                "step_id": "s1",
                "action": "parse",
                "input": "contract",
                "output": "result",
                "tool_required": "python",
                "failure_condition": "parse error",
            }
        ],
        "python_runner_contract": {
            "required": True,
            "entrypoint": "runner.py",
            "commands": [],
            "expected_artifacts": [],
            "timeout_seconds": 300,
            "success_criteria": [],
            "failure_criteria": [],
        },
        "validation_tests": [
            {
                "test_id": "t1",
                "test_type": "parser",
                "input": "contract",
                "expected_output": "result",
                "runner": "python",
                "pass_criteria": "ok",
                "fail_criteria": "error",
            }
        ],
        "failure_register": [
            {
                "failure": "bad input",
                "cause": "missing field",
                "impact": "no run",
                "detection": "validator",
                "mitigation": "fix field",
                "severity": "LOW",
            }
        ],
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
        "next_deterministic_action": "run parser",
        "final_verdict": {
            "status": "CANDIDATE_NOT_VALIDATED",
            "reason": "no runner output",
            "evidence_required": [],
        },
    }


def test_receipt_records_hash_and_counts(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(_base_contract()), encoding="utf-8")

    result = build([contract])

    assert result["status"] == "OK"
    assert result["item_count"] == 1
    assert result["ok_count"] == 1
    item = result["items"][0]
    assert item["bytes"] > 0
    assert len(item["sha256"]) == 64


def test_receipt_rejects_repeated_path(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(_base_contract()), encoding="utf-8")

    result = build([contract, contract])

    assert result["status"] == "ERROR"
    assert result["error_count"] == 1
    assert "repeated_path" in result["items"][1]["errors"]
