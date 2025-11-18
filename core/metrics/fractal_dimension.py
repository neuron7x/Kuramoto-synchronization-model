"""Fractal dimension estimators used by FHMC tests."""
from __future__ import annotations

import numpy as np


def box_counting_dim(signal: np.ndarray, eps_list: np.ndarray | None = None) -> float:
    """Estimate fractal dimension using box counting method.
    
    Args:
        signal: Input time series or signal array
        eps_list: Array of epsilon values for box sizes. If None, uses default
                  logarithmically spaced values from 10⁻³ to 10⁻¹
    
    Returns:
        Estimated fractal dimension (typically between 1 and 2 for time series)
    """
    values = np.asarray(signal, dtype=float)
    if eps_list is None:
        eps_list = np.logspace(-3, -1, 8)
    counts = []
    for eps in eps_list:
        bins = int(np.ceil((values.max() - values.min()) / (eps + 1e-8))) + 1
        hist, _ = np.histogram(values, bins=bins)
        counts.append((hist > 0).sum())
    X = -np.log(eps_list + 1e-12)
    Y = np.log(np.array(counts, dtype=float) + 1e-12)
    slope, _ = np.polyfit(X, Y, 1)
    return float(slope)
