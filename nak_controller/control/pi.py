"""PI control loop used to modulate risk exposure."""

from __future__ import annotations

import math
from typing import Optional, Tuple

from ..core.params import NaKParams
from ..core.state import StrategyState, clip


def band_center_width(params: NaKParams, band_expand: float) -> Tuple[float, float]:
    """Compute the center and half-width of the EI control band."""
    center = 0.5 * (params.EI_low + params.EI_high)
    half_width = max(1e-6, 0.5 * (params.EI_high - params.EI_low) * band_expand)
    return center, half_width


def pi_control(
    state: StrategyState, params: NaKParams, *, band_expand: float
) -> Tuple[float, float, float]:
    """Execute a PI step returning the normalized error, integrator and raw rate."""
    center, half_width = band_center_width(params, band_expand)
    error = (state.EI - center) / half_width
    tanh_error = math.tanh(error)
    state.I = clip(state.I + tanh_error, -params.I_max, params.I_max)  # noqa: E741
    integrator_term = math.tanh(state.I / max(1e-6, params.I_max / 2.0))
    control = params.Kp * tanh_error + params.Ki * integrator_term
    rate_target = clip(1.0 + control, params.r_min, params.r_max)
    return error, state.I, rate_target


def rate_limit(
    previous: Optional[float], target: float, *, limit: float, lo: float, hi: float
) -> float:
    """Apply a symmetric rate limit to the target value."""
    limited_target = clip(target, lo, hi)
    if previous is None:
        return limited_target
    delta = max(-limit, min(limit, limited_target - previous))
    return clip(previous + delta, lo, hi)


__all__ = ["band_center_width", "pi_control", "rate_limit"]
