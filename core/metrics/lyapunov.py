"""Lyapunov-inspired metrics used by FHMC diagnostics."""
from __future__ import annotations

import numpy as np


def eoi_edge_of_instability(grad_norm_series: np.ndarray, win: int = 200) -> float:
    """Compute the Edge of Instability (EOI) metric from gradient norms.

    The EOI metric quantifies system stability by measuring autocorrelation
    in gradient norm patterns. High positive autocorrelation suggests the
    system is approaching an instability boundary, while low or negative
    values indicate stable behavior.

    Parameters
    ----------
    grad_norm_series : np.ndarray
        Time series of gradient norm magnitudes from the optimization process.
        Should contain at least `win` finite values for meaningful results.
    win : int, optional
        Rolling window size for computing the metric. Defaults to 200.
        Must be positive and at least 2.

    Returns
    -------
    float
        Autocorrelation coefficient (lag-1) of the normalized gradient norms.
        Returns 0.0 for invalid inputs or insufficient data.
        Range: [-1.0, 1.0], with values near 1.0 indicating instability.

    Raises
    ------
    ValueError
        If win is less than 2 or grad_norm_series contains non-finite values.

    Notes
    -----
    This metric is inspired by Lyapunov exponent analysis and is used in
    FHMC (Fractal Hamiltonian Monte Carlo) diagnostics to detect when the
    sampler is near chaos boundaries.

    References
    ----------
    - Lyapunov exponent theory for dynamical systems
    - Edge of Chaos hypothesis in neural network training
    """
    if win < 2:
        raise ValueError("window size must be at least 2")

    window = np.asarray(grad_norm_series[-win:], dtype=float)

    if window.size == 0:
        return 0.0

    # Validate input contains finite values
    if not np.all(np.isfinite(window)):
        raise ValueError("grad_norm_series must contain only finite values")

    # Check for constant or near-constant series
    std = window.std()
    if std < 1e-10:
        return 0.0

    normalised = (window - window.mean()) / (std + 1e-8)
    if normalised.size < 2:
        return 0.0

    # Compute lag-1 autocorrelation
    try:
        autocorr = np.corrcoef(normalised[:-1], normalised[1:])[0, 1]
        return float(autocorr) if np.isfinite(autocorr) else 0.0
    except (ValueError, RuntimeWarning):
        # Handle edge cases where correlation cannot be computed
        return 0.0
