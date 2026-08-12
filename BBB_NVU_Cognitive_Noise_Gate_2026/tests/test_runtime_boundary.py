# ruff: noqa: I001

import json
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    load_yaml,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.runtime_boundary import RuntimeBoundary, RuntimeRequest
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
RULES = load_yaml(ROOT / "config" / "risk_rules.yaml")
SAMPLE_INPUT = cast(
    dict[str, Any],
    json.loads(
        (ROOT / "examples" / "sample_run_input.json").read_text(encoding="utf-8")
    ),
)
FIXED_TIME = "2026-06-03T00:00:00Z"
FIXED_ENGINE_HASH = "engine-hash-for-runtime-boundary-tests"


@requirement("R003")
def test_runtime_boundary_uses_explicit_timestamp_and_profiles() -> None:
    boundary = RuntimeBoundary(RULES, engine_hash=FIXED_ENGINE_HASH)

    full = cast(
        dict[str, Any],
        boundary.evaluate_run(
            SAMPLE_INPUT,
            source_id="sample.json",
            created_at=FIXED_TIME,
            profile="full",
        ),
    )
    risk = cast(
        dict[str, Any],
        boundary.evaluate_run(
            SAMPLE_INPUT,
            source_id="sample.json",
            created_at=FIXED_TIME,
            profile="risk",
        ),
    )
    actions = cast(
        list[dict[str, Any]],
        boundary.evaluate_run(
            SAMPLE_INPUT,
            source_id="sample.json",
            created_at=FIXED_TIME,
            profile="actions",
        ),
    )

    assert full["created_at"] == FIXED_TIME
    assert full["risk"] == risk
    assert full["actions"] == actions
    assert risk["risk_state"] == "YELLOW_WATCH"


@requirement("R003")
def test_runtime_boundary_batch_is_deterministic() -> None:
    boundary = RuntimeBoundary(RULES, engine_hash=FIXED_ENGINE_HASH)
    dict_request: dict[str, Any] = {"input_doc": SAMPLE_INPUT, "source_id": "a.json"}
    requests: list[RuntimeRequest | dict[str, Any]] = [
        dict_request,
        RuntimeRequest(input_doc=SAMPLE_INPUT, source_id="b.json"),
    ]

    first = cast(
        list[dict[str, Any]],
        boundary.evaluate_batch(requests, created_at=FIXED_TIME),
    )
    second = cast(
        list[dict[str, Any]],
        boundary.evaluate_batch(requests, created_at=FIXED_TIME),
    )

    assert first == second
    assert [item["provenance"]["source_id"] for item in first] == ["a.json", "b.json"]


@requirement("R002")
def test_runtime_boundary_request_rejects_extra_fields() -> None:
    try:
        RuntimeRequest.model_validate(
            {"input_doc": SAMPLE_INPUT, "source_id": "x.json", "extra": "value"}
        )
    except ValidationError as error:
        assert error.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("runtime request accepted an extra field")


@requirement("R003")
def test_engine_can_be_built_from_loaded_rules_without_rule_file_io() -> None:
    engine = DeterministicInferenceEngine.from_rules(RULES, engine_hash=FIXED_ENGINE_HASH)
    output = engine.build_output(SAMPLE_INPUT, source_id="memory.json", created_at=FIXED_TIME)
    assert output["created_at"] == FIXED_TIME
    assert output["risk"]["risk_state"] == "YELLOW_WATCH"
