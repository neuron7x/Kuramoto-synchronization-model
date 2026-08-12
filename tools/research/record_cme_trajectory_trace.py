from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "cme_trajectory_trace.schema.json"
DEFAULT_TRACE_PATH = ROOT / "data" / "cme_trajectory_trace_example.json"

REQUIRED_TOP_LEVEL = {
    "trace_version",
    "trace_id",
    "created_at",
    "status",
    "state_t",
    "operation_t",
    "candidate_t",
    "score_t",
    "decision_t",
    "artifact_delta_t",
    "rollback_condition_t",
    "state_t_plus_1",
    "verifiers",
    "claim_status",
}

REQUIRED_TRACE_FIELDS = {
    "state_t",
    "operation_t",
    "candidate_t",
    "score_t",
    "decision_t",
    "artifact_delta_t",
    "rollback_condition_t",
    "state_t_plus_1",
}

ALLOWED_STATUS = {"S0_REPO_FACT", "S1_TESTED", "S5_PROXY", "S6_SPECULATIVE"}
ALLOWED_DECISIONS = {"ACCEPT", "REJECT", "REROUTE", "HUMAN_REVIEW"}
ALLOWED_VERIFIER_STATUS = {"PASS", "FAIL", "MISSING", "UNKNOWN"}


class TrajectoryTraceError(ValueError):
    """Raised when a CME trajectory trace violates the repository contract."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TrajectoryTraceError(f"missing file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TrajectoryTraceError(f"expected JSON object in {path}")
    return payload


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TrajectoryTraceError(f"{field} must be a non-empty string")


def _require_non_empty_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or not value:
        raise TrajectoryTraceError(f"{field} must be a non-empty list")


def validate_trace(trace: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_TOP_LEVEL - set(trace))
    if missing:
        raise TrajectoryTraceError(f"missing required fields: {missing}")

    extra = sorted(set(trace) - REQUIRED_TOP_LEVEL)
    if extra:
        raise TrajectoryTraceError(f"unexpected fields: {extra}")

    if trace["trace_version"] != "1.0":
        raise TrajectoryTraceError("trace_version must be 1.0")

    _require_non_empty_string(trace["trace_id"], "trace_id")
    _require_non_empty_string(trace["created_at"], "created_at")

    if trace["status"] not in ALLOWED_STATUS:
        raise TrajectoryTraceError(f"invalid trace status: {trace['status']!r}")

    for field in REQUIRED_TRACE_FIELDS:
        if field not in trace:
            raise TrajectoryTraceError(f"missing trajectory field: {field}")

    _validate_state_snapshot(trace["state_t"], "state_t")
    _validate_state_snapshot(trace["state_t_plus_1"], "state_t_plus_1")
    _validate_operation(trace["operation_t"])
    _validate_candidates(trace["candidate_t"])
    _validate_scores(trace["score_t"])
    _validate_decision(trace["decision_t"])
    _validate_artifact_delta(trace["artifact_delta_t"])
    _validate_rollback(trace["rollback_condition_t"])
    _validate_verifiers(trace["verifiers"])
    _validate_claim_status(trace["claim_status"])


def _validate_state_snapshot(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError(f"{field} must be an object")
    for key in ("snapshot_id", "summary"):
        _require_non_empty_string(value.get(key), f"{field}.{key}")
    for key in ("known_constraints", "open_uncertainties"):
        if not isinstance(value.get(key), list):
            raise TrajectoryTraceError(f"{field}.{key} must be a list")


def _validate_operation(value: Any) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError("operation_t must be an object")
    for key in ("operator_name", "operation", "repo_location", "input_state_ref"):
        _require_non_empty_string(value.get(key), f"operation_t.{key}")
    if value.get("status") not in {"S0_REPO_FACT", "S1_TESTED", "S5_PROXY"}:
        raise TrajectoryTraceError("operation_t.status is invalid")


def _validate_candidates(value: Any) -> None:
    _require_non_empty_list(value, "candidate_t")
    for index, candidate in enumerate(value):
        if not isinstance(candidate, dict):
            raise TrajectoryTraceError(f"candidate_t[{index}] must be an object")
        for key in ("candidate_id", "description", "source"):
            _require_non_empty_string(candidate.get(key), f"candidate_t[{index}].{key}")
        if candidate.get("status") not in {"S0_REPO_FACT", "S5_PROXY", "S6_SPECULATIVE"}:
            raise TrajectoryTraceError(f"candidate_t[{index}].status is invalid")


def _validate_scores(value: Any) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError("score_t must be an object")
    score_keys = [
        "intent_coherence_score",
        "constraint_satisfaction_score",
        "operator_coverage_score",
        "verification_readiness_score",
        "claim_safety_score",
    ]
    total = 0
    for key in score_keys:
        score = value.get(key)
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 10:
            raise TrajectoryTraceError(f"score_t.{key} must be an integer from 0 to 10")
        total += score
    if value.get("total") != total:
        raise TrajectoryTraceError("score_t.total must equal the sum of component scores")


def _validate_decision(value: Any) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError("decision_t must be an object")
    if value.get("decision") not in ALLOWED_DECISIONS:
        raise TrajectoryTraceError("decision_t.decision is invalid")
    for key in ("reason", "made_by"):
        _require_non_empty_string(value.get(key), f"decision_t.{key}")
    if value.get("status") not in {"S0_REPO_FACT", "S1_TESTED", "S5_PROXY"}:
        raise TrajectoryTraceError("decision_t.status is invalid")


def _validate_artifact_delta(value: Any) -> None:
    _require_non_empty_list(value, "artifact_delta_t")
    for index, delta in enumerate(value):
        if not isinstance(delta, dict):
            raise TrajectoryTraceError(f"artifact_delta_t[{index}] must be an object")
        for key in ("path", "expected_validator"):
            _require_non_empty_string(delta.get(key), f"artifact_delta_t[{index}].{key}")
        if delta.get("change_type") not in {"CREATE", "MODIFY", "DELETE", "NONE"}:
            raise TrajectoryTraceError(f"artifact_delta_t[{index}].change_type is invalid")
        if delta.get("status") not in {"S0_REPO_FACT", "S1_TESTED", "S5_PROXY"}:
            raise TrajectoryTraceError(f"artifact_delta_t[{index}].status is invalid")


def _validate_rollback(value: Any) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError("rollback_condition_t must be an object")
    for key in ("condition", "trigger", "rollback_action"):
        _require_non_empty_string(value.get(key), f"rollback_condition_t.{key}")
    if value.get("status") not in {"S0_REPO_FACT", "S5_PROXY"}:
        raise TrajectoryTraceError("rollback_condition_t.status is invalid")


def _validate_verifiers(value: Any) -> None:
    _require_non_empty_list(value, "verifiers")
    for index, verifier in enumerate(value):
        if not isinstance(verifier, dict):
            raise TrajectoryTraceError(f"verifiers[{index}] must be an object")
        for key in ("name", "command"):
            _require_non_empty_string(verifier.get(key), f"verifiers[{index}].{key}")
        if verifier.get("current_status") not in ALLOWED_VERIFIER_STATUS:
            raise TrajectoryTraceError(f"verifiers[{index}].current_status is invalid")


def _validate_claim_status(value: Any) -> None:
    if not isinstance(value, dict):
        raise TrajectoryTraceError("claim_status must be an object")
    if not isinstance(value.get("blocked_claims"), list):
        raise TrajectoryTraceError("claim_status.blocked_claims must be a list")
    _require_non_empty_list(value.get("allowed_statuses"), "claim_status.allowed_statuses")
    _require_non_empty_string(value.get("promotion_rule"), "claim_status.promotion_rule")


def main(argv: list[str]) -> int:
    trace_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_TRACE_PATH
    if not trace_path.is_absolute():
        trace_path = ROOT / trace_path

    _load_json(SCHEMA_PATH)
    trace = _load_json(trace_path)
    validate_trace(trace)
    print(f"OK trajectory trace: {trace_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
