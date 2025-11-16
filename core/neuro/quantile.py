"""Streaming quantile estimation with deterministic insertion.

This module provides a simple, deterministic streaming quantile estimator
based on incremental sorted insertion. Unlike approximate algorithms like
P² or t-digest, this implementation maintains exact quantiles by storing
all observations in sorted order.

Key Components:
    P2Quantile: Streaming quantile tracker with O(n log n) insertion

While this approach has higher memory requirements (O(n)) compared to
approximate methods, it provides exact quantile values without tuning
parameters or approximation errors. This makes it suitable for scenarios
where exact quantiles are required and the data volume is manageable.

The implementation uses Python's bisect module for efficient binary search
insertion, minimizing the constant factors in the O(n log n) complexity.

Example:
    >>> tracker = P2Quantile(0.95)  # Track 95th percentile
    >>> for value in data_stream:
    ...     current_q95 = tracker.update(value)
    >>> print(f"Final 95th percentile: {tracker.quantile:.3f}")

Note:
    For very large streams, consider approximate alternatives like
    t-digest or P² algorithm with bounded memory.
"""
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
