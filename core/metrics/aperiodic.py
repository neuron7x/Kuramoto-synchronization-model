"""Aperiodic spectral slope estimators."""

from __future__ import annotations

from typing import Iterable

import numpy as np
from scipy.signal import welch


def aperiodic_slope(
    x: Iterable[float],
    *,
    fs: float,
    f_lo: float = 0.5,
    f_hi: float = 40.0,
) -> float:
    """Estimate the 1/f slope via log–log regression of the PSD."""

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("aperiodic_slope expects a 1-D sequence")
    if series.size < 4:
        return 0.0
    if fs <= 0:
        raise ValueError("fs must be positive")

    nperseg = int(min(series.size, max(int(fs * 4), 8)))
    freqs, psd = welch(series, fs=fs, nperseg=nperseg)
    mask = (freqs >= f_lo) & (freqs <= f_hi) & (psd > 0)
    if mask.sum() < 4:
        return 0.0

    xf = np.log10(freqs[mask] + 1e-12)
    yf = np.log10(psd[mask] + 1e-24)
    slope, _ = np.polyfit(xf, yf, deg=1)
    return float(slope)
