"""Risk-scalar computation with fail-closed behavior."""

from __future__ import annotations

import math


def compute_risk_scalar(gamma: float, *, fail_closed: bool = True) -> float:
    """Compute risk-scalar from gamma distance to metastable point (1.0).

    If ``fail_closed`` and gamma is not finite, return 0.0 (safe default).
    """
    if not math.isfinite(gamma):
        return 0.0 if fail_closed else 1.0
    return max(0.0, min(1.0, 1.0 - abs(gamma - 1.0)))
