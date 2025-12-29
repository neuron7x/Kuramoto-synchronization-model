"""Detrended fluctuation analysis utilities for long-range correlation detection.

This module implements Detrended Fluctuation Analysis (DFA) for estimating
the long-range correlation properties and self-affinity of time series.

Mathematical Foundation:
    DFA quantifies the scaling behavior of fluctuations in a non-stationary
    time series. For a time series x(t), the method:

    1. Computes the integrated profile (cumulative sum):
       y(t) = ∑ᵢ₌₁ᵗ [x(i) - x̄]

    2. Divides y(t) into non-overlapping segments of length s

    3. For each segment, fits a polynomial trend and computes RMS fluctuation:
       F²(s) = (1/N) ∑ₖ [y(k) - yₜᵣₑₙ(k)]²

    4. Analyzes scaling behavior:
       F(s) ~ s^α

       where α is the DFA scaling exponent.

The DFA scaling exponent α characterizes the self-affinity of the signal:

Scaling Exponent Interpretation:
    α ≈ 0.5: Uncorrelated (white noise) - random walk
    α < 0.5: Anti-correlated (mean-reverting) - tendency to reverse
    α > 0.5: Long-range positive correlations (persistent) - trends
    α ≈ 1.0: 1/f noise (pink noise) - scale-invariant
    α > 1.0: Non-stationary, unbounded (super-diffusive)
    α ≈ 1.5: Brownian motion (random walk of random walk)

Financial Interpretation:
    - α > 0.5: Trending market (momentum strategies favorable)
    - α ≈ 0.5: Random walk (efficient market hypothesis)
    - α < 0.5: Mean-reverting (contrarian strategies favorable)

References:
    - Peng, C. K., et al. (1994). Mosaic organization of DNA nucleotides.
      Physical Review E, 49(2), 1685.
    - Kantelhardt, J. W., et al. (2002). Multifractal detrended fluctuation
      analysis of nonstationary time series. Physica A, 316(1-4), 87-114.
    - Hurst, H. E. (1951). Long-term storage capacity of reservoirs.
      Transactions of the American Society of Civil Engineers, 116, 770-808.
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
    """Return the DFA scaling exponent α of time series x.

    Mathematical Algorithm:
        1. Mean-center the signal:
           x̃(t) = x(t) - x̄

        2. Compute integrated profile (cumulative sum):
           y(t) = ∑ᵢ₌₁ᵗ x̃(i)

        3. For each window size s ∈ [s_min, s_max]:
           a. Divide y(t) into non-overlapping segments of length s
           b. For each segment, fit linear trend via least squares
           c. Compute RMS fluctuation of detrended segment:
              F(s) = √[(1/N_s) ∑ [y(t) - y_trend(t)]²]

        4. Perform log-log regression to estimate scaling exponent:
           log F(s) ~ α · log s
           
           where α is extracted as the slope.

    Statistical Properties:
        - α = 0.5 ± 0.05 for white noise (95% confidence)
        - α = 1.0 ± 0.05 for 1/f noise (pink noise)
        - Confidence intervals scale as ~ 1/√(n_win)

    The implementation follows the standard log–log regression between the
    window scale and the mean fluctuation magnitude. Edge cases with
    insufficient data gracefully fallback to zero so downstream controllers can
    decide how to react.

    Args:
        x: Input time series as a 1-D iterable of floats.
        min_win: Minimum window size for fluctuation analysis (default: 50).
            Must be ≥ 4 for meaningful linear detrending.
        max_win: Maximum window size for fluctuation analysis (default: 2000).
            Typically limited to N/2 where N = len(x) to ensure ≥ 2 segments.
        n_win: Number of window sizes to use in the log-spaced range (default: 12).
            More windows → better α estimation but higher computational cost.

    Returns:
        DFA scaling exponent α ∈ ℝ. Typically α ∈ [0, 2] for physical signals.
        Returns 0.0 if insufficient data, degenerate input, or computation fails.

    Raises:
        ValueError: If input is not 1-dimensional.

    Numerical Stability:
        - Non-finite values filtered before processing
        - Mean-centering prevents drift in cumsum
        - Least-squares detrending numerically stable via np.polyfit
        - Log-safe thresholding: ensures no log(0) or log(negative)
        - Variance-safe thresholding: prevents division by zero in std()

    Complexity:
        Time: O(N·W) where N = len(x), W = number of windows
        Space: O(N) for integrated profile

    Examples:
        >>> # White noise (α ≈ 0.5)
        >>> white_noise = np.random.randn(10000)
        >>> alpha = dfa_alpha(white_noise)
        >>> assert 0.4 < alpha < 0.6

        >>> # Brownian motion (α ≈ 1.5)
        >>> brownian = np.cumsum(np.random.randn(10000))
        >>> alpha = dfa_alpha(brownian)
        >>> assert 1.4 < alpha < 1.6

        >>> # 1/f noise (α ≈ 1.0)
        >>> # (requires specialized generator, not shown)

    References:
        - Peng, C. K., et al. (1994). Mosaic organization of DNA nucleotides.
          Physical Review E, 49(2), 1685-1689.
        - Kantelhardt, J. W., et al. (2001). Detecting long-range correlations
          with detrended fluctuation analysis. Physica A, 295(3-4), 441-454.
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
