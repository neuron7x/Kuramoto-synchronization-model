"""Non-linear PI controller utilities for the NaK controller.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

import math

from ..core.params import NaKParams
from ..core.state import StrategyState, clip


def band_center_width(p: NaKParams, band_expand: float) -> tuple[float, float]:
    center = 0.5 * (p.EI_low + p.EI_high)
    halfw = max(1e-6, 0.5 * (p.EI_high - p.EI_low) * band_expand)
    return center, halfw


def pi_control(st: StrategyState, p: NaKParams, band_expand: float) -> tuple[float, float, float]:
    c, hw = band_center_width(p, band_expand)
    e = (st.EI - c) / hw  # normalized error (~[-1, 1])
    # anti-windup integral with tanh smoothing
    st.pi_integral = clip(st.pi_integral + math.tanh(e), -p.I_max, p.I_max)
    u = p.Kp * math.tanh(e) + p.Ki * math.tanh(st.pi_integral / max(1e-6, p.I_max / 2))
    r_tilde = clip(1.0 + u, p.r_min, p.r_max)
    return e, st.pi_integral, r_tilde


def rate_limit(prev: float | None, target: float, limit: float, lo: float, hi: float) -> float:
    if prev is None:
        return clip(target, lo, hi)
    delta = max(-limit, min(limit, target - prev))
    return clip(prev + delta, lo, hi)
