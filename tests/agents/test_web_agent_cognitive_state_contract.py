from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COGNITIVE_DOC = ROOT / "docs" / "agents" / "web_agent_cognitive_state_assessment.md"
COGNITIVE_SCHEMA = ROOT / "schemas" / "web_agent_cognitive_state.schema.json"


def test_cognitive_state_assessment_declares_required_dimensions() -> None:
    text = COGNITIVE_DOC.read_text(encoding="utf-8")

    required_terms = [
        "Perception",
        "Attention",
        "Memory",
        "Reasoning",
        "Decision",
        "Interpretation errors",
        "CognitiveState = Perception × Attention × Memory × Reasoning × Decision × InterpretationError",
        "COGNITIVE_STATE_MODEL_DEFINED_NOT_BASELINED",
        "PRODUCTION_READY: NO",
    ]

    missing = [term for term in required_terms if term not in text]
    assert not missing, f"Missing cognitive assessment contract terms: {missing}"


def test_cognitive_state_schema_is_machine_readable() -> None:
    schema = json.loads(COGNITIVE_SCHEMA.read_text(encoding="utf-8"))

    assert schema["title"] == "Web Agent Cognitive State"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    required = set(schema["required"])
    expected = {
        "perception_coverage",
        "attention_precision",
        "memory_minimization",
        "reasoning_traceability",
        "decision_safety",
        "interpretation_error_rate",
        "critical_interpretation_errors",
        "baseline_commit",
        "measurement_method",
    }

    assert expected.issubset(required)

    properties = schema["properties"]
    bounded_metrics = [
        "perception_coverage",
        "attention_precision",
        "memory_minimization",
        "reasoning_traceability",
        "decision_safety",
        "interpretation_error_rate",
    ]
    for metric in bounded_metrics:
        assert properties[metric]["minimum"] == 0.0
        assert properties[metric]["maximum"] == 1.0

    assert properties["critical_interpretation_errors"]["type"] == "integer"
    assert properties["critical_interpretation_errors"]["minimum"] == 0
