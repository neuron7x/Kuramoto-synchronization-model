"""Detrended fluctuation analysis utilities.

This module implements Detrended Fluctuation Analysis (DFA) for estimating
the long-range correlation properties of time series. The DFA scaling
exponent α characterizes the self-affinity of the signal:

- α ≈ 0.5: uncorrelated (white noise)
- α < 0.5: anti-correlated
- α > 0.5: long-range positive correlations
- α ≈ 1.0: 1/f noise (pink noise)
- α > 1.0: non-stationary, unbounded

References:
    Peng, C. K., et al. (1994). Mosaic organization of DNA nucleotides.
    Physical Review E, 49(2), 1685.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from core.utils.numeric_constants import LOG_SAFE_MIN, VARIANCE_SAFE_MIN


def dfa_alpha(
    x: Iterable[float],
    min_win: int = 50,
    max_win: int = 2000,
    n_win: int = 12,
) -> float:
    """Return the DFA scaling exponent of ``x``.

    The implementation follows the standard log–log regression between the
    window scale and the mean fluctuation magnitude.  Edge cases with
    insufficient data gracefully fallback to zero so downstream controllers can
    decide how to react.

    Args:
        x: Input time series as a 1-D iterable of floats.
        min_win: Minimum window size for fluctuation analysis.
        max_win: Maximum window size for fluctuation analysis.
        n_win: Number of window sizes to use in the log-spaced range.

    Returns:
        DFA scaling exponent α. Returns 0.0 if insufficient data or
        computation fails.

    Raises:
        ValueError: If input is not 1-dimensional.
    """

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("dfa_alpha expects a 1-D sequence")
    if series.size == 0:
        return 0.0

    # Filter non-finite values
    finite_mask = np.isfinite(series)
    if not finite_mask.all():
        series = series[finite_mask]
    if series.size == 0:
        return 0.0

    # Compute integrated profile (cumulative sum of deviations from mean)
    series = series - float(np.mean(series))
    profile = np.cumsum(series)

    # Generate logarithmically spaced window sizes
    effective_min = max(min_win, 4)
    effective_max = min(max_win, profile.size // 2)
    if effective_max <= effective_min:
        return 0.0

    wins = np.unique(
        np.logspace(
            np.log10(effective_min),
            np.log10(effective_max),
            n_win,
            dtype=int,
        )
    )

    flucts: list[float] = []
    scales: list[int] = []

    for window in wins:
        if window < 4 or window >= profile.size:
            continue
        n_segments = profile.size // window
        if n_segments < 2:
            continue
        segments = profile[: n_segments * window].reshape(n_segments, window)
        t = np.arange(window, dtype=float)
        rms_values: list[float] = []
        for segment in segments:
            # Use numerically stable least squares for detrending
            coeffs = np.polyfit(t, segment, deg=1)
            trend = np.polyval(coeffs, t)
            residual = segment - trend
            mse = float(np.mean(residual**2))
            # Ensure non-negative value before sqrt
            rms_values.append(float(np.sqrt(max(mse, 0.0))))

        mean_rms = float(np.mean(rms_values))
        # Only include valid fluctuation values
        if mean_rms > VARIANCE_SAFE_MIN:
            flucts.append(mean_rms)
            scales.append(window)

    # Need at least 2 points for regression
    if len(flucts) < 2:
        return 0.0

    # Use numerically stable log computation
    scales_arr = np.asarray(scales, dtype=float)
    flucts_arr = np.asarray(flucts, dtype=float)

    # Ensure all values are valid for log computation
    scales_arr = np.maximum(scales_arr, LOG_SAFE_MIN)
    flucts_arr = np.maximum(flucts_arr, LOG_SAFE_MIN)

    lw = np.log(scales_arr)
    lF = np.log(flucts_arr)

    # Check for constant values (would cause polyfit issues)
    if np.std(lw) < VARIANCE_SAFE_MIN or np.std(lF) < VARIANCE_SAFE_MIN:
        return 0.0

    slope, _ = np.polyfit(lw, lF, deg=1)

    # Validate result is finite
    if not np.isfinite(slope):
        return 0.0

    return float(slope)
