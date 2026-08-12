"""Audit and replay utilities for BBB-NVU deterministic inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictStr

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    audit_hash,
    canonical,
    sha256_text,
)


class AuditEvent(BaseModel):
    """Single JSONL-safe audit event derived from one inference run."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["inference_run"] = "inference_run"
    created_at: StrictStr
    run_id: StrictStr
    run_hash: StrictStr
    input_hash: StrictStr
    rules_hash: StrictStr
    engine_hash: StrictStr
    risk_state: StrictStr
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    degradations: list[StrictStr]
    action_ids: list[StrictStr]
    requires_human_review: StrictBool
    prohibited_autonomous_execution: StrictBool

    @classmethod
    def from_output(cls, output: dict[str, Any]) -> "AuditEvent":
        """Build an audit event from a canonical inference output."""
        actions = output.get("actions", [])
        return cls(
            created_at=output["created_at"],
            run_id=output["run_id"],
            run_hash=output["run_hash"],
            input_hash=output["input_hash"],
            rules_hash=output["rules_hash"],
            engine_hash=output["engine_hash"],
            risk_state=output["risk"]["risk_state"],
            confidence=float(output["risk"]["confidence"]),
            degradations=[str(item) for item in output["risk"].get("degradations", [])],
            action_ids=[str(action["action_id"]) for action in actions],
            requires_human_review=any(
                bool(action.get("requires_human_review")) for action in actions
            ),
            prohibited_autonomous_execution=any(
                bool(action.get("prohibited_autonomous_execution")) for action in actions
            ),
        )

    def to_jsonl(self) -> str:
        """Serialize event as one deterministic JSONL line."""
        return canonical(self.model_dump()) + "\n"


def write_audit_event(path: str | Path, event: AuditEvent) -> None:
    """Append one audit event to a JSONL file."""
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(event.to_jsonl())


def build_replay_bundle(
    output: dict[str, Any],
    input_doc: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic replay bundle for one inference run."""
    bundle = {
        "bundle_version": "BBB-NVU-CNG-replay.1",
        "created_at": output["created_at"],
        "source_id": output["provenance"]["source_id"],
        "input_doc": input_doc,
        "rules": rules,
        "expected": {
            "run_hash": output["run_hash"],
            "input_hash": output["input_hash"],
            "rules_hash": output["rules_hash"],
            "engine_hash": output["engine_hash"],
            "risk_state": output["risk"]["risk_state"],
        },
    }
    bundle["bundle_hash"] = sha256_text(canonical(bundle))
    return bundle


def replay_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Replay a bundle and return a fresh inference output."""
    engine = DeterministicInferenceEngine.from_rules(
        dict(bundle["rules"]),
        engine_hash=str(bundle["expected"]["engine_hash"]),
    )
    return engine.build_output(
        dict(bundle["input_doc"]),
        source_id=str(bundle["source_id"]),
        created_at=str(bundle["created_at"]),
    )


def verify_replay_bundle(bundle: dict[str, Any]) -> bool:
    """Return true only when replay reproduces the expected hashes and risk state."""
    expected = bundle["expected"]
    replayed = replay_bundle(bundle)
    return (
        replayed["run_hash"] == expected["run_hash"]
        and replayed["input_hash"] == expected["input_hash"]
        and replayed["rules_hash"] == expected["rules_hash"]
        and replayed["engine_hash"] == expected["engine_hash"]
        and replayed["risk"]["risk_state"] == expected["risk_state"]
        and audit_hash(bundle["input_doc"]) == expected["input_hash"]
    )
