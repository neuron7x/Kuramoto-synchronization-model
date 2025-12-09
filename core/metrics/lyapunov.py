"""Lyapunov-inspired metrics used by FHMC diagnostics.

This module implements edge-of-instability (EOI) metrics based on gradient dynamics,
inspired by the concept of "edge of chaos" in dynamical systems and neural networks.

The EOI metric quantifies temporal correlations in gradient magnitudes, which can
indicate whether a learning system is in a stable, chaotic, or critical regime.

References
----------
.. [1] Langton, C. G. (1990). "Computation at the edge of chaos: Phase transitions
       and emergent computation." Physica D, 42(1-3), 12-37.
.. [2] Shwartz-Ziv, R., & Tishby, N. (2017). "Opening the black box of deep neural
       networks via information." arXiv:1703.00810.
"""

from __future__ import annotations

import numpy as np

from core.utils.numeric_constants import DIV_SAFE_MIN


def eoi_edge_of_instability(grad_norm_series: np.ndarray, win: int = 200) -> float:
    """Compute edge-of-instability metric from gradient norm series.
    
    The EOI metric measures the lag-1 autocorrelation of normalized gradient norms,
    providing insight into the temporal dynamics of the learning process:
    
    .. math::
    
        z_t = \frac{||\nabla_t|| - \mu}{\sigma + \epsilon}
        
        EOI = \text{corr}(z_{1:T-1}, z_{2:T})
    
    Parameters
    ----------
    grad_norm_series : np.ndarray
        Time series of gradient norms (L2 norms of gradient vectors)
    win : int, optional
        Window size for computing autocorrelation, by default 200
        Uses the last `win` values from the series
    
    Returns
    -------
    float
        Lag-1 autocorrelation of normalized gradient norms in [-1, 1]
        - EOI ≈ 0: Uncorrelated (white noise regime, potentially good for exploration)
        - EOI > 0: Positive correlation (momentum-like behavior)
        - EOI < 0: Negative correlation (oscillatory behavior)
        - |EOI| ≈ 1: Strong temporal structure (may indicate instability)
    
    Notes
    -----
    Returns 0.0 for empty windows or insufficient data (< 2 points).
    The "edge of chaos" hypothesis suggests that optimal learning occurs when
    the system is neither too stable (EOI → 1) nor too chaotic (random EOI ≈ 0),
    but at a critical point between order and disorder.
    """
    window = np.asarray(grad_norm_series[-win:], dtype=float)
    if window.size == 0:
        return 0.0
    
    # Normalize to zero mean and unit variance
    normalised = (window - window.mean()) / (window.std() + DIV_SAFE_MIN)
    
    if normalised.size < 2:
        return 0.0
    
    # Compute lag-1 autocorrelation
    autocorr = np.corrcoef(normalised[:-1], normalised[1:])[0, 1]
    
    # Handle potential NaN from corrcoef (e.g., constant series)
    if not np.isfinite(autocorr):
        return 0.0
    
    return float(autocorr)
