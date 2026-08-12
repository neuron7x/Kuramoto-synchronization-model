# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""INV-5HT3 — monotone stress response (qualitative), the P1 invariant the suite
did not previously witness.

Theory: holding other inputs constant, a *single step* from a fresh controller
(before receptor desensitisation can build up) must give a non-decreasing serotonin
signal as stress rises. Desensitisation may later reverse this over time — that is
correct biology and explicitly outside INV-5HT3 — so the witness compares fresh
controllers on their first step, sweeping one input while holding the others.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController


def _first_step_level(stress: float, drawdown: float, novelty: float) -> float:
    return float(
        SerotoninController().step(stress=stress, drawdown=drawdown, novelty=novelty).level
    )


@given(
    stress_low=st.floats(min_value=0.0, max_value=2.5),
    stress_delta=st.floats(min_value=0.0, max_value=0.5),
    drawdown=st.floats(min_value=-0.6, max_value=0.0),
    novelty=st.floats(min_value=0.0, max_value=2.0),
)
@settings(max_examples=150, deadline=1000)
def test_single_step_serotonin_is_non_decreasing_in_stress(
    stress_low: float,
    stress_delta: float,
    drawdown: float,
    novelty: float,
) -> None:
    low = _first_step_level(stress_low, drawdown, novelty)
    high = _first_step_level(stress_low + stress_delta, drawdown, novelty)
    assert high >= low - 1e-9, (
        f"INV-5HT3 VIOLATED: raising stress {stress_low:.4f}→{stress_low + stress_delta:.4f} "
        f"(drawdown={drawdown:.3f}, novelty={novelty:.3f}) dropped the single-step serotonin "
        f"signal {low:.6f}→{high:.6f}. A fresh controller, before desensitisation, must not "
        f"decrease s(t) as stress rises."
    )


@given(
    stress=st.floats(min_value=0.0, max_value=3.0),
    novelty=st.floats(min_value=0.0, max_value=2.0),
    dd_mild=st.floats(min_value=-0.3, max_value=0.0),
    dd_extra=st.floats(min_value=0.0, max_value=0.3),
)
@settings(max_examples=150, deadline=1000)
def test_single_step_serotonin_is_non_decreasing_in_drawdown_magnitude(
    stress: float,
    novelty: float,
    dd_mild: float,
    dd_extra: float,
) -> None:
    # Larger loss magnitude (more negative drawdown) is a stronger aversive input.
    mild = _first_step_level(stress, dd_mild, novelty)
    severe = _first_step_level(stress, dd_mild - dd_extra, novelty)
    assert severe >= mild - 1e-9, (
        f"INV-5HT3 VIOLATED: deepening drawdown {dd_mild:.3f}→{dd_mild - dd_extra:.3f} "
        f"(stress={stress:.3f}, novelty={novelty:.3f}) dropped single-step serotonin "
        f"{mild:.6f}→{severe:.6f}."
    )
