from __future__ import annotations

import json

from application.settings import ApiServerSettings, BackendRuntimeSettings
from application.runtime.control_gates import GatePipelineResult
from tests.helpers.control_platform import (
    build_gate_result,
    compute_config_fingerprint,
)

FORBIDDEN_PATTERNS = (
    "token",
    "secret",
    "password",
    "api_key",
    "private",
    "begin rsa",
)


def test_no_secrets_in_telemetry_event() -> None:
    result: GatePipelineResult = build_gate_result()
    fingerprint = compute_config_fingerprint(
        BackendRuntimeSettings(), ApiServerSettings(allow_plaintext=True)
    )
    event = {
        **result.telemetry,
        "meta": result.gate.meta,
        "config_fingerprint": fingerprint,
    }
    payload = json.dumps(event)
    lowered = payload.lower()
    for token in FORBIDDEN_PATTERNS:
        assert token not in lowered
    assert isinstance(event["config_fingerprint"], str)
    assert len(event["config_fingerprint"]) >= 16
