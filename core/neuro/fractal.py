"""Utilities for computing fractal statistics on time-series signals.

The helpers in this module intentionally avoid metaphorical language and focus
on practical, reproducible metrics that can be consumed by controllers and
analytics pipelines.  Each function operates on plain :mod:`numpy` arrays and
implements a numerically stable variant of a well-documented estimator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np

ArrayLike = Iterable[float] | np.ndarray


def _validate_series(series: ArrayLike) -> np.ndarray:
    array = np.asarray(series, dtype=float)
    if array.ndim != 1:
        raise ValueError("series must be a 1D array or iterable")
    if array.size < 4:
        raise ValueError("series must contain at least four samples")
    if not np.all(np.isfinite(array)):
        raise ValueError("series must contain only finite values")
    return array


def rescaled_range(series: ArrayLike, window: int) -> float:
    """Return the rescaled range for ``window`` sized segments.

    The statistic is the range of the cumulative demeaned series divided by the
    standard deviation.  It is the backbone of classic Hurst exponent
    estimation techniques.
    """

    data = _validate_series(series)
    if window <= 1:
        raise ValueError("window must be greater than one")
    if data.size < window:
        return 0.0

    trimmed = data[: data.size - data.size % window]
    if trimmed.size < window:
        return 0.0

    reshaped = trimmed.reshape(-1, window)
    if reshaped.size == 0:
        return 0.0

    demeaned = reshaped - reshaped.mean(axis=1, keepdims=True)
    cumulative = demeaned.cumsum(axis=1)
    ranges = cumulative.max(axis=1) - cumulative.min(axis=1)
    stds = demeaned.std(axis=1)
    stds[stds == 0.0] = np.nan
    rs = ranges / stds
    rs = rs[np.isfinite(rs)]
    if rs.size == 0:
        return 0.0
    return float(np.mean(rs))


def hurst_exponent(
    series: ArrayLike, *, min_window: int = 8, max_window: int | None = None
) -> float:
    """Estimate the Hurst exponent using a log–log regression of R/S statistics."""

    data = _validate_series(series)
    if max_window is None:
        max_window = max(min(data.size // 2, 256), min_window)
    if max_window < min_window:
        max_window = min_window

    windows = np.unique(
        np.linspace(np.log(min_window), np.log(max_window), num=5).round().astype(int)
    )
    windows = windows[windows > 1]
    windows = windows[windows <= data.size // 2]
    if windows.size < 2:
        return 0.5

    rs_values = np.array(
        [rescaled_range(data, int(window)) for window in windows], dtype=float
    )
    mask = np.isfinite(rs_values) & (rs_values > 0.0)
    if mask.sum() < 2:
        return 0.5

    log_windows = np.log(windows[mask])
    log_rs = np.log(rs_values[mask])
    slope, _intercept = np.polyfit(log_windows, log_rs, 1)
    return float(np.clip(slope, 0.0, 1.0))


def fractal_dimension_from_hurst(hurst: float) -> float:
    """Return the fractal dimension implied by ``hurst``."""

    return float(np.clip(2.0 - float(hurst), 1.0, 2.0))


def multiscale_energy(series: ArrayLike, *, max_scale: int = 16) -> float:
    """Compute the average absolute increment across multiple scales."""

    data = _validate_series(series)
    max_scale = max(1, int(max_scale))
    increments: list[float] = []
    for scale in range(1, max_scale + 1):
        if data.size <= scale:
            break
        diffs = np.abs(data[scale:] - data[:-scale])
        increments.append(float(diffs.mean()))
    if not increments:
        return 0.0
    return float(np.mean(increments))


@dataclass(slots=True)
class FractalSummary:
    """Compact representation of the fractal statistics for a signal."""

    hurst: float
    fractal_dimension: float
    volatility: float
    scaling_exponent: float
    stability: float
    energy: float

    def as_mapping(self) -> Mapping[str, float]:
        return {
            "hurst": self.hurst,
            "fractal_dim": self.fractal_dimension,
            "volatility": self.volatility,
            "scaling_exponent": self.scaling_exponent,
            "stability": self.stability,
            "energy": self.energy,
        }


def summarise_fractal_properties(series: ArrayLike) -> FractalSummary:
    """Return a :class:`FractalSummary` for ``series``.

    ``stability`` is modelled as a Gaussian penalty around the efficient market
    benchmark of ``H = 0.5``.
    """

    data = _validate_series(series)
    hurst = hurst_exponent(data)
    fractal_dim = fractal_dimension_from_hurst(hurst)
    volatility = float(np.std(data))
    scaling_exponent = hurst
    stability = float(np.exp(-(((hurst - 0.5) / 0.2) ** 2)))
    energy = multiscale_energy(data)
    return FractalSummary(
        hurst=hurst,
        fractal_dimension=fractal_dim,
        volatility=volatility,
        scaling_exponent=scaling_exponent,
        stability=stability,
        energy=energy,
    )


__all__ = [
    "FractalSummary",
    "fractal_dimension_from_hurst",
    "hurst_exponent",
    "multiscale_energy",
    "rescaled_range",
    "summarise_fractal_properties",
]
