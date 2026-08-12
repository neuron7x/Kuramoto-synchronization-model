# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np


def es_alpha(returns: np.ndarray, alpha: float) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1.0 - alpha)
    tail = r[r <= q]
    return float(-np.mean(tail)) if tail.size > 0 else 0.0


class CVARGate:
    """Rolling expected shortfall gate returning allocation scale in [0, 1]."""

    def __init__(self, alpha: float = 0.95, limit: float = 0.03, lookback: int = 50):
        self.alpha = float(alpha)
        self.limit = float(limit)
        self.lookback = int(lookback)
        self.buf: list[float] = []

    def update(self, ret: float) -> float:
        self.buf.append(float(ret))
        if len(self.buf) > self.lookback:
            self.buf = self.buf[-self.lookback :]
        es = es_alpha(np.array(self.buf, dtype=float), self.alpha)
        if es <= self.limit or es == 0.0:
            return 1.0
        return float(np.clip(self.limit / es, 0.0, 1.0))
