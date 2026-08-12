# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import types
from typing import Any

import pytest

from application.runtime.control_gates import Decision, evaluate_control_gates
from application.runtime.decision_telemetry import build_decision_event


class _Config:
    def __init__(
        self, gate_defaults: dict | None = None, controllers_required: bool = True
    ) -> None:
        self.gate_defaults = gate_defaults or {
            "min_position_multiplier": 0.0,
            "max_position_multiplier": 1.0,
            "default_decision": "ALLOW",
        }
        self.controllers_required = controllers_required


class _Serotonin:
    def __init__(
        self,
        *,
        action_gate: str = "ALLOW",
        risk_budget: float = 1.0,
        reason_codes: tuple[str, ...] = (),
        metrics: dict | None = None,
    ) -> None:
        self._action_gate = action_gate
        self._risk_budget = risk_budget
        self._reason_codes = reason_codes
        self._metrics = metrics or {}

    def update(self, observation: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            action_gate=self._action_gate,
            risk_budget=self._risk_budget,
            reason_codes=self._reason_codes,
            metrics_snapshot=self._metrics,
        )


class _Thermo:
    def __init__(
        self,
        *,
        baseline_F: float | None = None,
        epsilon_adaptive: float = 0.0,
        circuit_breaker_active: bool = False,
        controller_state: str = "OK",
        previous_F: float = 0.0,
    ) -> None:
        self.baseline_F = baseline_F
        self.epsilon_adaptive = epsilon_adaptive
        self.circuit_breaker_active = circuit_breaker_active
        self.controller_state = controller_state
        self.previous_F = previous_F


def test_default_policy_falls_back_to_allow_and_clamps_max() -> None:
    cfg = _Config(
        gate_defaults={
            "default_decision": "unknown",
            "min_position_multiplier": 0.0,
            "max_position_multiplier": 0.7,
        }
    )
    serotonin = _Serotonin(action_gate="ALLOW", risk_budget=2.0)
    thermo = _Thermo()

    result = evaluate_control_gates(
        cfg, {"serotonin": serotonin, "thermo": thermo}, {"risk_score": 0.1}
    )

    assert result.gate.decision is Decision.ALLOW
    assert result.gate.position_multiplier == pytest.approx(0.7)
    assert result.telemetry["gate_summary"]["decision"] == "ALLOW"


def test_missing_required_controllers_raise() -> None:
    cfg = _Config()
    with pytest.raises(RuntimeError):
        evaluate_control_gates(cfg, {"serotonin": None, "thermo": None}, {})


def test_optional_controllers_missing_throttle_and_flag_proxies() -> None:
    cfg = _Config(
        gate_defaults={
            "default_decision": "ALLOW",
            "min_position_multiplier": 0.25,
            "max_position_multiplier": 1.0,
        },
        controllers_required=False,
    )

    result = evaluate_control_gates(cfg, {"serotonin": None, "thermo": None}, {})

    assert result.gate.decision is Decision.THROTTLE
    assert result.gate.position_multiplier == pytest.approx(0.25)
    assert "CTRL_MISSING_SEROTONIN" in result.gate.reasons
    assert "serotonin_missing" in result.gate.meta["proxy_flags"]
    assert "thermo_missing" in result.gate.meta["proxy_flags"]


def test_serotonin_hold_boundary_throttle_vs_deny() -> None:
    cfg = _Config(
        gate_defaults={
            "default_decision": "ALLOW",
            "min_position_multiplier": 0.05,
            "max_position_multiplier": 1.0,
        }
    )
    thermo = _Thermo()

    throttle_serotonin = _Serotonin(
        action_gate="HOLD_OR_REDUCE_ONLY",
        risk_budget=0.2,
        reason_codes=("COOL_DOWN",),
        metrics={"cooldown_s": 0.75},
    )
    throttle_result = evaluate_control_gates(
        cfg,
        {"serotonin": throttle_serotonin, "thermo": thermo},
        {"risk_score": 2.5, "drawdown": -0.2},
    )

    assert throttle_result.gate.decision is Decision.THROTTLE
    assert throttle_result.gate.position_multiplier == pytest.approx(0.2)
    assert throttle_result.gate.throttle_ms >= 700
    assert "SEROTONIN_INHIBIT" in throttle_result.gate.reasons

    deny_serotonin = _Serotonin(
        action_gate="HOLD",
        risk_budget=0.0,
        reason_codes=("STUCK",),
        metrics={"cooldown_s": 0.3},
    )
    deny_result = evaluate_control_gates(
        cfg,
        {"serotonin": deny_serotonin, "thermo": thermo},
        {"risk_score": 5.0, "drawdown": -0.5},
    )

    assert deny_result.gate.decision is Decision.DENY
    assert deny_result.gate.position_multiplier == 0.0
    assert "SEROTONIN_INHIBIT" in deny_result.gate.reasons


def test_decision_event_shape_preserves_proxies_and_inputs() -> None:
    gate_cfg = _Config(
        gate_defaults={
            "default_decision": "THROTTLE",
            "min_position_multiplier": 0.1,
            "max_position_multiplier": 1.0,
        },
        controllers_required=False,
    )
    gate_result = evaluate_control_gates(
        gate_cfg,
        {"serotonin": _Serotonin(action_gate="ALLOW", risk_budget=1.0), "thermo": _Thermo()},
        {"token": "should_be_sanitized"},
    )

    event = build_decision_event(
        gate=gate_result.gate,
        telemetry=gate_result.telemetry,
        effective_config=gate_cfg,
        signals={"token": "secret"},
    )

    assert event["decision"] == "THROTTLE"
    assert "token" not in event["inputs_summary"]
    assert event["inputs_summary"] == {}
    assert event["proxies"]["proxy_risk"] is True
    assert "thermo" in event["controller_states"]
