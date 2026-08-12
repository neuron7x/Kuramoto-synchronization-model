# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Conditional Value-at-Risk utilities."""

from __future__ import annotations

from typing import Iterable, List

import numpy as np


def cvar(returns: Iterable[float], alpha: float = 0.95) -> float:
    r = np.asarray(list(returns), dtype=float)
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    if tail.size == 0:
        return 0.0
    return float(tail.mean())


class CVARGate:
    """CVaR-based risk limiter."""

    def __init__(self, alpha: float = 0.95, limit: float = 0.03, lookback: int = 50) -> None:
        self.alpha = alpha
        self.limit = limit
        self.lookback = lookback
        self.buffer: List[float] = []

    def update(self, ret: float) -> float:
        self.buffer.append(ret)
        if len(self.buffer) > self.lookback:
            self.buffer = self.buffer[-self.lookback :]
        es = -cvar(self.buffer, self.alpha)
        if es <= self.limit or es == 0.0:
            return 1.0
        return max(0.0, self.limit / es)
