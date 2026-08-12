# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from geosync.core.neuro.dopamine.action_gate import (
    ActionGate,
    DopamineSnapshot,
    GABASnapshot,
    NAACHSnapshot,
    SerotoninSnapshot,
)


ACTION_GATE_PATH = Path("src/geosync/core/neuro/dopamine/action_gate.py")


class _BoundsOnlyProvider:
    def __init__(self) -> None:
        self.events: List[tuple[str, float]] = []

    def temperature_bounds(self) -> tuple[float, float]:
        return (0.2, 0.6)

    def _log(self, name: str, value: float) -> None:
        self.events.append((name, value))


class _DynamicBoundsProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.events: List[tuple[str, float]] = []

    def temperature_bounds(self) -> tuple[float, float]:
        self.calls += 1
        if self.calls == 1:
            return (0.2, 0.4)
        return (0.5, 0.7)

    def _log(self, name: str, value: float) -> None:
        self.events.append((name, value))


def test_action_gate_module_does_not_import_concrete_dopamine_controller() -> None:
    source = ACTION_GATE_PATH.read_text(encoding="utf-8")

    assert "dopamine_controller" not in source
    assert "DopamineController" not in source
    assert "TemperatureBoundsProvider" in source


def test_action_gate_uses_dynamic_structural_bounds_on_each_evaluation() -> None:
    provider = _DynamicBoundsProvider()
    gate = ActionGate(provider)
    dopamine = DopamineSnapshot(
        level=0.9,
        temperature=9.0,
        go_threshold=0.2,
        hold_threshold=0.1,
        no_go_threshold=0.05,
        release_gate_open=True,
    )

    first = gate.evaluate(dopamine=dopamine)
    second = gate.evaluate(dopamine=dopamine)

    assert first.temperature == pytest.approx(0.4)
    assert second.temperature == pytest.approx(0.7)
    assert provider.calls == 2
    assert sum(name == "tacl.ag.decision" for name, _ in provider.events) == 2


def test_action_gate_survives_dynamic_modulator_stress() -> None:
    provider = _BoundsOnlyProvider()
    gate = ActionGate(provider)
    decisions: set[str] = set()
    cases = 0

    for level in (-10.0, 0.0, 0.05, 0.35, 0.85, 10.0):
        for temp in (-5.0, 0.0, 1e-12, 0.4, 99.0):
            for inhibition in (-1.0, 0.0, 0.79, 0.8, 2.0):
                for attention, temp_scale in (
                    (-4.0, -2.0),
                    (0.2, 0.2),
                    (1.0, 1.0),
                    (9.0, 9.0),
                ):
                    evaluation = gate.evaluate(
                        dopamine=DopamineSnapshot(
                            level=level,
                            temperature=temp,
                            go_threshold=0.5,
                            hold_threshold=0.2,
                            no_go_threshold=0.1,
                            release_gate_open=True,
                        ),
                        serotonin=SerotoninSnapshot(
                            level=0.0,
                            hold=inhibition > 1.0,
                            temperature_floor=max(0.0, temp),
                        ),
                        gaba=GABASnapshot(
                            inhibition=inhibition,
                            stdp_dw=-0.01 * inhibition,
                        ),
                        na_ach=NAACHSnapshot(
                            arousal=1.0,
                            attention=attention,
                            risk_multiplier=1.0,
                            temperature_scale=temp_scale,
                        ),
                    )

                    cases += 1
                    decisions.add(evaluation.decision)
                    assert 0.0 <= evaluation.dopamine_level <= 1.0
                    assert 0.0 <= evaluation.score <= 1.0
                    assert 0.2 <= evaluation.temperature <= 0.6
                    assert evaluation.decision in {"GO", "HOLD", "NO_GO"}
                    assert evaluation.go is (evaluation.decision == "GO")
                    if evaluation.decision == "NO_GO":
                        assert evaluation.no_go is True
                    if evaluation.decision == "HOLD":
                        assert evaluation.go is False
                        assert evaluation.no_go is False

    assert cases == 600
    assert {"GO", "HOLD", "NO_GO"}.issubset(decisions)
    assert any(name == "tacl.ag.decision" for name, _ in provider.events)
