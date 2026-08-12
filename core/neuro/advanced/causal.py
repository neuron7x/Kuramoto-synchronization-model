# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causality diagnostics for divergence-aware neuroeconomic routines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True, slots=True)
class GrangerResult:
    """Outcome of a Granger causality test."""

    causes: bool
    p_value: float


def _lag_matrix(values: np.ndarray, lag: int) -> np.ndarray:
    """Construct a lagged design matrix with ``lag`` columns.

    Each column ``k`` contains ``values`` shifted by ``k + 1`` steps.  The
    returned matrix has ``len(values) - lag`` rows when ``len(values) > lag``.
    """

    if lag < 1:
        raise ValueError("lag must be at least one")
    n = values.size
    if n <= lag:
        raise ValueError("insufficient observations for the requested lag")
    return np.column_stack([values[(lag - k - 1) : n - (k + 1)] for k in range(lag)])


def _f_statistic(rss_restricted: float, rss_full: float, lag: int, samples: int) -> float:
    if rss_full <= 0.0 or samples <= 0:
        return 0.0
    numerator = max(rss_restricted - rss_full, 0.0) / float(lag)
    denominator = rss_full / float(samples)
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def granger_causality(
    series_y: Iterable[float],
    series_x: Iterable[float],
    *,
    max_lag: int = 3,
    p_threshold: float = 0.05,
) -> GrangerResult:
    """Perform a reduced-form Granger causality test.

    Parameters
    ----------
    series_y:
        Dependent variable that is hypothesised to be caused by ``series_x``.
    series_x:
        Candidate explanatory series.
    max_lag:
        Maximum lag order to evaluate.
    p_threshold:
        Significance threshold used to declare causality.
    """

    y = np.asarray(pd.Series(series_y).astype(float)).reshape(-1)
    x = np.asarray(pd.Series(series_x).astype(float)).reshape(-1)

    if y.size != x.size:
        raise ValueError("series must be aligned and share the same length")
    if y.size <= max_lag + 1:
        raise ValueError("not enough observations for Granger causality test")

    best_p = float("inf")
    for lag in range(1, max_lag + 1):
        try:
            y_lagged = _lag_matrix(y, lag)
            x_lagged = _lag_matrix(x, lag)
        except ValueError:
            break

        response = y[lag:]
        restricted = np.column_stack([np.ones_like(response), y_lagged])
        unrestricted = np.column_stack([restricted, x_lagged])

        beta_restricted, *_ = np.linalg.lstsq(restricted, response, rcond=None)
        beta_unrestricted, *_ = np.linalg.lstsq(unrestricted, response, rcond=None)

        resid_restricted = response - restricted @ beta_restricted
        resid_unrestricted = response - unrestricted @ beta_unrestricted

        rss_restricted = float(np.sum(resid_restricted**2))
        rss_unrestricted = float(np.sum(resid_unrestricted**2))

        df_den = response.size - (2 * lag + 1)
        if df_den <= 0:
            break
        f_stat = _f_statistic(rss_restricted, rss_unrestricted, lag, df_den)
        p_value = float(stats.f.sf(f_stat, lag, df_den))
        best_p = min(best_p, p_value)

    if best_p == float("inf"):
        raise ValueError("failed to compute Granger causality p-value")

    return GrangerResult(causes=best_p < p_threshold, p_value=best_p)


__all__ = ["GrangerResult", "granger_causality"]
