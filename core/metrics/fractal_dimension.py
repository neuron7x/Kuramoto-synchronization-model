"""Fractal dimension estimators used by FHMC tests."""
from __future__ import annotations

import numpy as np


def box_counting_dim(signal: np.ndarray, eps_list: np.ndarray | None = None) -> float:
    """Estimate fractal dimension using the box-counting method.
    
    The box-counting dimension is computed by analyzing how the number of 
    boxes needed to cover the signal changes with box size. This provides
    a measure of the signal's fractal complexity.
    
    Parameters
    ----------
    signal : np.ndarray
        Input signal for which to compute the fractal dimension.
        Must be a finite numeric array with at least 2 distinct values.
    eps_list : np.ndarray | None, optional
        Array of epsilon (box size) values to use for the calculation.
        If None, defaults to 8 logarithmically-spaced values from 1e-3 to 1e-1.
    
    Returns
    -------
    float
        Estimated box-counting dimension. Returns 0.0 for invalid inputs.
        Typical values range from 1.0 (smooth) to 2.0 (space-filling).
    
    Raises
    ------
    ValueError
        If signal contains non-finite values or has fewer than 2 values.
    
    Notes
    -----
    The algorithm counts how many boxes of size eps are needed to cover the
    signal's range, then fits a log-log regression to estimate the scaling
    exponent (fractal dimension).
    """
    values = np.asarray(signal, dtype=float)
    
    # Validate input
    if values.size < 2:
        raise ValueError("signal must contain at least 2 values")
    if not np.all(np.isfinite(values)):
        raise ValueError("signal must contain only finite values")
    
    if eps_list is None:
        eps_list = np.logspace(-3, -1, 8)
    
    # Check for constant signal
    if np.ptp(values) < 1e-10:
        return 1.0  # Constant signal has dimension 1
    
    counts = []
    for eps in eps_list:
        bins = int(np.ceil((values.max() - values.min()) / (eps + 1e-8))) + 1
        hist, _ = np.histogram(values, bins=bins)
        counts.append((hist > 0).sum())
    X = -np.log(eps_list + 1e-12)
    Y = np.log(np.array(counts, dtype=float) + 1e-12)
    slope, _ = np.polyfit(X, Y, 1)
    return float(slope)
