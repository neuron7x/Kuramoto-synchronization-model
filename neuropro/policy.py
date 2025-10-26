"""Sizing and gating policy for SABRE CAL."""

from __future__ import annotations

import numpy as np


class Policy:
    def __init__(self, max_pos: float = 1.0, kelly_shrink: float = 0.2) -> None:
        self.max_pos = max_pos
        self.kelly_shrink = kelly_shrink

    def size_from_interval(self, m: float, low: float, high: float) -> float:
        width = max(1e-9, high - low)
        scale = min(1.0, abs(m) / width)
        return float(np.clip(scale, 0.0, 1.0) * self.max_pos * np.sign(m))

    def decide(self, low_c: float, mid: float, high_c: float, costs: float) -> float:
        if (low_c - costs) > 0 and mid > 0:
            return self.size_from_interval(mid, low_c, high_c)
        if (high_c + costs) < 0 and mid < 0:
            return self.size_from_interval(mid, low_c, high_c)
        return 0.0
