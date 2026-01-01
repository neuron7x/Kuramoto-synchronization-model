from __future__ import annotations

from .dynamics import bounded_sigmoid, clamp, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    sustained = 0.6 * ctx.volatility_norm + 0.4 * ctx.novelty_norm
    activation = bounded_sigmoid(sustained - 0.3, k=2.2)
    activation = low_pass(state.prev_activation, activation, 0.45)
    state.prev_activation = activation
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.15:
        return ParamDeltas()
    hysteresis_delta = 0.04 * activation
    tonic_boost = 0.15 * activation
    return ParamDeltas(
        hold_hysteresis_delta=hysteresis_delta,
        tonic_weight_delta=tonic_boost,
    )
