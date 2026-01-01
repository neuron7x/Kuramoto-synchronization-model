from __future__ import annotations

import math

from .dynamics import clamp, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    if ctx.circadian_phase is None:
        return 0.0
    phase = float(ctx.circadian_phase % (2 * math.pi))
    rhythm = 0.5 * (1.0 + math.sin(phase - math.pi / 2))
    activation = low_pass(state.prev_activation, rhythm, 0.4)
    state.prev_activation = activation
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.1:
        return ParamDeltas()
    temp_adjust = 0.05 * (activation - 0.2)
    hysteresis_delta = 0.02 * activation
    return ParamDeltas(
        temperature_floor_delta=temp_adjust,
        hold_hysteresis_delta=hysteresis_delta,
    )
