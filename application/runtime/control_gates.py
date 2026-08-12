# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical control-gate pipeline combining serotonin and thermo controllers."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from application.runtime.decision_telemetry import (
    DecisionTelemetryEvent,
    build_decision_event,
    emit_decision_event,
)

LOGGER = logging.getLogger("geosync.control_gates")

DEFAULT_DRAWDOWN = -0.01
THERMO_EPSILON_FLOOR = 0.05


class Decision(Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    DENY = "DENY"


@dataclass(slots=True)
class GateDecision:
    decision: Decision
    position_multiplier: float = 1.0
    throttle_ms: int = 0
    reasons: list[str] = field(default_factory=list)
    meta: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.position_multiplier) or self.position_multiplier < 0:
            raise ValueError("position_multiplier must be finite and non-negative")
        if self.decision is Decision.DENY:
            self.position_multiplier = 0.0
        if self.decision in (Decision.THROTTLE, Decision.DENY) and not self.reasons:
            raise ValueError("reasons must be provided for THROTTLE or DENY decisions")
        if self.decision is Decision.ALLOW and self.position_multiplier == 0.0:
            self.decision = Decision.DENY
            if not self.reasons:
                self.reasons.append("POSITION_MULTIPLIER_ZERO")


@dataclass(slots=True)
class GatePipelineResult:
    gate: GateDecision
    controllers: dict[str, object]
    telemetry: dict[str, object]
    decision_event: DecisionTelemetryEvent | None = None


def _severity(decision: Decision) -> int:
    return {Decision.ALLOW: 0, Decision.THROTTLE: 1, Decision.DENY: 2}[decision]


def _clamp_multiplier(value: float, defaults: Mapping[str, object]) -> float:
    min_mul = float(defaults.get("min_position_multiplier", 0.0) or 0.0)
    max_mul = float(defaults.get("max_position_multiplier", 1.0) or 1.0)
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return min_mul
    if not math.isfinite(as_float):
        return min_mul
    return max(min_mul, min(max_mul, as_float))


def evaluate_control_gates(
    effective_config: Any, controllers: Mapping[str, object], signals: Mapping[str, object] | None
) -> GatePipelineResult:
    """Evaluate serotonin + thermo controllers and return a unified decision."""

    signals = dict(signals or {})
    gate_defaults = dict(
        getattr(
            effective_config,
            "gate_defaults",
            {
                "min_position_multiplier": 0.0,
                "max_position_multiplier": 1.0,
                "default_decision": "ALLOW",
            },
        )
        or {}
    )
    controllers_required = bool(getattr(effective_config, "controllers_required", True))

    default_decision = str(gate_defaults.get("default_decision", "ALLOW")).upper()
    decision = (
        Decision[default_decision] if default_decision in Decision.__members__ else Decision.ALLOW
    )
    reasons_seed = ["DEFAULT_POLICY"] if decision in (Decision.THROTTLE, Decision.DENY) else []
    if decision is Decision.DENY:
        position_multiplier = _clamp_multiplier(
            gate_defaults.get("min_position_multiplier", 0.0), gate_defaults
        )
    elif decision is Decision.THROTTLE:
        position_multiplier = _clamp_multiplier(
            gate_defaults.get("min_position_multiplier", 1.0), gate_defaults
        )
    else:
        position_multiplier = _clamp_multiplier(1.0, gate_defaults)
    throttle_ms = 0
    reasons: list[str] = list(reasons_seed)
    meta: dict[str, object] = {"proxy_flags": []}
    telemetry: dict[str, object] = {"signals": signals}

    required = ("serotonin", "thermo")
    missing = [name for name in required if controllers.get(name) is None]
    if missing:
        if controllers_required:
            raise RuntimeError(f"Mandatory controllers missing: {', '.join(missing)}")
        for name in missing:
            reasons.append(f"CTRL_MISSING_{name.upper()}")
            meta["proxy_flags"].append(f"{name}_missing")
        if reasons:
            decision = Decision.THROTTLE
            position_multiplier = _clamp_multiplier(
                gate_defaults.get("min_position_multiplier", 0.0), gate_defaults
            )

    def _apply(
        new_decision: Decision,
        new_multiplier: float,
        new_reasons: list[str],
        new_throttle_ms: int = 0,
    ) -> None:
        nonlocal decision, position_multiplier, throttle_ms, reasons
        if not new_reasons and new_decision in (Decision.THROTTLE, Decision.DENY):
            new_reasons = ["UNSPECIFIED"]
        if _severity(new_decision) > _severity(decision):
            decision = new_decision
            position_multiplier = new_multiplier
            throttle_ms = max(throttle_ms, new_throttle_ms)
        elif _severity(new_decision) == _severity(decision):
            position_multiplier = min(position_multiplier, new_multiplier)
            throttle_ms = max(throttle_ms, new_throttle_ms)
        reasons.extend([reason for reason in new_reasons if reason])

    serotonin_ctrl = controllers.get("serotonin")
    if serotonin_ctrl is not None:
        stress = signals.get("risk_score", signals.get("volatility", 1.0))
        drawdown = signals.get("drawdown", DEFAULT_DRAWDOWN)
        novelty = signals.get("free_energy", signals.get("novelty", stress))
        proxies = []
        if "risk_score" not in signals and "volatility" not in signals:
            proxies.append("stress_proxy")
        if "drawdown" not in signals:
            proxies.append("drawdown_proxy")
        if "free_energy" not in signals and "novelty" not in signals:
            proxies.append("novelty_proxy")
        meta["proxy_flags"].extend(proxies)
        try:
            drawdown_val = float(drawdown)
            if drawdown_val > 0:
                drawdown_val = -abs(drawdown_val)
        except (TypeError, ValueError):
            drawdown_val = DEFAULT_DRAWDOWN
            meta["proxy_flags"].append("drawdown_defaulted")
        observation = {
            "stress": max(0.0, float(stress) if isinstance(stress, (int, float)) else 1.0),
            "drawdown": drawdown_val,
            "novelty": max(0.0, float(novelty) if isinstance(novelty, (int, float)) else 0.5),
        }
        serotonin_output = serotonin_ctrl.update(observation)
        telemetry["serotonin"] = {
            "action_gate": getattr(serotonin_output, "action_gate", "UNKNOWN"),
            "reason_codes": list(getattr(serotonin_output, "reason_codes", ())),
            "metrics": getattr(serotonin_output, "metrics_snapshot", {}),
        }
        serotonin_reasons = list(getattr(serotonin_output, "reason_codes", ()))
        serotonin_gate = str(getattr(serotonin_output, "action_gate", "")).upper()
        hold_state = "HOLD" in serotonin_gate or serotonin_gate not in {"", "ALLOW"}
        serotonin_multiplier = _clamp_multiplier(
            getattr(serotonin_output, "risk_budget", position_multiplier), gate_defaults
        )
        throttle_reasons = serotonin_reasons.copy()
        if hold_state:
            throttle_reasons.append("SEROTONIN_INHIBIT")
        if hold_state and serotonin_multiplier <= gate_defaults.get("min_position_multiplier", 0.0):
            _apply(Decision.DENY, 0.0, throttle_reasons)
        elif hold_state:
            cooldown_s = 0.0
            metrics = getattr(serotonin_output, "metrics_snapshot", {}) or {}
            try:
                cooldown_s = float(metrics.get("cooldown_s", 0.0))
            except (TypeError, ValueError):
                cooldown_s = 0.0
            _apply(
                Decision.THROTTLE, serotonin_multiplier, throttle_reasons, int(cooldown_s * 1000)
            )
        else:
            if serotonin_multiplier < position_multiplier:
                _apply(
                    Decision.THROTTLE,
                    serotonin_multiplier,
                    serotonin_reasons or ["SEROTONIN_BUDGET"],
                )

    thermo_ctrl = controllers.get("thermo")
    if thermo_ctrl is not None:
        free_energy_signal = signals.get("free_energy")
        if free_energy_signal is None:
            meta["proxy_flags"].append("thermo_free_energy_proxy")
            free_energy_signal = getattr(thermo_ctrl, "previous_F", 0.0)
        try:
            free_energy_value = float(free_energy_signal)
        except (TypeError, ValueError):
            free_energy_value = 0.0
        baseline = getattr(thermo_ctrl, "baseline_F", None)
        epsilon = float(getattr(thermo_ctrl, "epsilon_adaptive", 0.0) or 0.0)
        circuit_breaker_active = bool(getattr(thermo_ctrl, "circuit_breaker_active", False))
        crisis_state = str(getattr(thermo_ctrl, "controller_state", "")).upper()
        telemetry["thermo"] = {
            "baseline_F": baseline,
            "epsilon": epsilon,
            "circuit_breaker_active": circuit_breaker_active,
            "controller_state": crisis_state,
            "free_energy": free_energy_value,
        }
        thermo_reasons: list[str] = []
        if circuit_breaker_active or crisis_state == "CRITICAL_HALT":
            thermo_reasons.append("THERMO_CIRCUIT_BREAKER")
            _apply(Decision.DENY, 0.0, thermo_reasons)
        elif baseline is not None:
            threshold = float(baseline) + max(epsilon, THERMO_EPSILON_FLOOR)
            if free_energy_value > threshold:
                thermo_reasons.append("THERMO_BUDGET_EXCEEDED")
                _apply(
                    Decision.THROTTLE,
                    _clamp_multiplier(
                        gate_defaults.get("min_position_multiplier", 0.0), gate_defaults
                    ),
                    thermo_reasons,
                )

    gate = GateDecision(
        decision=decision,
        position_multiplier=position_multiplier if decision is not Decision.DENY else 0.0,
        throttle_ms=throttle_ms,
        reasons=reasons,
        meta=meta,
    )
    telemetry["gate_summary"] = {**gate.meta, "decision": gate.decision.value}
    event = build_decision_event(
        gate=gate,
        telemetry=telemetry,
        effective_config=effective_config,
        signals=signals,
    )
    emit_decision_event(event, logger=LOGGER)
    return GatePipelineResult(
        gate=gate, controllers=dict(controllers), telemetry=telemetry, decision_event=event
    )


__all__ = ["Decision", "GateDecision", "GatePipelineResult", "evaluate_control_gates"]
