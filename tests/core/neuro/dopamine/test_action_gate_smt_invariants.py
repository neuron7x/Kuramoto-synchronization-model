# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from z3 import If, Real, Solver, sat


def test_action_gate_score_and_temperature_bounds_have_smt_witnesses() -> None:
    raw_level = Real("raw_level")
    raw_inhibition = Real("raw_inhibition")
    raw_attention = Real("raw_attention")
    raw_temperature = Real("raw_temperature")
    raw_scale = Real("raw_scale")
    raw_floor = Real("raw_floor")

    da = If(raw_level < 0.0, 0.0, If(raw_level > 1.0, 1.0, raw_level))
    inhibition = If(
        raw_inhibition < 0.0,
        0.0,
        If(raw_inhibition > 0.99, 0.99, raw_inhibition),
    )
    attention = If(raw_attention < 0.2, 0.2, If(raw_attention > 2.0, 2.0, raw_attention))
    temp_scale = If(raw_scale < 0.2, 0.2, If(raw_scale > 3.0, 3.0, raw_scale))
    base_temperature = If(raw_temperature < 0.0, 0.0, raw_temperature)
    serotonin_floor = If(raw_floor < 0.0, 0.0, raw_floor)

    raw_score = da * (1.0 - inhibition) * attention
    score = If(raw_score < 0.0, 0.0, If(raw_score > 1.0, 1.0, raw_score))
    scaled_temperature = If(
        base_temperature * temp_scale < serotonin_floor,
        serotonin_floor,
        base_temperature * temp_scale,
    )
    clamped_temperature = If(
        scaled_temperature < 0.2,
        0.2,
        If(scaled_temperature > 0.6, 0.6, scaled_temperature),
    )

    solver = Solver()
    solver.add(raw_level >= -1000.0, raw_level <= 1000.0)
    solver.add(raw_inhibition >= -1000.0, raw_inhibition <= 1000.0)
    solver.add(raw_attention >= -1000.0, raw_attention <= 1000.0)
    solver.add(raw_temperature >= -1000.0, raw_temperature <= 1000.0)
    solver.add(raw_scale >= -1000.0, raw_scale <= 1000.0)
    solver.add(raw_floor >= -1000.0, raw_floor <= 1000.0)

    solver.push()
    solver.add((score < 0.0) | (score > 1.0))
    assert solver.check() != sat
    solver.pop()

    solver.push()
    solver.add((clamped_temperature < 0.2) | (clamped_temperature > 0.6))
    assert solver.check() != sat
    solver.pop()
