"""Aperiodic spectral slope estimators.

This module implements 1/f^β slope estimation from power spectral density,
which characterizes the scale-free temporal structure of neural and market signals.

References
----------
.. [1] Voytek, B., et al. (2015). "Age-Related Changes in 1/f Neural
       Electrophysiological Noise." Journal of Neuroscience, 35(38), 13257-13265.
.. [2] He, B. J. (2014). "Scale-free brain activity: past, present, and future."
       Trends in Cognitive Sciences, 18(9), 480-487.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from scipy.signal import welch

from core.utils.numeric_constants import LOG_SAFE_MIN

# Welch periodogram parameters for reliable PSD estimation
_WELCH_DURATION_FACTOR = 4  # seconds of data per segment for reliable spectral estimation
_WELCH_MIN_SEGMENT_SIZE = 8  # minimum samples per segment to avoid excessive variance

# Safe minimums for log-log regression to avoid log(0)
_PSD_LOG_SAFE_MIN = 1e-24  # very small for PSD which can have extremely low values


def aperiodic_slope(
    x: Iterable[float],
    *,
    fs: float,
    f_lo: float = 0.5,
    f_hi: float = 40.0,
) -> float:
    """Estimate the 1/f^β slope via log-log regression of the power spectral density.
    
    The aperiodic (1/f) component of the PSD characterizes scale-free temporal
    structure. The slope β in PSD ~ 1/f^β indicates the color of noise:
    
    .. math::
    
        \log_{10} P(f) = c + m \log_{10} f
    
    where m is the slope (related to β by m = -β).
    
    Parameters
    ----------
    x : Iterable[float]
        Input time series as 1-D sequence
    fs : float
        Sampling frequency in Hz
    f_lo : float, optional
        Lower frequency bound for regression, by default 0.5 Hz
    f_hi : float, optional
        Upper frequency bound for regression, by default 40.0 Hz
    
    Returns
    -------
    float
        Estimated slope m (note: β = -m for 1/f^β noise)
        - m ≈ 0: white noise (flat spectrum)
        - m ≈ -1: pink noise (1/f)
        - m ≈ -2: brown noise (1/f²)
    
    Raises
    ------
    ValueError
        If input is not 1-dimensional or fs is not positive
    
    Notes
    -----
    Returns 0.0 for short series (< 4 points) or insufficient frequency points.
    Uses Welch's method for robust PSD estimation with overlapping segments.
    """

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("aperiodic_slope expects a 1-D sequence")
    if series.size < 4:
        return 0.0
    if fs <= 0:
        raise ValueError("fs must be positive")

    # Compute Welch periodogram with appropriate segment size
    nperseg = int(min(series.size, max(int(fs * _WELCH_DURATION_FACTOR), _WELCH_MIN_SEGMENT_SIZE)))
    freqs, psd = welch(series, fs=fs, nperseg=nperseg)
    
    # Select frequency range and filter valid PSD values
    mask = (freqs >= f_lo) & (freqs <= f_hi) & (psd > 0)
    if mask.sum() < 4:
        return 0.0

    # Log-log regression with safe minimums to avoid log(0)
    xf = np.log10(freqs[mask] + LOG_SAFE_MIN)
    yf = np.log10(psd[mask] + _PSD_LOG_SAFE_MIN)
    slope, _ = np.polyfit(xf, yf, deg=1)
    return float(slope)
