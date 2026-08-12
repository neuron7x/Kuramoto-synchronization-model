# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ricci temporal calibrator — honest empirical measurement.

Measures actual κ → dislocation temporal offset from data.
No post-hoc claims. If not predictive, says so explicitly.
Permutation test (n_shuffles=100, seed=42) for statistical validity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Empirical κ → dislocation temporal offset measurement."""

    ricci_value: float
    regime_classification: str  # "fragile" | "stable" | "transitioning"
    honest_statement: str  # calibration-gated, never claims prediction
    empirical_offset_bars: float | None  # None if not calibrated
    is_calibrated: bool
    is_predictive: bool
    p_value: float
    n_events: int
    recommendation: str  # USE / CAUTION / REMOVE_CLAIM


class RicciTemporalCalibrator:
    """Empirical calibration of κ → dislocation temporal offset.

    Method:
      1. Find κ < threshold events
      2. For each: find next |returns| > dislocation_sigma × σ
      3. Measure temporal offset distribution
      4. Permutation test (n=100): is real offset significantly better than random?
    """

    def _classify(self, kappa: float) -> str:
        if kappa < -0.3:
            return "fragile"
        if kappa > 0.3:
            return "stable"
        return "transitioning"

    def calibrate(
        self,
        kappa_series: np.ndarray,
        returns_series: np.ndarray,
        kappa_threshold: float = -0.3,
        dislocation_sigma: float = 2.0,
        max_horizon_bars: int = 30,
    ) -> CalibrationResult:
        """Calibrate temporal offset from κ and returns series."""
        kappa = np.asarray(kappa_series, dtype=np.float64)
        returns = np.asarray(returns_series, dtype=np.float64)

        n = min(len(kappa), len(returns))
        mean_kappa = float(np.mean(kappa[:n])) if n > 0 else 0.0
        classification = self._classify(mean_kappa)

        if n < 50:
            return self._no_data(mean_kappa, classification)

        kappa = kappa[:n]
        returns = returns[:n]

        sigma = float(np.std(returns[np.isfinite(returns)]))
        if sigma < 1e-12:
            return self._no_data(mean_kappa, classification)
        dis_thresh = dislocation_sigma * sigma

        kappa_events = np.where(kappa < kappa_threshold)[0]
        if len(kappa_events) == 0:
            return self._no_data(mean_kappa, classification)

        offsets = _measure_offsets(returns, kappa_events, dis_thresh, max_horizon_bars, n)

        if len(offsets) < 3:
            return self._no_data(mean_kappa, classification)

        lt = np.array(offsets)
        median_lt = float(np.median(lt))
        n_events = len(lt)
        n_uncensored = int(np.sum(lt < max_horizon_bars))

        # Binomial test
        try:
            from scipy.stats import binomtest

            p_value = float(binomtest(n_uncensored, n_events, 0.5, alternative="greater").pvalue)
        except Exception:
            p_value = 1.0

        # Permutation test (n=100, seed=42)
        rng = np.random.Generator(np.random.PCG64(42))
        shuffle_medians: list[float] = []
        for _ in range(100):
            shuffled_kappa = kappa[rng.permutation(n)]
            shuffled_events = np.where(shuffled_kappa < kappa_threshold)[0]
            s_offsets = _measure_offsets(returns, shuffled_events, dis_thresh, max_horizon_bars, n)
            if s_offsets:
                shuffle_medians.append(float(np.median(s_offsets)))

        if shuffle_medians:
            shuffle_median = float(np.median(shuffle_medians))
            is_predictive = (
                p_value < 0.05
                and median_lt < shuffle_median * 0.7
                and median_lt < max_horizon_bars * 0.8
            )
        else:
            is_predictive = False

        if is_predictive:
            recommendation = "USE"
            honest = (
                f"Ricci={mean_kappa:.3f} → {classification} topology. "
                f"Empirical offset {median_lt:.1f} bars "
                f"(n={n_events}, p={p_value:.3f}). "
                "Calibrated — revalidate on live instrument."
            )
        elif n_uncensored > n_events * 0.3:
            recommendation = "CAUTION"
            honest = (
                f"Ricci={mean_kappa:.3f} → {classification} topology. "
                f"Weak association (median={median_lt:.1f} bars, p={p_value:.3f}). "
                "Requires empirical backtest on target instrument."
            )
        else:
            recommendation = "REMOVE_CLAIM"
            honest = (
                f"Ricci={mean_kappa:.3f} → {classification} topology. "
                "Predictive temporal offset NOT established. "
                "Requires empirical backtest on target instrument."
            )

        return CalibrationResult(
            ricci_value=round(mean_kappa, 4),
            regime_classification=classification,
            honest_statement=honest,
            empirical_offset_bars=round(median_lt, 1) if is_predictive else None,
            is_calibrated=True,
            is_predictive=is_predictive,
            p_value=round(p_value, 4),
            n_events=n_events,
            recommendation=recommendation,
        )

    def _no_data(self, kappa: float, classification: str) -> CalibrationResult:
        return CalibrationResult(
            ricci_value=round(kappa, 4),
            regime_classification=classification,
            honest_statement=(
                f"Ricci={kappa:.3f} → {classification} topology. "
                "Predictive temporal offset NOT established. "
                "Requires empirical backtest on target instrument."
            ),
            empirical_offset_bars=None,
            is_calibrated=False,
            is_predictive=False,
            p_value=1.0,
            n_events=0,
            recommendation="REMOVE_CLAIM",
        )


# Backward-compat alias for existing consumers
RicciLeadTimeCalibrator = RicciTemporalCalibrator


def _measure_offsets(
    returns: np.ndarray,
    events: np.ndarray,
    dis_thresh: float,
    max_horizon: int,
    n: int,
) -> list[float]:
    """Measure temporal offsets from events to next dislocation."""
    offsets: list[float] = []
    for idx in events:
        found = False
        for h in range(1, min(max_horizon + 1, n - int(idx))):
            if abs(returns[int(idx) + h]) > dis_thresh:
                offsets.append(float(h))
                found = True
                break
        if not found:
            offsets.append(float(max_horizon))
    return offsets
