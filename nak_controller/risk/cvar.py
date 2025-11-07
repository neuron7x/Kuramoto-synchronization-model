"""Risk metric helpers for validation scripts."""
from __future__ import annotations

from typing import Iterable

import numpy as np


def conditional_value_at_risk(samples: Iterable[float], alpha: float = 0.95) -> float:
    """Compute the CVaR of *samples* at confidence level *alpha*."""

    values = np.sort(np.asarray(list(samples), dtype=float))
    if values.size == 0:
        raise ValueError("samples must not be empty")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    index = int(np.floor((1 - alpha) * values.size))
    index = min(max(index, 0), values.size - 1)
    tail = values[: index + 1]
    return float(np.mean(tail))


__all__ = ["conditional_value_at_risk"]
