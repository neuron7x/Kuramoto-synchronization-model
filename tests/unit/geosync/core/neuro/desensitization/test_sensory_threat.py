# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from geosync.core.neuro.desensitization import (
    SensoryHabituation,
    SensoryHabituationConfig,
    ThreatGate,
)


def test_sensory_habituation_recovers_on_new_context() -> None:
    hab = SensoryHabituation(SensoryHabituationConfig(recovery_hl=5))
    val1, _ = hab.update([1.0, 0.0])
    for _ in range(10):
        val1, _ = hab.update([1.0, 0.0])
    assert val1 < 1.0
    val2, state = hab.update([0.0, 1.0])
    assert val2 > val1
    assert state["ticks_in_ctx"] == 0.0


def test_threat_gate_reopens_after_breach() -> None:
    gate = ThreatGate()
    value, _ = gate.update(drawdown=0.05, vol=0.02)
    assert 0.0 <= value <= 1.0
    value, state = gate.update(drawdown=0.2, vol=0.03)
    assert value == gate.cfg.min_gate
    for _ in range(200):
        value, state = gate.update(drawdown=0.01, vol=0.02)
    assert state["breached"] in {0.0, 1.0}
    assert gate.cfg.min_gate <= value <= 1.0
