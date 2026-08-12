import json
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    validate_inference_input,
    validate_observation,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
ENGINE = DeterministicInferenceEngine(ROOT / "config" / "risk_rules.yaml")
FIXED_TIME = "2026-06-03T00:00:00Z"


def sample_observation() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "examples" / "sample_observation.json").read_text(encoding="utf-8")
        ),
    )


def sample_inference_input() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "examples" / "sample_run_input.json").read_text(encoding="utf-8")
        ),
    )


@requirement("R001")
def test_l1_observation_gate_accepts_numeric_metric_with_iso_datetimes() -> None:
    observation = validate_observation(sample_observation())
    assert observation.value == 0.42
    assert observation.timestamp.tzinfo is not None
    assert observation.provenance.created_at.tzinfo is not None


@requirement("R001")
def test_l1_observation_gate_rejects_polymorphic_value_and_extra_fields() -> None:
    observation = sample_observation()
    observation["value"] = "0.42"
    try:
        validate_observation(observation)
    except ValidationError as error:
        assert error.errors()[0]["type"] == "float_type"
    else:
        raise AssertionError("string metric value was accepted by the L1 observation gate")

    observation = sample_observation()
    observation["unexpected"] = "not_allowed"
    try:
        validate_observation(observation)
    except ValidationError as error:
        assert error.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("extra observation field was accepted by the L1 observation gate")


@requirement("R002")
def test_l1_inference_gate_rejects_coercion_and_engine_fails_closed() -> None:
    input_doc = sample_inference_input()
    input_doc["confidence"] = "0.74"

    try:
        validate_inference_input(input_doc)
    except ValidationError as error:
        assert error.errors()[0]["type"] == "float_type"
    else:
        raise AssertionError("string confidence was accepted by the L1 inference gate")

    risk, actions = ENGINE.evaluate_run(input_doc, FIXED_TIME)
    assert risk["risk_state"] == "BLACK_INVALID"
    assert risk["confidence"] == 0.0
    assert "SCHEMA_INVALID" in risk["degradations"]
    assert all(action["prohibited_autonomous_execution"] for action in actions)


@requirement("R002")
def test_l1_inference_gate_rejects_unknown_domain_and_extra_fields() -> None:
    input_doc = sample_inference_input()
    domain_indices = cast(dict[str, Any], input_doc["domain_indices"])
    domain_indices["UNKNOWN"] = 10
    risk, _actions = ENGINE.evaluate_run(input_doc, FIXED_TIME)
    assert risk["risk_state"] == "BLACK_INVALID"
    assert any(
        "domain_indices.UNKNOWN" in explanation for explanation in risk["explanations"]
    )

    input_doc = sample_inference_input()
    input_doc["extra"] = "not_allowed"
    risk, _actions = ENGINE.evaluate_run(input_doc, FIXED_TIME)
    assert risk["risk_state"] == "BLACK_INVALID"
    assert any("extra" in explanation for explanation in risk["explanations"])
