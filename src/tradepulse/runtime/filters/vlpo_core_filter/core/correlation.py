"""Correlation utilities for VLPO denoising."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy.stats import pearsonr


def compute_pearson_correlation(signal: ArrayLike, target: ArrayLike) -> float:
    """Return the Pearson correlation between ``signal`` and ``target``.

    Any mismatch in shape or a lack of variance in the inputs yields ``0.0``
    which effectively disables the correlation-driven forgetting rule.
    """

    x = np.asarray(signal, dtype=float)
    y = np.asarray(target, dtype=float)
    if x.size == 0 or y.size == 0 or x.size != y.size:
        return 0.0

    # ``pearsonr`` raises warnings when the standard deviation is zero; guard by
    # performing the variance check explicitly which mirrors the SciPy logic.
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0

    correlation, _ = pearsonr(x, y)
    if np.isnan(correlation):
        return 0.0
    return float(correlation)


def forget_low_correlation(
    signal: ArrayLike,
    target: ArrayLike,
    *,
    threshold: float = 0.3,
) -> np.ndarray:
    """Zero-out ``signal`` when the correlation to ``target`` is too weak."""

    x = np.asarray(signal, dtype=float)
    correlation = compute_pearson_correlation(x, target)
    if correlation < threshold:
        return np.zeros_like(x)
    return x


__all__ = ["compute_pearson_correlation", "forget_low_correlation"]
