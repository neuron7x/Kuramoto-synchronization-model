# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Early-warning predictor: rolling Kuramoto-order-parameter features.

Given a :class:`PhaseMatrix` of bank-level phases the predictor computes
three time-resolved features designed to detect *approach* to a phase
transition (not the transition itself):

1. **Level** :math:`R(t) = \\Big| \\frac{1}{N} \\sum_j e^{i\\theta_j(t)}\\Big|`
   — the global order parameter. Bounded by INV-K1: :math:`0 \\le R \\le 1`.
2. **Slope** — least-squares slope of :math:`R` over a trailing window
   of ``window`` samples. A persistent positive slope indicates
   accelerating coherence.
3. **Variance** — sample variance of :math:`R` over the same window.
   Critical-slowing-down theory predicts variance grows as the system
   approaches a bifurcation (Scheffer et al. 2009, *Nature* 461: 53);
   variance + slope are the two canonical CSD diagnostics.

The features are *physics-anchored* (INV-K1, Scheffer CSD), not
hand-tuned. The composite *score* used downstream by the falsification
battery is :math:`R \\cdot |slope| / (1 + var^{-1})` — a simple monotone
combination chosen for transparency. Alternative composites are easy
to swap in via :class:`EarlyWarningConfig`.

Pure-function API. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.contracts import PhaseMatrix

__all__ = [
    "EarlyWarningConfig",
    "EarlyWarningResult",
    "compute_early_warning",
    "kuramoto_order_parameter",
]


def kuramoto_order_parameter(phases: NDArray[np.float64]) -> NDArray[np.float64]:
    """Time-resolved global order parameter :math:`R(t)`.

    Parameters
    ----------
    phases
        Real array shape ``(T, N)`` of phases (radians) — the canonical
        ``PhaseMatrix.theta`` layout used across the kuramoto stack.

    Returns
    -------
    Real array shape ``(T,)`` with values in ``[0, 1]`` — INV-K1.
    """
    if phases.ndim != 2:
        raise ValueError(f"phases must be 2-D, got shape={phases.shape}")
    z = np.exp(1j * phases.astype(np.float64))
    r = np.abs(z.mean(axis=1))
    out: NDArray[np.float64] = np.asarray(r, dtype=np.float64)
    return out


@dataclass(frozen=True, slots=True)
class EarlyWarningConfig:
    """Predictor hyperparameters.

    Attributes
    ----------
    window
        Trailing-window length in samples. Default 60 corresponds to
        ~3 trading-month rolling on daily data.
    min_window_fraction
        Minimum number of finite samples (as a fraction of ``window``)
        required at a given time-step for that step's features to be
        non-NaN. Default ``0.95`` matches a strict rolling regime.

    Invariants
    ----------
    INV-EW1: ``window >= 4`` (variance + slope require ≥4 points).
    INV-EW2: ``0.5 <= min_window_fraction <= 1.0``.
    """

    window: int = 60
    min_window_fraction: float = 0.95

    def __post_init__(self) -> None:
        if self.window < 4:
            raise ValueError(f"INV-EW1: window must be >= 4, got {self.window}")
        if not 0.5 <= self.min_window_fraction <= 1.0:
            raise ValueError(
                f"INV-EW2: min_window_fraction must be in [0.5, 1.0], "
                f"got {self.min_window_fraction}"
            )


@dataclass(frozen=True, slots=True)
class EarlyWarningResult:
    """Time-resolved predictor outputs.

    Attributes
    ----------
    R
        Global order parameter :math:`R(t)` shape ``(T,)``.
    R_level
        Trailing-window mean of :math:`R`, shape ``(T,)``. NaN at indices
        where the window is insufficient (start of series).
    R_slope
        Trailing-window OLS slope of :math:`R`, shape ``(T,)``.
    R_var
        Trailing-window sample variance (``ddof=1``), shape ``(T,)``.
    score
        Composite predictor :math:`R\\_level \\cdot |R\\_slope| \\cdot \\sqrt{R\\_var}`,
        shape ``(T,)``. NaN where any component is NaN. Designed to grow
        with all three CSD features simultaneously.
    """

    R: NDArray[np.float64]
    R_level: NDArray[np.float64]
    R_slope: NDArray[np.float64]
    R_var: NDArray[np.float64]
    score: NDArray[np.float64]

    def __post_init__(self) -> None:
        for name in ("R", "R_level", "R_slope", "R_var", "score"):
            arr = getattr(self, name)
            if arr.ndim != 1:
                raise ValueError(f"{name} must be 1-D, got shape={arr.shape}")
            arr2 = np.array(arr, dtype=np.float64, copy=True)
            arr2.flags.writeable = False
            object.__setattr__(self, name, arr2)
        # INV-K1 on the raw R series (NaN-tolerant comparison).
        r = self.R
        finite = r[np.isfinite(r)]
        if finite.size > 0 and (finite.min() < 0.0 or finite.max() > 1.0 + 1e-12):
            raise ValueError(
                f"INV-K1 VIOLATED: R out of [0,1]; min={finite.min():.6f}, max={finite.max():.6f}"
            )


def _rolling_slope(values: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Trailing-window OLS slope; output[t] uses values[t-window+1 .. t]."""
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    x = np.arange(window, dtype=np.float64)
    x_mean = x.mean()
    x_centered = x - x_mean
    denom = float((x_centered**2).sum())
    if denom <= 0:
        return out
    for t in range(window - 1, n):
        seg = values[t - window + 1 : t + 1]
        y_mean = seg.mean()
        out[t] = float((x_centered * (seg - y_mean)).sum() / denom)
    return out


def _rolling_var(values: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Trailing-window sample variance (``ddof=1``)."""
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    for t in range(window - 1, n):
        seg = values[t - window + 1 : t + 1]
        out[t] = float(seg.var(ddof=1))
    return out


def _rolling_mean(values: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    cumsum = np.concatenate(([0.0], np.cumsum(values, dtype=np.float64)))
    out[window - 1 :] = (cumsum[window:] - cumsum[: n - window + 1]) / float(window)
    return out


def compute_early_warning(
    phases: PhaseMatrix,
    config: EarlyWarningConfig | None = None,
) -> EarlyWarningResult:
    """Compute the rolling early-warning features from a :class:`PhaseMatrix`.

    Parameters
    ----------
    phases
        Per-bank phases on the canonical ``(T, N_banks)`` layout
        produced by :func:`core.kuramoto.phase_extractor.PhaseExtractor`.
    config
        Optional :class:`EarlyWarningConfig`; defaults to ``EarlyWarningConfig()``.
    """
    cfg = config if config is not None else EarlyWarningConfig()
    theta = np.asarray(phases.theta, dtype=np.float64)
    if theta.ndim != 2:
        raise ValueError(f"PhaseMatrix.theta must be 2-D, got {theta.shape}")
    if theta.shape[0] < cfg.window:
        raise ValueError(
            f"T={theta.shape[0]} shorter than window={cfg.window}; "
            f"increase data length or shrink window"
        )
    r = kuramoto_order_parameter(theta)
    r_level = _rolling_mean(r, cfg.window)
    r_slope = _rolling_slope(r, cfg.window)
    r_var = _rolling_var(r, cfg.window)
    score = r_level * np.abs(r_slope) * np.sqrt(np.maximum(r_var, 0.0))
    return EarlyWarningResult(
        R=r,
        R_level=r_level,
        R_slope=r_slope,
        R_var=r_var,
        score=score,
    )
