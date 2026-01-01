from __future__ import annotations

from .dynamics import bounded_sigmoid, clamp, hysteresis_latch, low_pass
from .types import ParamDeltas, ReceptorContext, ReceptorState


def compute_activation(ctx: ReceptorContext, state: ReceptorState) -> float:
    raw = max(ctx.shock_norm, ctx.volatility_norm)
    trend = low_pass(state.prev_activation, raw, 0.6)
    activation = bounded_sigmoid(trend * 2.0, k=2.5)
    state.prev_activation = activation
    # Hysteresis latch to avoid chatter
    state.latched = hysteresis_latch(
        activation > 0.4, state.latched, enter=0.55, exit=0.35, signal=activation
    )
    if state.latched:
        activation = max(activation, 0.6)
    return clamp(activation, 0.0, 1.0)


def compute_deltas(ctx: ReceptorContext, activation: float) -> ParamDeltas:
    if activation < 0.35:
        return ParamDeltas()
    cooldown = 3.0 * activation
    temp_delta = -0.15 * activation
    hysteresis_delta = 0.05 * activation
    force_veto = activation > 0.75
    veto_bias = 0.1 * activation
    return ParamDeltas(
        cooldown_s=cooldown,
        temperature_floor_delta=temp_delta,
        hold_hysteresis_delta=hysteresis_delta,
        veto_bias=veto_bias,
        force_veto=force_veto,
    )
