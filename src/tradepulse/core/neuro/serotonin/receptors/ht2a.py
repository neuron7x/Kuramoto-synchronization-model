from __future__ import annotations

from .dynamics import bounded_sigmoid, clamp, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    stability = clamp(1.0 - ctx.drawdown_norm - 0.3 * ctx.shock_norm, 0.0, 1.0)
    activation = bounded_sigmoid(stability - 0.4, k=2.0)
    activation = low_pass(state.prev_activation, activation, 0.35)
    state.prev_activation = activation
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.2:
        return ParamDeltas()
    temp_delta = 0.08 * activation
    phasic_delta = -0.05 * activation
    return ParamDeltas(
        temperature_floor_delta=temp_delta,
        phasic_weight_delta=phasic_delta,
    )
