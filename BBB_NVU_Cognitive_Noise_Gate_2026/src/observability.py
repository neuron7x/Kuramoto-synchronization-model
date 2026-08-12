"""Metrics and incident records for BBB-NVU inference outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    AUTONOMOUS_PROHIBITED_STATES,
    HIGH_REVIEW_STATES,
    VALID_STATES,
    canonical,
    sha256_text,
)

INCIDENT_STATES = {"YELLOW_WATCH", "ORANGE_RISK", "RED_CRITICAL", "BLACK_INVALID"}
SEVERITY_BY_STATE: dict[str, str] = {
    "BLACK_INVALID": "CRITICAL",
    "RED_CRITICAL": "CRITICAL",
    "ORANGE_RISK": "ERROR",
    "YELLOW_WATCH": "WARN",
}
RESPONSE_BY_SEVERITY: dict[str, list[str]] = {
    "WARN": ["collect_more_data", "repeat_low_quality_measurements"],
    "ERROR": [
        "open_human_review",
        "activate_mitigation_protocol",
        "track_until_closed",
    ],
    "CRITICAL": [
        "block_autonomous_execution",
        "open_urgent_human_review",
        "freeze_dependent_automation",
    ],
}


class MetricsSnapshot(BaseModel):
    """Canonical counters derived from inference outputs."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: StrictStr
    created_at: StrictStr
    total_runs: StrictInt = Field(ge=0)
    risk_state_counts: dict[StrictStr, StrictInt]
    degradation_counts: dict[StrictStr, StrictInt]
    action_class_counts: dict[StrictStr, StrictInt]
    human_review_required: StrictInt = Field(ge=0)
    autonomous_execution_prohibited: StrictInt = Field(ge=0)
    low_confidence_runs: StrictInt = Field(ge=0)
    incident_candidates: StrictInt = Field(ge=0)

    def to_json(self) -> str:
        """Serialize snapshot deterministically."""
        return canonical(self.model_dump())


class IncidentRecord(BaseModel):
    """Single deterministic incident record derived from one inference output."""

    model_config = ConfigDict(extra="forbid")

    incident_id: StrictStr
    created_at: StrictStr
    run_id: StrictStr
    run_hash: StrictStr
    severity: Literal["WARN", "ERROR", "CRITICAL"]
    trigger: StrictStr
    risk_state: StrictStr
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    degradations: list[StrictStr]
    action_ids: list[StrictStr]
    requires_human_review: StrictBool
    prohibited_autonomous_execution: StrictBool
    response_steps: list[StrictStr]
    status: Literal["OPEN"] = "OPEN"

    def to_jsonl(self) -> str:
        """Serialize incident as one deterministic JSONL line."""
        return canonical(self.model_dump()) + "\n"


def _actions(output: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(action) for action in output.get("actions", [])]


def _risk_state(output: dict[str, Any]) -> str:
    state = str(output["risk"]["risk_state"])
    if state not in VALID_STATES:
        return "BLACK_INVALID"
    return state


def _requires_human_review(output: dict[str, Any]) -> bool:
    state = _risk_state(output)
    return state in HIGH_REVIEW_STATES or any(
        bool(action.get("requires_human_review")) for action in _actions(output)
    )


def _prohibits_autonomous_execution(output: dict[str, Any]) -> bool:
    state = _risk_state(output)
    return state in AUTONOMOUS_PROHIBITED_STATES or any(
        bool(action.get("prohibited_autonomous_execution")) for action in _actions(output)
    )


def build_metrics_snapshot(
    outputs: list[dict[str, Any]],
    *,
    created_at: str,
) -> MetricsSnapshot:
    """Build deterministic counters from a batch of inference outputs."""
    risk_state_counts = {state: 0 for state in sorted(VALID_STATES)}
    degradation_counts: dict[str, int] = {}
    action_class_counts: dict[str, int] = {}
    human_review_required = 0
    autonomous_execution_prohibited = 0
    low_confidence_runs = 0
    incident_candidates = 0

    for output in outputs:
        state = _risk_state(output)
        risk_state_counts[state] += 1
        confidence = float(output["risk"].get("confidence", 0.0))
        if confidence < 0.70:
            low_confidence_runs += 1
        if state in INCIDENT_STATES:
            incident_candidates += 1
        if _requires_human_review(output):
            human_review_required += 1
        if _prohibits_autonomous_execution(output):
            autonomous_execution_prohibited += 1
        for degradation in output["risk"].get("degradations", []):
            key = str(degradation)
            degradation_counts[key] = degradation_counts.get(key, 0) + 1
        for action in _actions(output):
            key = str(action.get("action_class", "UNKNOWN"))
            action_class_counts[key] = action_class_counts.get(key, 0) + 1

    snapshot_body = {
        "created_at": created_at,
        "total_runs": len(outputs),
        "risk_state_counts": risk_state_counts,
        "degradation_counts": dict(sorted(degradation_counts.items())),
        "action_class_counts": dict(sorted(action_class_counts.items())),
        "human_review_required": human_review_required,
        "autonomous_execution_prohibited": autonomous_execution_prohibited,
        "low_confidence_runs": low_confidence_runs,
        "incident_candidates": incident_candidates,
    }
    snapshot_id = "metrics-" + sha256_text(canonical(snapshot_body))[:12]
    return MetricsSnapshot(
        snapshot_id=snapshot_id,
        created_at=created_at,
        total_runs=len(outputs),
        risk_state_counts=risk_state_counts,
        degradation_counts=dict(sorted(degradation_counts.items())),
        action_class_counts=dict(sorted(action_class_counts.items())),
        human_review_required=human_review_required,
        autonomous_execution_prohibited=autonomous_execution_prohibited,
        low_confidence_runs=low_confidence_runs,
        incident_candidates=incident_candidates,
    )


def incident_from_output(output: dict[str, Any]) -> IncidentRecord | None:
    """Build an incident for non-green outputs; return None for stable green runs."""
    state = _risk_state(output)
    if state not in INCIDENT_STATES:
        return None

    severity = SEVERITY_BY_STATE[state]
    actions = _actions(output)
    trigger = f"risk_state:{state}"
    body = {
        "created_at": output["created_at"],
        "run_id": output["run_id"],
        "run_hash": output["run_hash"],
        "severity": severity,
        "trigger": trigger,
        "risk_state": state,
    }
    return IncidentRecord(
        incident_id="incident-" + sha256_text(canonical(body))[:12],
        created_at=str(output["created_at"]),
        run_id=str(output["run_id"]),
        run_hash=str(output["run_hash"]),
        severity=cast(Literal["WARN", "ERROR", "CRITICAL"], severity),
        trigger=trigger,
        risk_state=state,
        confidence=float(output["risk"].get("confidence", 0.0)),
        degradations=[str(item) for item in output["risk"].get("degradations", [])],
        action_ids=[str(action["action_id"]) for action in actions],
        requires_human_review=_requires_human_review(output),
        prohibited_autonomous_execution=_prohibits_autonomous_execution(output),
        response_steps=RESPONSE_BY_SEVERITY[severity],
    )


def build_incident_register(outputs: list[dict[str, Any]]) -> list[IncidentRecord]:
    """Return deterministic incidents for all non-green outputs."""
    incidents = [incident_from_output(output) for output in outputs]
    return sorted(
        (incident for incident in incidents if incident is not None),
        key=lambda item: item.incident_id,
    )


def write_incidents(path: str | Path, incidents: list[IncidentRecord]) -> None:
    """Append incidents to a JSONL file."""
    with Path(path).open("a", encoding="utf-8") as handle:
        for incident in incidents:
            handle.write(incident.to_jsonl())
