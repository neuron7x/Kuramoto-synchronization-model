"""Conditional Value-at-Risk gating utilities."""

from __future__ import annotations

import numpy as np


def cvar(returns: list[float] | np.ndarray, alpha: float = 0.95) -> float:
    """Compute the left-tail CVaR at level ``alpha``."""

    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    return float(tail.mean()) if tail.size > 0 else 0.0


class CVARGate:
    """Scale allocations to enforce a CVaR limit."""

    def __init__(self, alpha: float = 0.95, limit: float = 0.03, lookback: int = 50):
        self.alpha = float(alpha)
        self.limit = float(limit)
        self.lookback = int(lookback)
        self._buf: list[float] = []

    def update(self, ret: float) -> float:
        self._buf.append(float(ret))
        if len(self._buf) > self.lookback:
            self._buf = self._buf[-self.lookback :]
        es = -cvar(self._buf, self.alpha)
        if es <= self.limit or es == 0.0:
            return 1.0
        return max(0.0, self.limit / max(1e-12, es))
