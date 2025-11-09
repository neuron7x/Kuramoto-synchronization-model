from __future__ import annotations

import bisect
import math


class P2Quantile:
    """Deterministic streaming quantile via incremental insertion."""

    __slots__ = ("p", "_values")

    def __init__(self, q: float):
        if not (0.0 < q < 1.0):
            msg = "Quantile must be within the open interval (0, 1)"
            raise ValueError(msg)
        self.p = float(q)
        self._values: list[float] = []

    def update(self, x: float) -> float:
        bisect.insort(self._values, float(x))
        return self.quantile

    @property
    def quantile(self) -> float:
        if not self._values:
            return float("nan")
        n = len(self._values)
        pos = (n - 1) * self.p
        lower = math.floor(pos)
        upper = math.ceil(pos)
        if lower == upper:
            return float(self._values[lower])
        frac = pos - lower
        return float((1.0 - frac) * self._values[lower] + frac * self._values[upper])
