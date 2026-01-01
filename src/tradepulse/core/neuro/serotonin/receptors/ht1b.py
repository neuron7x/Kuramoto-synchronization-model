from __future__ import annotations

from .dynamics import bounded_sigmoid, clamp, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    base = clamp(ctx.impulse_pressure_norm, 0.0, 2.0)
    activation = bounded_sigmoid(base - 0.3, k=3.0)
    activation = low_pass(state.prev_activation, activation, 0.5)
    state.prev_activation = activation
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.25:
        return ParamDeltas()
    cooldown = 1.5 * activation
    phasic_delta = -0.3 * activation
    return ParamDeltas(cooldown_s=cooldown, phasic_weight_delta=phasic_delta)
