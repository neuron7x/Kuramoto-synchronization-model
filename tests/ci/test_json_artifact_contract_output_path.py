from __future__ import annotations

import json
from pathlib import Path

from tools.validate_json_artifact_contract import main


def _candidate() -> dict[str, object]:
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
            "entrypoint": "tools/validate_json_artifact_contract.py",
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


def test_main_creates_result_parent_directory(tmp_path: Path) -> None:
    src = tmp_path / "contract.json"
    out = tmp_path / "nested" / "validation" / "result.json"
    src.write_text(json.dumps(_candidate()), encoding="utf-8")

    assert main([str(src), "--out", str(out)]) == 0

    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "OK"
    assert result["errors"] == []
