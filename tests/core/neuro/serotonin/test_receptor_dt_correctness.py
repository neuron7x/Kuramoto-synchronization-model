# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Receptor low-pass filters must be step-size correct.

Previously the low-pass blend factor was a fixed per-step constant, so a receptor's
effective time constant silently depended on the caller's dt. The correct factor is
alpha_eff = 1 - (1 - alpha)**dt, whose defining property is the semigroup identity:
one step of size dt == dt unit-steps under a constant input. These tests lock that in
and confirm dt is actually threaded through the receptors.
"""
from __future__ import annotations

import pytest

from geosync.core.neuro.serotonin.receptors import ht1a
from geosync.core.neuro.serotonin.receptors.dynamics import low_pass
from geosync.core.neuro.serotonin.receptors.types import ReceptorContext, ReceptorState


def test_dt_one_matches_the_plain_per_step_alpha() -> None:
    assert low_pass(0.2, 0.8, 0.5, 1.0) == pytest.approx(low_pass(0.2, 0.8, 0.5))


def test_semigroup_one_dt2_step_equals_two_unit_steps() -> None:
    prev, new, alpha = 0.2, 0.8, 0.4
    once = low_pass(prev, new, alpha, dt=2.0)
    twice = low_pass(low_pass(prev, new, alpha, 1.0), new, alpha, 1.0)
    assert once == pytest.approx(twice)


def test_larger_dt_moves_further_toward_the_target() -> None:
    prev, new, alpha = 0.0, 1.0, 0.3
    small = low_pass(prev, new, alpha, dt=0.5)
    unit = low_pass(prev, new, alpha, dt=1.0)
    large = low_pass(prev, new, alpha, dt=4.0)
    assert prev < small < unit < large < new


def _ctx(dt: float) -> ReceptorContext:
    return ReceptorContext(
        volatility_norm=0.7,
        drawdown_norm=0.0,
        novelty_norm=0.5,
        shock_norm=0.0,
        impulse_pressure_norm=0.0,
        regime_entropy_norm=0.0,
        dt=dt,
    )


def test_receptor_threads_dt_semigroup() -> None:
    # ht1a under a constant context: one dt=2 step must equal two dt=1 steps.
    state_two_unit = ReceptorState()
    ht1a.compute_activation(_ctx(1.0), state_two_unit)
    a_two_unit = ht1a.compute_activation(_ctx(1.0), state_two_unit)

    state_one_double = ReceptorState()
    a_one_double = ht1a.compute_activation(_ctx(2.0), state_one_double)

    assert a_two_unit == pytest.approx(a_one_double)
