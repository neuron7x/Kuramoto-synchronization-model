from __future__ import annotations

import json

from application.settings import ApiServerSettings, BackendRuntimeSettings
from tests.helpers.control_platform import (
    FORBIDDEN_PATTERNS,
    build_gate_result,
    compute_config_fingerprint,
)

def _make_event() -> dict[str, object]:
    runtime = BackendRuntimeSettings()
    server = ApiServerSettings(allow_plaintext=True)
    result = build_gate_result()
    return {
        **result.telemetry,
        "meta": result.gate.meta,
        "config_fingerprint": compute_config_fingerprint(runtime, server),
    }


def test_telemetry_event_schema_contract() -> None:
    event = _make_event()
    for required in ("signals", "gate_summary", "config_fingerprint"):
        assert required in event
    assert "telemetry" not in event  # flattened structure only

    payload = json.dumps(event)
    lowered = payload.lower()
    for token in FORBIDDEN_PATTERNS:
        assert token not in lowered

    round_tripped = json.loads(payload)
    assert round_tripped["gate_summary"]["decision"] in {"ALLOW", "THROTTLE", "DENY"}


def test_config_fingerprint_stable() -> None:
    runtime = BackendRuntimeSettings()
    server = ApiServerSettings(allow_plaintext=True)
    first = compute_config_fingerprint(runtime, server)
    second = compute_config_fingerprint(runtime, server)
    assert first == second
