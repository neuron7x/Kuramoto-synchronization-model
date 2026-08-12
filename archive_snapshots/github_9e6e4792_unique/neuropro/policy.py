"""Sizing and gating policy for SABRE CAL."""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np


class Policy:
    def __init__(
        self,
        max_pos: float = 1.0,
        kelly_shrink: float = 0.2,
        risk_gamma: float = 10.0,
        cvar_alpha: float = 0.95,
        cvar_window: int = 1000,
    ) -> None:
        self.max_pos = float(max_pos)
        self.kelly_shrink = float(kelly_shrink)
        self.risk_gamma = float(risk_gamma)
        self.cvar_alpha = float(cvar_alpha)
        self.cvar_window = int(cvar_window)

    def size_from_interval(self, m: float, low: float, high: float) -> float:
        width = max(1e-9, high - low)
        scale = min(1.0, abs(m) / width)
        return float(np.clip(scale, 0.0, 1.0) * self.max_pos * np.sign(m))

    def _dyn_cap(self, r_hist: Optional[Iterable[float]]) -> float:
        if r_hist is None:
            return self.max_pos
        hist = list(r_hist)
        if not hist:
            return self.max_pos
        tail_window = min(len(hist), self.cvar_window)
        arr = np.asarray(hist[-tail_window:])
        quantile = np.quantile(arr, 1.0 - self.cvar_alpha)
        tail = arr[arr <= quantile]
        cvar = abs(tail.mean()) if len(tail) > 0 else 0.0
        scale = float(np.exp(-self.risk_gamma * cvar))
        return float(np.clip(scale, 0.1, 1.0) * self.max_pos)

    def decide(
        self,
        low_c: float,
        mid: float,
        high_c: float,
        costs: float,
        buffer_frac: float,
        r_hist: Optional[Iterable[float]],
    ) -> float:
        thresh = float(costs + (buffer_frac or 0.0))
        if (low_c - thresh) > 0 and mid > 0:
            base = self.size_from_interval(mid, low_c, high_c)
            cap = self._dyn_cap(r_hist)
            return float(np.sign(base) * min(abs(base), cap))
        if (high_c + thresh) < 0 and mid < 0:
            base = self.size_from_interval(mid, low_c, high_c)
            cap = self._dyn_cap(r_hist)
            return float(np.sign(base) * min(abs(base), cap))
        return 0.0
