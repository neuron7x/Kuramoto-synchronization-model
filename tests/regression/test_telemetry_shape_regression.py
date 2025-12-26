from __future__ import annotations

from typing import Any, Mapping

from application.settings import ApiServerSettings, BackendRuntimeSettings
from tests.helpers.control_platform import build_gate_result, compute_config_fingerprint

BASELINE_SHAPE: Mapping[str, Any] = {
    "signals": {
        "risk_score": "float",
        "volatility": "float",
        "drawdown": "float",
        "free_energy": "float",
    },
    "serotonin": {
        "action_gate": "str",
        "reason_codes": "list",
        "metrics": "dict",
    },
    "thermo": {
        "baseline_F": "float",
        "epsilon": "float",
        "circuit_breaker_active": "bool",
        "controller_state": "str",
        "free_energy": "float",
    },
    "gate_summary": {"proxy_flags": "list", "decision": "str"},
    "config_fingerprint": "str",
}


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "none"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return value.__class__.__name__


def _shape(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "signals": {key: _type_name(value) for key, value in event.get("signals", {}).items()},
        "serotonin": {key: _type_name(value) for key, value in event.get("serotonin", {}).items()},
        "thermo": {key: _type_name(value) for key, value in event.get("thermo", {}).items()},
        "gate_summary": {key: _type_name(value) for key, value in event.get("gate_summary", {}).items()},
        "config_fingerprint": _type_name(event.get("config_fingerprint")),
    }


def test_telemetry_shape_regression_guard() -> None:
    runtime = BackendRuntimeSettings()
    server = ApiServerSettings(allow_plaintext=True)
    result = build_gate_result(
        signals={
            "risk_score": 1.0,
            "volatility": 1.0,
            "drawdown": -0.01,
            "free_energy": 0.2,
        }
    )
    event = {
        **result.telemetry,
        "config_fingerprint": compute_config_fingerprint(runtime, server),
    }

    assert _shape(event) == BASELINE_SHAPE
