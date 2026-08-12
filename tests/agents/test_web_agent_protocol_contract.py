from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "agents" / "WEB_AGENT_ARCHITECTURE_PROTOCOL.md"
MATRIX = ROOT / "docs" / "agents" / "web_agent_operationalization_matrix.md"
SCHEMA = ROOT / "schemas" / "web_agent_score.schema.json"


def test_web_agent_protocol_declares_core_contracts() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")

    required_terms = [
        "effect × reversibility × uncertainty",
        "Minimal footprint rule",
        "Context as a Resource",
        "Agent System Hierarchy",
        "Tool Design Specification",
        "Security and Trust Zones",
        "Acceptance Gate",
        "Failure Conditions",
    ]

    missing = [term for term in required_terms if term not in text]
    assert not missing, f"Missing protocol contract terms: {missing}"


def test_operationalization_matrix_has_roles_metrics_and_checkpoints() -> None:
    text = MATRIX.read_text(encoding="utf-8")

    required_terms = [
        "Roles",
        "Resources",
        "Metrics",
        "Checkpoints",
        "CP0 Protocol Canonicalization",
        "CP7 Release Verdict",
        "OVERALL: NOT_PRODUCTION_READY",
    ]

    missing = [term for term in required_terms if term not in text]
    assert not missing, f"Missing operationalization terms: {missing}"


def test_web_agent_score_schema_is_machine_readable() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["title"] == "Web Agent Score"
    assert schema["type"] == "object"

    required = set(schema["required"])
    expected = {
        "task_completion_rate",
        "irreversible_actions_without_confirmation",
        "context_efficiency",
        "hallucination_rate",
        "escalation_precision",
        "injection_resistance",
    }

    assert expected.issubset(required)

    properties = schema["properties"]
    assert properties["task_completion_rate"]["minimum"] == 0.0
    assert properties["task_completion_rate"]["maximum"] == 1.0
    assert properties["irreversible_actions_without_confirmation"]["minimum"] == 0
    assert properties["injection_resistance"]["type"] == "boolean"
