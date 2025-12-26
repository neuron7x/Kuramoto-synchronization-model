from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, Mapping

FORBIDDEN_PATTERNS = (
    "token",
    "secret",
    "password",
    "api_key",
    "private",
    "begin rsa",
)

from application.runtime.control_gates import (
    Decision,
    GateDecision,
    GatePipelineResult,
    evaluate_control_gates,
)
from application.runtime.init_control_platform import ControlPlatformInitResult
from application.settings import ApiServerSettings, BackendRuntimeSettings


class StubSerotoninController:
    """Deterministic serotonin controller for tests."""

    def __init__(self, hold_threshold: float = 1.25) -> None:
        self.hold_threshold = hold_threshold

    def update(self, observation: Mapping[str, Any]) -> SimpleNamespace:
        stress = float(observation.get("stress", 0.0))
        gate = "ALLOW"
        reasons: list[str] = []
        if stress >= self.hold_threshold:
            gate = "HOLD"
            reasons.append("STRESS_HIGH")
        risk_budget = max(0.0, 1.0 - 0.2 * stress)
        metrics_snapshot = {"cooldown_s": min(1.0, max(0.0, stress * 0.1))}
        return SimpleNamespace(
            action_gate=gate,
            risk_budget=risk_budget,
            reason_codes=reasons,
            metrics_snapshot=metrics_snapshot,
        )


class StubThermoController:
    """Deterministic thermo controller for tests."""

    def __init__(self, baseline: float = 0.2, epsilon: float = 0.1) -> None:
        self.baseline_F = baseline
        self.epsilon_adaptive = epsilon
        self.previous_F = baseline
        self.controller_state = "STABLE"
        self.circuit_breaker_active = False


def compute_config_fingerprint(
    runtime_settings: BackendRuntimeSettings, server_settings: ApiServerSettings
) -> str:
    payload = {
        "runtime": runtime_settings.model_dump(mode="json"),
        "server": server_settings.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_gate_result(
    *,
    signals: Mapping[str, Any] | None = None,
    runtime_settings: BackendRuntimeSettings | None = None,
    serotonin: object | None = None,
    thermo: object | None = None,
) -> GatePipelineResult:
    runtime = runtime_settings or BackendRuntimeSettings()
    controllers = {
        "serotonin": serotonin or StubSerotoninController(),
        "thermo": thermo or StubThermoController(),
    }
    return evaluate_control_gates(runtime, controllers, signals or {})


def build_init_result_stub(
    *,
    runtime_settings: BackendRuntimeSettings | None = None,
    server_settings: ApiServerSettings | None = None,
    controllers: Mapping[str, object] | None = None,
    telemetry_meta: Mapping[str, Any] | None = None,
    gate_result: GatePipelineResult | None = None,
) -> ControlPlatformInitResult:
    runtime = runtime_settings or BackendRuntimeSettings()
    server = server_settings or ApiServerSettings(allow_plaintext=True)
    gate = gate_result or build_gate_result(runtime_settings=runtime)
    controllers_map = dict(controllers or gate.controllers)
    telemetry = dict(
        telemetry_meta
        or {
            "effective_config_source": "defaults",
            "controllers_loaded": sorted(controllers_map.keys()),
        }
    )
    return ControlPlatformInitResult(
        runtime_settings=runtime,
        server_settings=server,
        controllers=controllers_map,
        app=SimpleNamespace(name="stub-app"),
        telemetry_meta=telemetry,
        gate_pipeline=lambda *_args, **_kwargs: gate,
        controllers_required=True,
    )


def stable_decision_snapshot(result: GatePipelineResult) -> dict[str, Any]:
    gate = result.gate
    return {
        "decision": gate.decision.value,
        "position_multiplier": gate.position_multiplier,
        "throttle_ms": gate.throttle_ms,
        "reasons": list(gate.reasons),
        "meta": dict(gate.meta),
        "telemetry": result.telemetry,
    }
