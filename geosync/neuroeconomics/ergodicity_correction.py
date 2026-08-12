# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Peters-Kelly ergodicity correction for non-ergodic markets.

Theory (Peters 2019):
  Ensemble growth: g_ens = μ
  Time growth:     g_time = μ - σ²/2   (Itô SDE: dW = μdt + σdB)
  Ergodicity gap:  Δg = σ²/2  (always ≥ 0)

  NEI = σ² / (2|μ| + ε)  — Non-Ergodicity Index
    < 0.5  → ERGODIC
    ≥ 0.5  → non-ergodic (correction material)

  kelly_corrected = max(0, μ/σ²) * (1 - min(1.0, NEI))
  pragmatic_corrected = pragmatic * exp(-Δg × horizon)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ErgodicityResult:
    """Full SDE ergodicity assessment."""

    ensemble_drift: float  # μ
    time_average_drift: float  # μ - σ²/2
    sde_drift_correction: float  # -σ²/2
    volatility: float  # σ
    nei: float  # non-ergodicity index
    kelly_corrected: float  # max(0, μ/σ²) * (1 - min(1, NEI))
    pragmatic_corrected: float  # exp(-Δg × horizon)
    is_ergodic: bool  # abs(sde_drift_correction) < 0.01


class ErgodicityCorrection:
    """Peters-Kelly correction for decision pipeline.

    Parameters
    ----------
    horizon_bars
        Expected trade duration for discount computation.
    mu_epsilon
        Minimum |μ| to avoid division by zero in NEI.
    ergodic_threshold
        Maximum |sde_drift_correction| for is_ergodic=True.
    """

    def __init__(
        self,
        horizon_bars: float = 10.0,
        mu_epsilon: float = 1e-8,
        ergodic_threshold: float = 0.01,
    ) -> None:
        self._horizon = horizon_bars
        self._mu_eps = mu_epsilon
        self._ergodic_threshold = ergodic_threshold

    def update(self, returns: np.ndarray) -> ErgodicityResult:
        """Compute ergodicity state from returns window."""
        r = np.asarray(returns, dtype=np.float64).ravel()
        r = r[np.isfinite(r)]

        if len(r) < 10:
            return ErgodicityResult(
                ensemble_drift=0.0,
                time_average_drift=0.0,
                sde_drift_correction=0.0,
                volatility=0.0,
                nei=999.0,
                kelly_corrected=0.0,
                pragmatic_corrected=0.0,
                is_ergodic=False,
            )

        mu = float(np.mean(r))
        sigma = float(np.std(r, ddof=1))

        # Itô SDE correction: -σ²/2
        sde_correction = -(sigma**2) / 2.0
        time_drift = mu + sde_correction  # μ - σ²/2

        # Non-Ergodicity Index
        nei = sigma**2 / (2.0 * abs(mu) + self._mu_eps)

        # Kelly with ergodicity correction
        if sigma > 1e-12 and abs(mu) > self._mu_eps:
            f_kelly = max(0.0, mu / (sigma**2))
            correction = 1.0 - min(1.0, nei)
            kelly = float(np.clip(f_kelly * correction, 0.0, 1.0))
        else:
            kelly = 0.0

        # Pragmatic discount: exp(-Δg × horizon), Δg = σ²/2
        gap = sigma**2 / 2.0
        pragmatic = float(np.clip(math.exp(-gap * self._horizon), 0.0, 1.0))

        is_ergodic = abs(sde_correction) < self._ergodic_threshold

        return ErgodicityResult(
            ensemble_drift=round(mu, 8),
            time_average_drift=round(time_drift, 8),
            sde_drift_correction=round(sde_correction, 8),
            volatility=round(sigma, 8),
            nei=round(nei, 4),
            kelly_corrected=round(kelly, 6),
            pragmatic_corrected=round(pragmatic, 6),
            is_ergodic=is_ergodic,
        )

    def correct_pragmatic(
        self,
        pragmatic: float,
        state: ErgodicityResult,
    ) -> float:
        """Apply ergodicity discount to pragmatic value."""
        return pragmatic * state.pragmatic_corrected
