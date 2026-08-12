# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from application.runtime.control_gates import Decision
from application.runtime.init_control_platform import initialize_control_platform
from core.neuro.serotonin.serotonin_controller import ControllerOutput


class SerotoninHoldStub:
    def update(self, observation):  # noqa: ARG002 - signature matches controller API
        return ControllerOutput(
            mode="DEFENSIVE",
            risk_budget=0.0,
            action_gate="HOLD_OR_REDUCE_ONLY",
            reason_codes=("SEROTONIN_INHIBIT",),
            metrics_snapshot={"cooldown_s": 1.0, "serotonin_level": 0.9},
        )


class SerotoninAllowStub:
    def update(self, observation):  # noqa: ARG002 - signature matches controller API
        return ControllerOutput(
            mode="NORMAL",
            risk_budget=1.0,
            action_gate="ALLOW",
            reason_codes=(),
            metrics_snapshot={"cooldown_s": 0.0, "serotonin_level": 0.1},
        )


class ThermoBudgetStub:
    def __init__(self, baseline_F: float = 0.05, epsilon: float = 0.01) -> None:
        self.baseline_F = baseline_F
        self.epsilon_adaptive = epsilon
        self.circuit_breaker_active = False
        self.controller_state = "NORMAL"
        self.previous_F = baseline_F

    def get_current_F(self) -> float:
        return float(self.previous_F)


def test_serotonin_inhibits_gate_throttle_or_deny():
    init_result = initialize_control_platform(
        serotonin_factory=lambda *_: SerotoninHoldStub(),
        thermo_factory=lambda *_: ThermoBudgetStub(),
    )
    signals = {"risk_score": 5.0, "drawdown": -0.2, "free_energy": 1.5}

    result = init_result.gate_pipeline(
        init_result.runtime_settings, init_result.controllers, signals
    )

    assert result.gate.decision in (Decision.THROTTLE, Decision.DENY)
    assert "SEROTONIN_INHIBIT" in result.gate.reasons
    assert result.telemetry["serotonin"]["reason_codes"]


def test_thermo_budget_exceeded_throttles():
    thermo = ThermoBudgetStub(baseline_F=0.05, epsilon=0.01)
    init_result = initialize_control_platform(
        serotonin_factory=lambda *_: SerotoninAllowStub(),
        thermo_factory=lambda *_: thermo,
    )
    signals = {"free_energy": 1.0, "risk_score": 0.1, "drawdown": -0.01}

    result = init_result.gate_pipeline(
        init_result.runtime_settings, init_result.controllers, signals
    )

    assert result.gate.decision in (Decision.THROTTLE, Decision.DENY)
    assert any(reason == "THERMO_BUDGET_EXCEEDED" for reason in result.gate.reasons)
