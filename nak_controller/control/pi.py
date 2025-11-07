"""Non-linear PI controller for EI regulation."""
from __future__ import annotations

import math
from typing import Tuple

from ..core.params import NaKParams
from ..core.state import StrategyState, clip


def band_center_width(params: NaKParams, band_expand: float) -> Tuple[float, float]:
    """Return the EI target band centre and half-width."""

    centre = 0.5 * (params.EI_low + params.EI_high)
    half_width = max(1e-6, 0.5 * (params.EI_high - params.EI_low) * band_expand)
    return centre, half_width


def pi_control(state: StrategyState, params: NaKParams, band_expand: float) -> Tuple[float, float, float]:
    """Apply a tanh PI controller to derive the risk multiplier."""

    centre, half_width = band_center_width(params, band_expand)
    error = (state.EI - centre) / half_width
    tanh_error = math.tanh(error)

    state.integral = clip(state.integral + tanh_error, -params.I_max, params.I_max)
    integ = math.tanh(state.integral / max(1e-6, params.I_max / 2))
    control = params.Kp * tanh_error + params.Ki * integ
    r_tilde = clip(1.0 + control, params.r_min, params.r_max)
    return error, state.integral, r_tilde


def rate_limit(prev: float | None, target: float, limit: float, lo: float, hi: float) -> float:
    """Rate limit the change from *prev* to *target* by *limit*."""

    if prev is None:
        return clip(target, lo, hi)
    delta = max(-limit, min(limit, target - prev))
    return clip(prev + delta, lo, hi)


__all__ = ["band_center_width", "pi_control", "rate_limit"]
