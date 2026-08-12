# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from tacl.risk_gating import PreActionContext, RiskGatingConfig, RiskGatingEngine


def test_latency_spike_triggers_rollback() -> None:
    cfg = RiskGatingConfig()
    gate = RiskGatingEngine(cfg)
    decision = gate.check(
        PreActionContext(
            venue="x",
            symbol="ETHUSDT",
            side="SELL",
            quantity=2.0,
            latency_ms=cfg.hard_latency_ms + 1.0,
        )
    )

    assert decision.allowed is False
    assert decision.rollback is True
    assert "latency_spike" in decision.reasons


def test_latency_degraded_switches_to_safe_policy() -> None:
    cfg = RiskGatingConfig()
    gate = RiskGatingEngine(cfg)
    decision = gate.check(
        PreActionContext(
            venue="x",
            symbol="ETHUSDT",
            side="SELL",
            quantity=2.0,
            latency_ms=cfg.max_latency_ms + 1.0,
        )
    )

    assert decision.allowed is True
    assert decision.safe_mode is True
    assert decision.policy_override == cfg.safe_policy
    assert "latency_degraded" in decision.reasons
