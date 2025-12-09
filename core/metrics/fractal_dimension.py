"""Fractal dimension estimators used by FHMC tests.

This module implements box-counting dimension estimation for characterizing
the fractal properties of time series data.

References
----------
.. [1] Mandelbrot, B. B. (1982). The Fractal Geometry of Nature.
"""

from __future__ import annotations

import numpy as np

from core.utils.numeric_constants import DIV_SAFE_MIN, LOG_SAFE_MIN


def box_counting_dim(signal: np.ndarray, eps_list: np.ndarray | None = None) -> float:
    """Estimate the box-counting (fractal) dimension of a signal.
    
    The box-counting dimension quantifies how the "detail" in a signal changes
    with the scale at which it is measured. It's computed by counting the number
    of boxes needed to cover the signal at different scales.
    
    .. math::
    
        D = \lim_{\epsilon \to 0} \frac{\log N(\epsilon)}{\log(1/\epsilon)}
    
    where N(ε) is the number of boxes of size ε needed to cover the signal.
    
    Parameters
    ----------
    signal : np.ndarray
        Input signal as 1-D array
    eps_list : np.ndarray, optional
        Array of box sizes (epsilon values) to use. If None, uses logarithmically
        spaced values from 0.001 to 0.1.
    
    Returns
    -------
    float
        Estimated box-counting dimension (typically between 1 and 2 for time series)
    
    Notes
    -----
    For a smooth curve: D ≈ 1
    For a space-filling curve: D ≈ 2
    For typical financial time series: D ≈ 1.5
    """
    values = np.asarray(signal, dtype=float)
    if eps_list is None:
        eps_list = np.logspace(-3, -1, 8)
    counts = []
    for eps in eps_list:
        bins = int(np.ceil((values.max() - values.min()) / (eps + DIV_SAFE_MIN))) + 1
        hist, _ = np.histogram(values, bins=bins)
        counts.append((hist > 0).sum())
    X = -np.log(eps_list + LOG_SAFE_MIN)
    Y = np.log(np.array(counts, dtype=float) + LOG_SAFE_MIN)
    slope, _ = np.polyfit(X, Y, 1)
    return float(slope)
