"""Lyapunov-inspired metrics used by FHMC diagnostics."""
from __future__ import annotations

import numpy as np


def eoi_edge_of_instability(grad_norm_series: np.ndarray, win: int = 200) -> float:
    """Calculate Edge of Instability metric from gradient norm series.
    
    Measures autocorrelation in normalized gradient norms to detect chaotic
    behavior or instability in the optimization process.
    
    Args:
        grad_norm_series: Array of gradient norms over time
        win: Window size for recent history analysis (default: 200)
    
    Returns:
        Autocorrelation coefficient [-1, 1]. Values near 0 indicate stability,
        values near 1 suggest high persistence (potential instability)
    """
    window = np.asarray(grad_norm_series[-win:], dtype=float)
    if window.size == 0:
        return 0.0
    normalised = (window - window.mean()) / (window.std() + 1e-8)
    if normalised.size < 2:
        return 0.0
    autocorr = np.corrcoef(normalised[:-1], normalised[1:])[0, 1]
    return float(autocorr)
