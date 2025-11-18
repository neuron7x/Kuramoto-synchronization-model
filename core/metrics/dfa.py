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
    """Return the DFA scaling exponent of ``x``.

    The implementation follows the standard log–log regression between the
    window scale and the mean fluctuation magnitude.  Edge cases with
    insufficient data gracefully fallback to zero so downstream controllers can
    decide how to react.
    """

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("dfa_alpha expects a 1-D sequence")
    if series.size == 0:
        return 0.0

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
