# SPDX-License-Identifier: MIT
"""Forward-contract tests for the MFN seven-role evidence-cycle schema.

The schema is a *forward* contract: it constrains the evidence-cycle
artifact a future networked MFN run will emit. No instance is committed
(run dumps are transient and environment-specific), so these tests prove
the schema is a valid metaschema and that it structurally fails closed —
no instance can promote a claim tier or self-score above the bound.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "mfn_multi_agent_cycle.schema.json"


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_mfn_multi_agent_cycle_schema_is_a_valid_metaschema() -> None:
    Draft202012Validator.check_schema(_schema())


def test_mfn_multi_agent_cycle_schema_fails_closed_on_promotion() -> None:
    schema = _schema()
    evidence = schema["properties"]["evidence_status"]["properties"]
    final_gate = schema["properties"]["final_gate"]["properties"]

    # A conforming instance can never self-score and is capped below 1.0.
    assert evidence["score"] == {"type": "null"}
    assert evidence["status"]["const"] == "BLOCKED"
    assert evidence["confidence"]["maximum"] <= 0.9
    # The terminal gate is pinned BLOCKED — no instance can report success.
    assert final_gate["status"]["const"] == "BLOCKED"
    assert schema["properties"]["objective"]["properties"]["action_vector"]["const"] == (
        "earn -> exit -> build systems"
    )


def test_mfn_multi_agent_cycle_schema_rejects_a_promoted_instance() -> None:
    validator = Draft202012Validator(_schema())
    roles = (
        "orchestrator",
        "web_evidence_agent",
        "local_code_builder",
        "integrator",
        "verifier",
        "falsifier",
        "validator_calibrator",
    )
    promoted = {
        "cycle_id": "x",
        "objective": {
            "target_state": "t",
            "current_state": "c",
            "transformation": "x",
            "action_vector": "earn -> exit -> build systems",
        },
        "agent_outputs": {role: {"role": role, "status": "BLOCKED"} for role in roles},
        "artifact_delta": ["a"],
        "evidence_status": {
            "external_evidence_available": True,
            "evidence_source": "python_runner",
            "tests_executed": [],
            "tests_not_executed": [],
            "score": 0.99,  # forbidden: self-score
            "confidence": 0.95,  # forbidden: above 0.9 cap
            "status": "PASS",  # forbidden: only BLOCKED admissible
        },
        "reverse_trace": [
            {
                "failure": "f",
                "cause": "c",
                "component": "x",
                "patch": "p",
                "test": "t",
                "evidence": "e",
            }
        ],
        "next_deterministic_action": "a",
        "final_gate": {"status": "PASS", "reason": "r", "evidence_required": ["x"]},
    }
    assert not validator.is_valid(promoted)
