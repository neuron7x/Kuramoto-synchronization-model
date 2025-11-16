"""Detrended fluctuation analysis utilities."""
from __future__ import annotations

from typing import Iterable

import numpy as np


def dfa_alpha(
    x: Iterable[float],
    min_win: int = 50,
    max_win: int = 2000,
    n_win: int = 12,
) -> float:
    """Return the DFA (Detrended Fluctuation Analysis) scaling exponent of ``x``.

    The implementation follows the standard log–log regression between the
    window scale and the mean fluctuation magnitude. The DFA exponent
    characterizes the long-range correlations in the time series:
    - α ≈ 0.5: uncorrelated (white noise)
    - 0.5 < α < 1.0: persistent (positive correlations)
    - α ≈ 1.0: 1/f noise (pink noise)
    - α > 1.0: non-stationary
    
    Parameters
    ----------
    x : Iterable[float]
        Input time series. Must be a 1-D sequence of finite numeric values
        with at least 4 data points.
    min_win : int, optional
        Minimum window size for DFA analysis. Default is 50.
        Must be at least 4.
    max_win : int, optional
        Maximum window size for DFA analysis. Default is 2000.
        Must be greater than min_win.
    n_win : int, optional
        Number of logarithmically-spaced window sizes to test. Default is 12.
        Must be at least 2.
    
    Returns
    -------
    float
        DFA scaling exponent (alpha). Returns 0.0 for edge cases with
        insufficient data so downstream controllers can decide how to react.
        Typical values range from 0.0 to 2.0.
    
    Raises
    ------
    ValueError
        If input is not 1-D, contains non-finite values, or parameters
        are out of valid ranges.
        
    Notes
    -----
    DFA is robust to non-stationarities in the mean and can detect long-range
    correlations in the presence of trends. It's commonly used in financial
    time series analysis and biomedical signal processing.
    
    References
    ----------
    Peng, C.-K., et al. (1994). "Mosaic organization of DNA nucleotides."
    Physical Review E, 49(2), 1685.
    """
    # Validate parameters
    if min_win < 4:
        raise ValueError("min_win must be at least 4")
    if max_win <= min_win:
        raise ValueError("max_win must be greater than min_win")
    if n_win < 2:
        raise ValueError("n_win must be at least 2")

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("dfa_alpha expects a 1-D sequence")
    if series.size == 0:
        return 0.0
    if series.size < 4:
        raise ValueError("input series must contain at least 4 data points")
    if not np.all(np.isfinite(series)):
        raise ValueError("input series must contain only finite values")

    series = series - float(series.mean())
    profile = np.cumsum(series)

    wins = np.unique(
        np.logspace(
            np.log10(max(min_win, 4)),
            np.log10(max_win),
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
        t = np.arange(window)
        rms: list[float] = []
        for segment in segments:
            coeffs = np.polyfit(t, segment, deg=1)
            trend = np.polyval(coeffs, t)
            rms.append(float(np.sqrt(np.mean((segment - trend) ** 2))))
        flucts.append(float(np.mean(rms)))
        scales.append(window)

    if not flucts:
        return 0.0

    lw = np.log(np.asarray(scales, dtype=float) + 1e-8)
    lF = np.log(np.asarray(flucts, dtype=float) + 1e-12)
    slope, _ = np.polyfit(lw, lF, deg=1)
    return float(slope)
