from __future__ import annotations

import math


def clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def low_pass(prev: float, new: float, alpha: float) -> float:
    alpha = clamp(alpha, 0.0, 1.0)
    return float((1.0 - alpha) * prev + alpha * new)


def hysteresis_latch(active: bool, prev_latched: bool, enter: float, exit: float, signal: float) -> bool:
    if prev_latched:
        return signal > exit
    return active and signal >= enter


def bounded_sigmoid(x: float, k: float = 3.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * max(-5.0, min(5.0, x))))
