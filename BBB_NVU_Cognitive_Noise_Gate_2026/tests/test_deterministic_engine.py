# ruff: noqa: I001

from pathlib import Path
from typing import Any

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    build_output,
    evaluate,
    load_yaml,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
RULES = load_yaml(ROOT / "config" / "risk_rules.yaml")
DomainIndices = dict[str, float]
InputDoc = dict[str, Any]


def input_doc(
    indices: DomainIndices,
    confidence: float = 0.9,
    critical_data_invalid: bool = False,
    degradations: list[str] | None = None,
) -> InputDoc:
    return {
        "subject_id": "S-test",
        "critical_data_invalid": critical_data_invalid,
        "confidence": confidence,
        "domain_indices": indices,
        "degradations": degradations or [],
    }


@requirement("R003")
def test_golden_risk_vectors() -> None:
    cases: list[tuple[InputDoc, str]] = [
        (
            input_doc(
                {"BSI": 20, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
                0.90,
            ),
            "GREEN_STABLE",
        ),
        (
            input_doc(
                {"BSI": 20, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
                0.62,
            ),
            "YELLOW_WATCH",
        ),
        (
            input_doc(
                {"BSI": 65, "NRI": 15, "VML": 61, "GRS": 70, "CNI": 20},
                0.85,
            ),
            "ORANGE_RISK",
        ),
        (
            input_doc(
                {"BSI": 82, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
                0.90,
            ),
            "RED_CRITICAL",
        ),
        (input_doc({}, 0.0, critical_data_invalid=True), "BLACK_INVALID"),
    ]

    for doc, expected in cases:
        risk, _actions = evaluate(doc, RULES)
        assert risk["risk_state"] == expected


@requirement("R004")
def test_missing_domain_is_explicit_degradation() -> None:
    risk, _actions = evaluate(
        input_doc({"BSI": 20, "NRI": 20, "VML": 20, "CNI": 20}, 0.80),
        RULES,
    )
    assert "missing_domain:GRS" in risk["degradations"]


@requirement("R005")
def test_high_risk_and_invalid_states_require_human_review() -> None:
    cases = [
        input_doc(
            {"BSI": 65, "NRI": 15, "VML": 61, "GRS": 70, "CNI": 20},
            0.85,
        ),
        input_doc(
            {"BSI": 82, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
            0.90,
        ),
        input_doc({}, 0.0, critical_data_invalid=True),
    ]
    for doc in cases:
        _risk, actions = evaluate(doc, RULES)
        assert actions
        assert all(action["requires_human_review"] for action in actions)


@requirement("R003")
def test_run_hash_is_stable_for_same_input_rules_and_engine() -> None:
    doc = input_doc(
        {"BSI": 20, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
        0.90,
    )
    first = build_output(doc, "memory.json", RULES)
    second = build_output(doc, "memory.json", RULES)
    assert first["run_hash"] == second["run_hash"]
    assert first["input_hash"] == second["input_hash"]
    assert first["provenance"]["record_id"] == second["provenance"]["record_id"]
