from __future__ import annotations

import json
from pathlib import Path

from tools.check_json_contract_evidence_policy import check_policy, main


def _candidate() -> dict[str, object]:
    return {
        "contract_type": "repository_repair_contract",
        "inputs": {"missing": []},
        "evidence_status": {
            "external_evidence_available": False,
            "evidence_source": "unavailable",
            "tests_executed": [],
            "score": None,
            "status": "CANDIDATE_NOT_VALIDATED",
        },
        "final_verdict": {"status": "CANDIDATE_NOT_VALIDATED"},
    }


def _blocked() -> dict[str, object]:
    return {
        "contract_type": "blocked_contract",
        "inputs": {"missing": ["external_runner_output"]},
        "evidence_status": {
            "external_evidence_available": False,
            "evidence_source": "unavailable",
            "tests_executed": [],
            "score": None,
            "status": "BLOCKED",
        },
        "final_verdict": {"status": "BLOCKED"},
    }


def _verified() -> dict[str, object]:
    return {
        "contract_type": "external_validation_contract",
        "inputs": {"missing": []},
        "evidence_status": {
            "external_evidence_available": True,
            "evidence_source": "ci_log",
            "tests_executed": ["ci"],
            "score": None,
            "status": "CI_VERIFIED",
        },
        "final_verdict": {"status": "CI_VERIFIED"},
    }


def test_candidate_policy_is_ok() -> None:
    assert check_policy(_candidate()) == []


def test_blocked_policy_is_ok_when_missing_inputs_are_explicit() -> None:
    assert check_policy(_blocked()) == []


def test_verified_policy_is_ok_with_matching_source_and_tests() -> None:
    assert check_policy(_verified()) == []


def test_status_alignment_is_required() -> None:
    payload = _candidate()
    verdict = payload["final_verdict"]
    assert isinstance(verdict, dict)
    verdict["status"] = "BLOCKED"

    assert "status_mismatch" in check_policy(payload)


def test_blocked_contract_requires_missing_inputs() -> None:
    payload = _blocked()
    inputs = payload["inputs"]
    assert isinstance(inputs, dict)
    inputs["missing"] = []

    assert "blocked_contract_missing_inputs_required" in check_policy(payload)


def test_verified_status_requires_matching_source() -> None:
    payload = _verified()
    evidence = payload["evidence_status"]
    assert isinstance(evidence, dict)
    evidence["evidence_source"] = "tool_log"

    assert "validated_status_source_mismatch" in check_policy(payload)


def test_cli_writes_result(tmp_path: Path) -> None:
    src = tmp_path / "contract.json"
    out = tmp_path / "result.json"
    src.write_text(json.dumps(_candidate()), encoding="utf-8")

    assert main([str(src), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "OK"
