# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import List

from hypothesis import given, settings, strategies as st

from geosync.core.neuro.dopamine.action_gate import (
    ActionGate,
    DopamineSnapshot,
    GABASnapshot,
    NAACHSnapshot,
    SerotoninSnapshot,
)

FINITE_FLOATS = st.floats(
    min_value=-1_000.0,
    max_value=1_000.0,
    allow_nan=False,
    allow_infinity=False,
    width=32,
)


class _Provider:
    def __init__(self) -> None:
        self.events: List[tuple[str, float]] = []

    def temperature_bounds(self) -> tuple[float, float]:
        return (0.2, 0.6)

    def _log(self, name: str, value: float) -> None:
        self.events.append((name, value))


def _assert_invariants(evaluation) -> None:
    assert 0.0 <= evaluation.dopamine_level <= 1.0
    assert 0.0 <= evaluation.score <= 1.0
    assert 0.2 <= evaluation.temperature <= 0.6
    assert evaluation.decision in {"GO", "HOLD", "NO_GO"}
    assert evaluation.go is (evaluation.decision == "GO")
    if evaluation.decision == "GO":
        assert evaluation.hold is False
        assert evaluation.no_go is False
    if evaluation.decision == "HOLD":
        assert evaluation.go is False
        assert evaluation.no_go is False
    if evaluation.decision == "NO_GO":
        assert evaluation.no_go is True


@given(
    level=FINITE_FLOATS,
    temperature=FINITE_FLOATS,
    go_threshold=FINITE_FLOATS,
    hold_threshold=FINITE_FLOATS,
    no_go_threshold=FINITE_FLOATS,
    release_gate_open=st.booleans(),
    serotonin_hold=st.booleans(),
    serotonin_floor=FINITE_FLOATS,
    inhibition=FINITE_FLOATS,
    attention=FINITE_FLOATS,
    temperature_scale=FINITE_FLOATS,
)
@settings(max_examples=300, deadline=None)
def test_action_gate_property_fuzz_invariants(
    level: float,
    temperature: float,
    go_threshold: float,
    hold_threshold: float,
    no_go_threshold: float,
    release_gate_open: bool,
    serotonin_hold: bool,
    serotonin_floor: float,
    inhibition: float,
    attention: float,
    temperature_scale: float,
) -> None:
    gate = ActionGate(_Provider())
    evaluation = gate.evaluate(
        dopamine=DopamineSnapshot(
            level=level,
            temperature=temperature,
            go_threshold=go_threshold,
            hold_threshold=hold_threshold,
            no_go_threshold=no_go_threshold,
            release_gate_open=release_gate_open,
        ),
        serotonin=SerotoninSnapshot(
            level=0.0,
            hold=serotonin_hold,
            temperature_floor=max(0.0, serotonin_floor),
        ),
        gaba=GABASnapshot(inhibition=inhibition, stdp_dw=-0.01 * inhibition),
        na_ach=NAACHSnapshot(
            arousal=1.0,
            attention=attention,
            risk_multiplier=1.0,
            temperature_scale=temperature_scale,
        ),
    )

    _assert_invariants(evaluation)
