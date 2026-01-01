from __future__ import annotations

from .dynamics import bounded_sigmoid, clamp, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    stress = max(ctx.drawdown_norm, 0.7 * ctx.novelty_norm)
    activation = bounded_sigmoid(stress - 0.2, k=3.2)
    activation = low_pass(state.prev_activation, activation, 0.55)
    state.prev_activation = activation
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.2:
        return ParamDeltas()
    cap_delta = -0.3 * activation
    veto_bias = 0.08 * activation
    return ParamDeltas(pos_mult_cap_delta=cap_delta, veto_bias=veto_bias)
