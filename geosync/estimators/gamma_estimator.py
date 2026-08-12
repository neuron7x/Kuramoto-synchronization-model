# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""PSD gamma estimator v2 — quality-weighted, bootstrap CI, ADF stationarity.

γ = spectral exponent from Welch PSD log-log slope.
  γ ≈ 0 → white noise (no memory, efficient market)
  γ ≈ 1 → 1/f noise (metastable, edge of criticality)
  γ ≈ 2 → Brownian (persistent, trending)

Hurst exponent: H = γ / 2 (for fBm paths).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import welch


@dataclass(frozen=True, slots=True)
class GammaEstimate:
    """PSD gamma with confidence interval and stationarity gate."""

    value: float
    quality: float
    ci_low: float
    ci_high: float
    is_valid: bool
    is_stationary: bool
    n_segments_used: int
    hurst: float


class PSDGammaEstimator:
    """Multi-segment Welch PSD with quality weighting and bootstrap CI."""

    def __init__(
        self,
        fs: float = 1.0,
        f_lo: float = 0.02,
        min_quality: float = 0.15,
        bootstrap_n: int = 200,
    ) -> None:
        self.fs = fs
        self.f_lo = f_lo
        self.min_quality = min_quality
        self.bootstrap_n = bootstrap_n

    def compute(self, data: np.ndarray) -> GammaEstimate:
        """Estimate gamma from 1D series. DERIVED, never assigned."""
        x = np.asarray(data, dtype=np.float64)
        if x.ndim != 1 or x.size < 96 or not np.all(np.isfinite(x)):
            return GammaEstimate(0.0, 0.0, 0.0, 0.0, False, False, 0, 0.0)

        x = x - np.mean(x)
        n = x.size

        is_stationary = _adf_stationary(x)

        nyquist = self.fs / 2.0
        f_hi_frac = 0.45 if n < 200 else (0.40 if n < 500 else 0.35)
        f_hi = min(nyquist * f_hi_frac, nyquist * 0.95)

        npersegs = sorted(set(max(48, min(n - 1, p)) for p in (64, 96, 128, 192, 256)))

        gammas: list[float] = []
        qualities: list[float] = []

        for nperseg in npersegs:
            g, q = self._fit_segment(x, nperseg, f_hi)
            if q >= self.min_quality:
                gammas.append(g)
                qualities.append(q)

        if not gammas:
            return GammaEstimate(0.0, 0.0, 0.0, 0.0, False, is_stationary, 0, 0.0)

        ga = np.array(gammas)
        qa = np.array(qualities)
        gamma = float(np.sum(ga * qa) / np.sum(qa))
        mean_q = float(np.mean(qa))

        # Small-sample penalty on quality, NOT on gamma
        mean_q *= 1.0 - min(0.30, 48.0 / n)

        ci_low, ci_high = self._bootstrap_ci(x, f_hi)

        gamma = float(np.clip(gamma, -5.0, 5.0))
        hurst = float(np.clip((gamma - 1.0) / 2.0, 0.0, 1.0))

        return GammaEstimate(
            value=gamma,
            quality=round(mean_q, 4),
            ci_low=round(ci_low, 4),
            ci_high=round(ci_high, 4),
            is_valid=mean_q >= self.min_quality and is_stationary,
            is_stationary=is_stationary,
            n_segments_used=len(gammas),
            hurst=round(hurst, 4),
        )

    def _fit_segment(
        self,
        x: np.ndarray,
        nperseg: int,
        f_hi: float,
    ) -> tuple[float, float]:
        f, pxx = welch(x, fs=self.fs, nperseg=nperseg, detrend="linear", scaling="density")
        mask = (f >= self.f_lo) & (f <= f_hi) & (pxx > 0.0) & np.isfinite(pxx)
        if int(mask.sum()) < 8:
            return 0.0, 0.0

        xf = np.log(f[mask])
        yf = np.log(pxx[mask])
        coeffs = np.polyfit(xf, yf, deg=1)
        slope = coeffs[0]
        intercept = coeffs[1]

        pred = slope * xf + intercept
        resid = yf - pred
        mad = float(np.median(np.abs(resid - np.median(resid)))) + 1e-12
        quality = 1.0 / (1.0 + 1.4826 * mad)

        return float(-slope), float(quality)

    def _bootstrap_ci(
        self,
        x: np.ndarray,
        f_hi: float,
    ) -> tuple[float, float]:
        rng = np.random.Generator(np.random.PCG64(42))
        boot: list[float] = []
        n = len(x)
        nperseg = max(48, min(n - 1, 128))

        for _ in range(self.bootstrap_n):
            idx = rng.integers(0, n, size=n)
            g, q = self._fit_segment(x[idx], nperseg, f_hi)
            if q >= 0.1:
                boot.append(g)

        if len(boot) < 10:
            return -5.0, 5.0

        return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def _adf_stationary(x: np.ndarray) -> bool:
    try:
        from statsmodels.tsa.stattools import adfuller

        result = adfuller(x, maxlag=int(np.sqrt(len(x))), autolag=None)
        return float(result[1]) < 0.05
    except (ImportError, ValueError, np.linalg.LinAlgError):
        return True
