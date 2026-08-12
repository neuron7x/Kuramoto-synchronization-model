"""Hurst exponent via Detrended Fluctuation Analysis (DFA).

DFA (Peng et al. 1994) is a robust, scale-free estimator of long-range
correlation that subsumes spectral β under a more trend-tolerant
framework:

    β (spectral slope)   ↔   H (Hurst exponent)
    β ≈ 0                    H ≈ 0.5    (white noise, no memory)
    β ≈ 1                    H ≈ 1.0    (pink / 1/f noise)
    β ≈ 2                    H ≈ 1.5    (Brownian / random walk)

For a stationary signal under DFA-1 (linear detrending):
    H > 0.5  → persistent   (long-range positive autocorrelation)
    H = 0.5  → uncorrelated (white noise)
    H < 0.5  → anti-persistent (mean-reverting)

The PR #271 spectral report gave β = +1.80 → expected H ≈ 1.40.
This module computes H independently, cross-checks that estimate,
and tightens the persistence claim with scale-free evidence.

Method:
    1. Integrate (cumsum) the demeaned signal → y(t).
    2. Partition y into non-overlapping windows of length s.
    3. In each window, fit a linear trend; compute residual RMS.
    4. Average RMS across windows → F(s).
    5. Repeat for a log-spaced grid of s ∈ [16, N/4].
    6. OLS log F(s) on log(s); slope = H.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

DEFAULT_MIN_SCALE: Final[int] = 16
DEFAULT_MAX_SCALE_FRAC: Final[float] = 0.25  # up to N/4
DEFAULT_N_SCALES: Final[int] = 16


@dataclass(frozen=True)
class HurstReport:
    hurst_exponent: float
    r_squared: float
    scales: tuple[int, ...]
    fluctuations: tuple[float, ...]
    n_samples_used: int
    verdict: str  # "MEAN_REVERTING" | "WHITE_NOISE" | "PERSISTENT" | "STRONG_PERSISTENT" | "INCONCLUSIVE"


def _dfa_fluctuation(y: NDArray[np.float64], scale: int) -> float:
    """RMS of linearly-detrended residuals across non-overlapping windows."""
    n = y.shape[0]
    n_windows = n // scale
    if n_windows == 0:
        return float("nan")
    rms_sq: list[float] = []
    x = np.arange(scale, dtype=np.float64)
    for k in range(n_windows):
        seg = y[k * scale : (k + 1) * scale]
        if seg.size < scale:
            break
        # Fit seg ~ a*x + b, take residuals.
        slope, intercept = np.polyfit(x, seg, 1)
        resid = seg - (slope * x + intercept)
        rms_sq.append(float(np.mean(resid**2)))
    if not rms_sq:
        return float("nan")
    return float(np.sqrt(np.mean(rms_sq)))


def dfa_hurst(
    signal: NDArray[np.float64],
    *,
    min_scale: int = DEFAULT_MIN_SCALE,
    max_scale_frac: float = DEFAULT_MAX_SCALE_FRAC,
    n_scales: int = DEFAULT_N_SCALES,
) -> HurstReport:
    """Estimate Hurst exponent H via Detrended Fluctuation Analysis (DFA-1).

    Returns a HurstReport carrying H, the log-log-fit R², the scale grid,
    the fluctuation values, and a verdict label.
    """
    x = np.asarray(signal, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 4 * min_scale:
        return HurstReport(
            hurst_exponent=float("nan"),
            r_squared=float("nan"),
            scales=(),
            fluctuations=(),
            n_samples_used=int(n),
            verdict="INCONCLUSIVE",
        )

    # Integrate demeaned signal
    y = np.cumsum(x - float(np.mean(x)))

    max_scale = max(min_scale + 1, int(n * max_scale_frac))
    # Log-spaced integer grid, dedup
    log_min = np.log(min_scale)
    log_max = np.log(max_scale)
    raw = np.exp(np.linspace(log_min, log_max, n_scales)).astype(int)
    scales = sorted(set(int(s) for s in raw if s >= min_scale))
    if len(scales) < 4:
        return HurstReport(
            hurst_exponent=float("nan"),
            r_squared=float("nan"),
            scales=tuple(scales),
            fluctuations=(),
            n_samples_used=int(n),
            verdict="INCONCLUSIVE",
        )

    fluct: list[float] = []
    for s in scales:
        fluct.append(_dfa_fluctuation(y, s))

    scales_arr = np.asarray(scales, dtype=np.float64)
    fluct_arr = np.asarray(fluct, dtype=np.float64)
    valid = np.isfinite(fluct_arr) & (fluct_arr > 0.0)
    if int(valid.sum()) < 4:
        return HurstReport(
            hurst_exponent=float("nan"),
            r_squared=float("nan"),
            scales=tuple(int(s) for s in scales),
            fluctuations=tuple(float(f) for f in fluct_arr.tolist()),
            n_samples_used=int(n),
            verdict="INCONCLUSIVE",
        )

    log_s = np.log(scales_arr[valid])
    log_f = np.log(fluct_arr[valid])
    slope, intercept = np.polyfit(log_s, log_f, 1)
    # R² of the log-log fit
    pred = slope * log_s + intercept
    ss_res = float(np.sum((log_f - pred) ** 2))
    ss_tot = float(np.sum((log_f - log_f.mean()) ** 2))
    r_sq = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else float("nan")

    h = float(slope)
    if not np.isfinite(h):
        verdict = "INCONCLUSIVE"
    elif h < 0.4:
        verdict = "MEAN_REVERTING"
    elif h < 0.6:
        verdict = "WHITE_NOISE"
    elif h < 1.0:
        verdict = "PERSISTENT"
    else:
        verdict = "STRONG_PERSISTENT"

    return HurstReport(
        hurst_exponent=h,
        r_squared=float(r_sq) if np.isfinite(r_sq) else float("nan"),
        scales=tuple(int(s) for s in scales),
        fluctuations=tuple(float(f) for f in fluct_arr.tolist()),
        n_samples_used=int(n),
        verdict=verdict,
    )
