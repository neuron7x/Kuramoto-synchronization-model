# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Entropy helpers used by the VLPO-inspired filters."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy.stats import entropy


def compute_shannon_entropy(signal: ArrayLike, *, base: float = 2.0) -> float:
    """Compute the Shannon entropy of a one-dimensional signal.

    Zero-length signals return ``0.0`` to keep downstream scaling predictable.
    Probabilities are normalised using the absolute values of ``signal`` which
    ensures negative telemetry values do not cancel each other out.
    """

    arr = np.asarray(signal, dtype=float)
    if arr.size == 0:
        return 0.0

    magnitudes = np.abs(arr)
    normaliser = magnitudes.sum()
    if normaliser == 0:
        return 0.0

    probabilities = magnitudes / normaliser
    probabilities = probabilities[probabilities > 0]
    if probabilities.size == 0:
        return 0.0

    return float(entropy(probabilities, base=base))


def downscale_low_entropy(
    signal: ArrayLike,
    *,
    threshold: float = 2.5,
    scale_factor: float = 0.5,
) -> np.ndarray:
    """Downscale signals whose Shannon entropy falls below ``threshold``.

    The function returns a copy of ``signal`` scaled by ``scale_factor`` when
    the entropy is low, otherwise the original signal is returned unchanged.
    """

    arr = np.asarray(signal, dtype=float)
    entropy_value = compute_shannon_entropy(arr)
    if entropy_value < threshold:
        return arr * float(scale_factor)
    return arr


__all__ = ["compute_shannon_entropy", "downscale_low_entropy"]
