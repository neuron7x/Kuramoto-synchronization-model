# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math


def clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def low_pass(prev: float, new: float, alpha: float, dt: float = 1.0) -> float:
    """First-order low-pass with a *time-correct* smoothing factor.

    ``alpha`` is the per-unit-time (dt=1) blend. Under a different step size the
    effective factor is ``alpha_eff = 1 - (1 - alpha)**dt`` — exactly the result of
    applying the unit-step filter ``dt`` times — so the filter's time constant no
    longer silently depends on the caller's step size. At dt=1 this is identically
    ``alpha`` (backward compatible); dt is clamped to ≥0.
    """
    alpha = clamp(alpha, 0.0, 1.0)
    dt = max(0.0, float(dt))  # bounds: dt ≥ 0 (negative step size is meaningless)
    alpha_eff = alpha if dt == 1.0 else 1.0 - (1.0 - alpha) ** dt
    return float((1.0 - alpha_eff) * prev + alpha_eff * new)


def hysteresis_latch(
    active: bool, prev_latched: bool, enter: float, exit: float, signal: float
) -> bool:
    if prev_latched:
        return signal > exit
    return active and signal >= enter


def bounded_sigmoid(x: float, k: float = 3.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * max(-5.0, min(5.0, x))))
