from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "cme_trajectory_trace.schema.json"
TRACE_PATH = ROOT / "data" / "cme_trajectory_trace_example.json"
VALIDATOR_PATH = ROOT / "tools" / "research" / "record_cme_trajectory_trace.py"

spec = importlib.util.spec_from_file_location("record_cme_trajectory_trace", VALIDATOR_PATH)
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_cme_trajectory_trace_matches_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))

    assert schema["title"] == "CME Trajectory Trace Contract"
    Draft202012Validator(schema).validate(trace)
    validator.validate_trace(trace)

    required_trace_fields = {
        "state_t",
        "operation_t",
        "candidate_t",
        "score_t",
        "decision_t",
        "artifact_delta_t",
        "rollback_condition_t",
        "state_t_plus_1",
    }
    assert required_trace_fields <= set(trace)
    assert trace["trace_id"].strip()
    assert trace["decision_t"]["decision"] in {"ACCEPT", "REJECT", "REROUTE", "HUMAN_REVIEW"}
    assert trace["artifact_delta_t"]
    assert trace["verifiers"]
    assert trace["claim_status"]["promotion_rule"].strip()


def test_score_total_is_not_decorative() -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    scores = trace["score_t"]
    component_total = (
        scores["intent_coherence_score"]
        + scores["constraint_satisfaction_score"]
        + scores["operator_coverage_score"]
        + scores["verification_readiness_score"]
        + scores["claim_safety_score"]
    )
    assert scores["total"] == component_total


def test_example_remains_proxy_without_execution_evidence() -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    assert trace["status"] == "S5_PROXY"
    assert trace["decision_t"]["status"] == "S5_PROXY"
    assert all(item["current_status"] == "UNKNOWN" for item in trace["verifiers"])
    assert "command output is persisted" in trace["claim_status"]["promotion_rule"]


@pytest.mark.parametrize("field", ["state_t", "verifiers", "rollback_condition_t"])
def test_missing_trace_evidence_is_rejected(field: str) -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    del trace[field]
    with pytest.raises(validator.TrajectoryTraceError, match="missing required fields"):
        validator.validate_trace(trace)


@pytest.mark.parametrize("score", [-1, 11, True])
def test_invalid_component_scores_are_rejected(score: int | bool) -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    trace["score_t"]["claim_safety_score"] = score
    with pytest.raises(validator.TrajectoryTraceError, match="integer from 0 to 10"):
        validator.validate_trace(trace)


def test_inconsistent_score_total_is_rejected() -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    trace["score_t"]["total"] += 1
    with pytest.raises(validator.TrajectoryTraceError, match="sum of component scores"):
        validator.validate_trace(trace)


def test_extra_top_level_field_is_rejected() -> None:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    trace["unverified_promotion"] = True
    with pytest.raises(validator.TrajectoryTraceError, match="unexpected fields"):
        validator.validate_trace(trace)


def test_schema_rejects_extra_nested_field() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    trace["decision_t"]["unverified_promotion"] = True
    with pytest.raises(ValidationError, match="Additional properties are not allowed"):
        Draft202012Validator(schema).validate(trace)
