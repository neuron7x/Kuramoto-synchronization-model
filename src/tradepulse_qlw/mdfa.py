"""Multifractal Detrended Fluctuation Analysis (MF-DFA) for Hurst exponent estimation."""

from __future__ import annotations

import numpy as np


def hurst_mfdfa(ts: np.ndarray, q: float = 2.0, scales: np.ndarray | None = None) -> float:
    """
    Estimate Hurst exponent via MF-DFA.

    Parameters
    ----------
    ts : np.ndarray
        Time series data
    q : float
        Moment order (default 2.0 for standard DFA)
    scales : np.ndarray, optional
        Window scales to use. If None, uses logarithmic spacing

    Returns
    -------
    float
        Hurst exponent H in (0, 1)
    """
    ts = np.asarray(ts, dtype=float)
    n = len(ts)

    if scales is None:
        # Logarithmic scale spacing
        min_scale = max(4, int(n / 20))
        max_scale = int(n / 4)
        scales = np.unique(np.logspace(np.log10(min_scale), np.log10(max_scale), 12).astype(int))

    # Cumulative sum (profile)
    mean = np.mean(ts)
    profile = np.cumsum(ts - mean)

    F_q = []
    for s in scales:
        # Number of segments
        num_segments = n // s
        if num_segments < 1:
            continue

        # Fit polynomial trends and compute fluctuations
        fluct = []
        for v in range(num_segments):
            segment = profile[v * s : (v + 1) * s]
            x = np.arange(s)
            # Linear detrending
            poly_coef = np.polyfit(x, segment, 1)
            trend = np.polyval(poly_coef, x)
            detrended = segment - trend
            fluct.append(np.mean(detrended**2))

        if not fluct:
            continue

        # Compute q-th order fluctuation function
        fluct = np.array(fluct)
        if q != 0:
            F_q_s = np.mean(fluct ** (q / 2.0)) ** (1.0 / q)
        else:
            F_q_s = np.exp(0.5 * np.mean(np.log(fluct + 1e-12)))

        F_q.append(F_q_s)

    if len(F_q) < 2:
        # Fallback for insufficient data
        return 0.5

    # Fit log-log relationship: log(F_q) ~ H * log(scales)
    log_scales = np.log(scales[: len(F_q)])
    log_F_q = np.log(np.array(F_q) + 1e-12)

    # Linear regression
    H = np.polyfit(log_scales, log_F_q, 1)[0]

    # Clamp to valid range
    H = float(np.clip(H, 0.01, 0.99))

    return H


def gamma_from_h(H: float, gamma_lo: float, gamma_hi: float) -> float:
    """
    Map Hurst exponent H to damping coefficient gamma.

    Higher persistence (H closer to 1) → lower damping
    Lower persistence (H closer to 0) → higher damping

    Parameters
    ----------
    H : float
        Hurst exponent
    gamma_lo : float
        Minimum damping coefficient
    gamma_hi : float
        Maximum damping coefficient

    Returns
    -------
    float
        Damping coefficient gamma
    """
    return gamma_lo + (gamma_hi - gamma_lo) * (1 - H)
