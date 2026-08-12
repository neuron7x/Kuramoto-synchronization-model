# ruff: noqa: I001

from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    canonical,
    load_yaml,
    sha256_text,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.operational_kernel import (
    OperationalKernel,
    RequestMapping,
    verify_operational_envelope,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
RULES = load_yaml(ROOT / "config" / "risk_rules.yaml")
FIXED_TIME = "2026-06-03T00:00:00Z"
FIXED_ENGINE_HASH = "engine-hash-for-operational-kernel-tests"

STABLE_INPUT: dict[str, Any] = {
    "subject_id": "S-STABLE",
    "critical_data_invalid": False,
    "confidence": 0.95,
    "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
    "degradations": [],
}
RED_INPUT: dict[str, Any] = {
    "subject_id": "S-RED",
    "critical_data_invalid": False,
    "confidence": 0.90,
    "domain_indices": {"BSI": 82, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
    "degradations": [],
}
INVALID_INPUT: dict[str, Any] = {
    "subject_id": "S-INVALID",
    "critical_data_invalid": True,
    "confidence": 1.0,
    "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
    "degradations": [],
}


def request(input_doc: dict[str, Any], source_id: str, **extra: Any) -> RequestMapping:
    return {"input_doc": input_doc, "source_id": source_id, **extra}


def kernel() -> OperationalKernel:
    return OperationalKernel(RULES, engine_hash=FIXED_ENGINE_HASH)


def as_payload(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value)


@requirement("R003")
def test_operational_envelope_is_deterministic_and_replay_verified():
    requests: list[RequestMapping] = [
        request(STABLE_INPUT, "stable.json"),
        request(RED_INPUT, "red.json"),
    ]

    first = kernel().execute(requests, created_at=FIXED_TIME)
    second = kernel().execute(requests, created_at=FIXED_TIME)

    assert first.envelope_hash == second.envelope_hash
    assert first.to_json() == second.to_json()
    assert first.manifest["replay_verified"] == [True, True]
    assert first.manifest["request_count"] == 2


@requirement("R004")
def test_operational_envelope_contains_metrics_audit_and_incidents():
    requests: list[RequestMapping] = [
        request(STABLE_INPUT, "stable.json"),
        request(RED_INPUT, "red.json"),
    ]
    envelope = kernel().execute(requests, created_at=FIXED_TIME)

    assert envelope.request_count == 2
    assert len(envelope.outputs) == 2
    assert len(envelope.audit_events) == 2
    assert len(envelope.replay_bundles) == 2
    assert envelope.metrics_snapshot["risk_state_counts"]["GREEN_STABLE"] == 1
    assert envelope.metrics_snapshot["risk_state_counts"]["RED_CRITICAL"] == 1
    assert envelope.metrics_snapshot["incident_candidates"] == 1
    assert envelope.incidents[0]["severity"] == "CRITICAL"
    assert envelope.incidents[0]["prohibited_autonomous_execution"] is True


@requirement("R002")
def test_operational_kernel_preserves_fail_closed_invalid_behavior():
    requests: list[RequestMapping] = [request(INVALID_INPUT, "invalid.json")]
    envelope = kernel().execute(requests, created_at=FIXED_TIME)

    assert envelope.outputs[0]["risk"]["risk_state"] == "BLACK_INVALID"
    assert envelope.outputs[0]["risk"]["confidence"] == 0.0
    assert envelope.incidents[0]["severity"] == "CRITICAL"
    assert envelope.incidents[0]["prohibited_autonomous_execution"] is True
    assert envelope.manifest["replay_verified"] == [True]


@requirement("R002")
def test_operational_kernel_rejects_boundary_request_extra_fields():
    try:
        requests: list[RequestMapping] = [request(STABLE_INPUT, "stable.json", extra="value")]
        kernel().execute(requests, created_at=FIXED_TIME)
    except ValidationError as error:
        assert error.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("operational request accepted an extra field")


@requirement("R003")
def test_operational_envelope_verifier_accepts_fresh_envelope():
    requests: list[RequestMapping] = [
        request(STABLE_INPUT, "stable.json"),
        request(RED_INPUT, "red.json"),
    ]
    envelope = kernel().execute(requests, created_at=FIXED_TIME)

    assert verify_operational_envelope(envelope)


@requirement("R003")
def test_operational_envelope_verifier_rejects_hash_mismatch():
    requests: list[RequestMapping] = [request(STABLE_INPUT, "stable.json")]
    envelope = kernel().execute(requests, created_at=FIXED_TIME)
    payload = as_payload(envelope.model_dump())
    outputs = cast(list[dict[str, Any]], payload["outputs"])
    risk = cast(dict[str, Any], outputs[0]["risk"])
    risk["confidence"] = 0.10

    assert not verify_operational_envelope(payload)


@requirement("R003")
def test_operational_envelope_verifier_rejects_manifest_mismatch():
    requests: list[RequestMapping] = [request(STABLE_INPUT, "stable.json")]
    envelope = kernel().execute(requests, created_at=FIXED_TIME)
    payload = as_payload(envelope.model_dump())
    manifest = cast(dict[str, Any], payload["manifest"])
    manifest["replay_verified"] = [False]
    body = dict(payload)
    body.pop("envelope_hash")
    payload["envelope_hash"] = sha256_text(canonical(body))

    assert not verify_operational_envelope(payload)


@requirement("R002")
def test_operational_envelope_verifier_fails_closed_on_bad_payload():
    assert not verify_operational_envelope({"envelope_hash": "bad", "outputs": None})
