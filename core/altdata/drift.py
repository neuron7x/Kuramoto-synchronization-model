"""Distribution drift monitoring utilities for alternative data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

try:
    from scipy import stats as _SCIPY_STATS
except Exception:  # pragma: no cover - handled via fallback logic
    _logger.warning(
        "SciPy stats module unavailable for drift monitoring; using NumPy fallback",
        exc_info=_logger.isEnabledFor(logging.DEBUG),
    )
    _SCIPY_STATS = None


@dataclass(frozen=True)
class DriftAssessment:
    """Summary of a drift evaluation."""

    metric: str
    value: float
    threshold: float
    drifted: bool
    details: dict[str, float]


class DistributionDriftMonitor:
    """Assess population drift for alternative data feature streams."""

    def __init__(
        self, *, method: str = "psi", threshold: float = 0.2, bins: int = 10
    ) -> None:
        self._method = method.lower()
        if self._method not in {"psi", "ks"}:
            raise ValueError("method must be either 'psi' or 'ks'")
        self._threshold = float(threshold)
        self._bins = max(3, int(bins))

    def _ensure_series(self, values: Iterable[float]) -> pd.Series:
        series = pd.Series(list(values), dtype=float).dropna()
        if series.empty:
            raise ValueError("Input series must contain at least one value")
        return series

    def _psi(self, reference: pd.Series, current: pd.Series) -> DriftAssessment:
        quantiles = np.linspace(0, 1, self._bins + 1)
        edges = np.unique(np.quantile(reference, quantiles))
        if len(edges) < 2:
            return DriftAssessment(
                "psi", 0.0, self._threshold, False, {"bins": len(edges)}
            )
        ref_hist, _ = np.histogram(reference, bins=edges)
        cur_hist, _ = np.histogram(current, bins=edges)
        ref_pct = np.clip(ref_hist / ref_hist.sum(), 1e-6, None)
        cur_pct = np.clip(cur_hist / max(cur_hist.sum(), 1), 1e-6, None)
        psi = float(((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)).sum())
        return DriftAssessment(
            "psi",
            psi,
            self._threshold,
            psi >= self._threshold,
            {"bins": float(len(edges) - 1)},
        )

    def _ks(self, reference: pd.Series, current: pd.Series) -> DriftAssessment:
        ref_values = reference.to_numpy(dtype=float, copy=False)
        cur_values = current.to_numpy(dtype=float, copy=False)

        if _SCIPY_STATS is not None:
            try:
                statistic, pvalue = _SCIPY_STATS.ks_2samp(ref_values, cur_values)
            except Exception:  # pragma: no cover - exercised in tests
                _logger.warning(
                    "SciPy ks_2samp failed; falling back to NumPy implementation",
                    exc_info=_logger.isEnabledFor(logging.DEBUG),
                )
                statistic, pvalue = _ks_2samp_fallback(ref_values, cur_values)
        else:
            statistic, pvalue = _ks_2samp_fallback(ref_values, cur_values)

        drifted = pvalue < self._threshold
        return DriftAssessment(
            "ks", float(statistic), self._threshold, drifted, {"pvalue": float(pvalue)}
        )

    def assess(
        self, reference: Iterable[float], current: Iterable[float]
    ) -> DriftAssessment:
        """Evaluate drift between reference and current samples."""

        ref_series = self._ensure_series(reference)
        cur_series = self._ensure_series(current)
        if self._method == "psi":
            return self._psi(ref_series, cur_series)
        return self._ks(ref_series, cur_series)


__all__ = ["DistributionDriftMonitor", "DriftAssessment"]


def _ks_2samp_fallback(
    reference: np.ndarray, current: np.ndarray
) -> tuple[float, float]:
    """Compute a two-sample KS test using only NumPy primitives.

    The implementation mirrors the asymptotic formulation used by SciPy and is
    employed whenever SciPy is unavailable or misconfigured in lightweight
    environments. It returns the KS statistic and an approximate p-value based on
    the Kolmogorov distribution.
    """

    reference = np.sort(np.asarray(reference, dtype=float))
    current = np.sort(np.asarray(current, dtype=float))

    n_ref = reference.size
    n_cur = current.size
    if n_ref == 0 or n_cur == 0:
        raise ValueError("KS test requires both samples to contain observations")

    combined = np.concatenate((reference, current))
    cdf_ref = np.searchsorted(reference, combined, side="right") / n_ref
    cdf_cur = np.searchsorted(current, combined, side="right") / n_cur
    statistic = float(np.max(np.abs(cdf_ref - cdf_cur)))

    if n_ref * n_cur <= 10_000:
        pvalue = _ks_pvalue_exact(statistic, n_ref, n_cur)
    else:
        pvalue = _ks_pvalue_asymptotic(statistic, n_ref, n_cur)

    return statistic, pvalue


def _ks_pvalue_asymptotic(statistic: float, n_ref: int, n_cur: int) -> float:
    """Return the Kolmogorov p-value using the asymptotic formulation."""

    effective_n = np.sqrt((n_ref * n_cur) / (n_ref + n_cur))
    adjusted = (effective_n + 0.12 + 0.11 / max(effective_n, 1e-12)) * statistic
    if adjusted <= 0.0:
        return 1.0

    indices = np.arange(1, 101, dtype=float)
    signs = np.where(indices.astype(int) % 2 == 1, 1.0, -1.0)
    terms = np.exp(-2.0 * (indices**2) * (adjusted**2))
    return float(np.clip(2.0 * np.sum(signs * terms), 0.0, 1.0))


def _ks_pvalue_exact(statistic: float, n_ref: int, n_cur: int) -> float:
    """Return the exact two-sample KS p-value via dynamic programming."""

    if statistic <= 0.0:
        return 1.0

    prob = np.zeros((n_ref + 1, n_cur + 1), dtype=float)
    prob[0, 0] = 1.0

    inv_ref = 1.0 / float(n_ref)
    inv_cur = 1.0 / float(n_cur)
    tolerance = 1e-12
    limit = max(statistic - tolerance, 0.0)

    for i in range(n_ref + 1):
        for j in range(n_cur + 1):
            current_prob = prob[i, j]
            if current_prob <= 0.0:
                continue
            remaining_ref = n_ref - i
            remaining_cur = n_cur - j
            remaining_total = remaining_ref + remaining_cur
            if remaining_total == 0:
                continue

            if remaining_ref:
                new_diff = abs((i + 1) * inv_ref - j * inv_cur)
                if new_diff <= limit:
                    prob[i + 1, j] += current_prob * (remaining_ref / remaining_total)

            if remaining_cur:
                new_diff = abs(i * inv_ref - (j + 1) * inv_cur)
                if new_diff <= limit:
                    prob[i, j + 1] += current_prob * (remaining_cur / remaining_total)

    probability_within = float(np.clip(prob[n_ref, n_cur], 0.0, 1.0))
    return 1.0 - probability_within
