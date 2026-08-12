from __future__ import annotations

import json
import importlib.util
from pathlib import Path

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
