"""Risk utility helpers for the NaK controller."""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def conditional_value_at_risk(
    samples: Sequence[float] | Iterable[float], alpha: float = 0.95
) -> float:
    """Compute the Conditional Value at Risk (CVaR) at level ``alpha``.

    Parameters
    ----------
    samples:
        Loss samples. Positive numbers indicate a loss.
    alpha:
        Confidence level. Must lie in (0, 1).
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be within (0, 1)")

    arr = np.fromiter((float(s) for s in samples), dtype=float)
    if arr.size == 0:
        raise ValueError("samples must be non-empty")

    quantile = np.quantile(arr, alpha)
    tail = arr[arr >= quantile]
    if tail.size == 0:
        return float(quantile)
    return float(np.mean(tail))


__all__ = ["conditional_value_at_risk"]
