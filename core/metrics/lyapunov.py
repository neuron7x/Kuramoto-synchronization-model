"""Lyapunov-inspired metrics used by FHMC diagnostics."""

from __future__ import annotations

import numpy as np


def eoi_edge_of_instability(grad_norm_series: np.ndarray, win: int = 200) -> float:
    window = np.asarray(grad_norm_series[-win:], dtype=float)
    if window.size == 0:
        return 0.0
    normalised = (window - window.mean()) / (window.std() + 1e-8)
    if normalised.size < 2:
        return 0.0
    autocorr = np.corrcoef(normalised[:-1], normalised[1:])[0, 1]
    return float(autocorr)
