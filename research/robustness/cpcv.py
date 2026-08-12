# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Combinatorial Purged Cross-Validation + PBO + Probabilistic Sharpe.

Canonical references:

- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*,
  Wiley. Chapter 7 (CPCV), Chapter 11 (PBO), Chapter 14 (PSR/DSR).
- Bailey, Borwein, Lopez de Prado, Zhu (2017) "The Probability of
  Backtest Overfitting", *Journal of Computational Finance*.

All functions are pure and deterministic. Inputs are numpy arrays or
pandas Series; outputs are dataclasses or scalars. No I/O.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class CPCVSplit:
    """One training / testing index pair from a CPCV fold combination."""

    train_index: NDArray[np.int64]
    test_index: NDArray[np.int64]
    embargo_mask: NDArray[np.bool_]


def _purge_and_embargo(
    n: int,
    test_blocks: tuple[tuple[int, int], ...],
    embargo: int,
) -> tuple[NDArray[np.int64], NDArray[np.bool_]]:
    """Compute the train index and embargo mask for given test blocks.

    Any training sample within ``embargo`` bars of a test block is dropped
    (purged) to prevent leakage from overlapping labels.
    """
    mask = np.ones(n, dtype=bool)
    for lo, hi in test_blocks:
        mask[max(0, lo - embargo) : min(n, hi + embargo)] = False
    train_index = np.nonzero(mask)[0].astype(np.int64)
    return train_index, ~mask


def cpcv_splits(
    n_samples: int,
    n_groups: int,
    n_test_groups: int,
    embargo: int = 0,
) -> Iterator[CPCVSplit]:
    """Yield every ``C(n_groups, n_test_groups)`` purged split.

    ``n_groups`` contiguous buckets of (roughly) equal size partition the
    time axis; every combination of ``n_test_groups`` of them is a
    disjoint test set, the remainder is the training set after purging
    ``embargo`` bars around each test block.

    Parameters
    ----------
    n_samples
        Total number of timesteps.
    n_groups
        Total number of time-ordered groups (paper convention: N).
    n_test_groups
        Number of groups forming the test set each combination (k).
    embargo
        Embargo bars applied around each test block on both sides.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0, got {n_samples}")
    if not 2 <= n_groups <= n_samples:
        raise ValueError(f"n_groups must be in [2, n_samples={n_samples}], got {n_groups}")
    if not 1 <= n_test_groups < n_groups:
        raise ValueError(
            f"n_test_groups must be in [1, n_groups-1={n_groups - 1}], got {n_test_groups}"
        )
    if embargo < 0:
        raise ValueError(f"embargo must be >= 0, got {embargo}")

    edges = np.linspace(0, n_samples, n_groups + 1, dtype=np.int64)
    group_ranges: tuple[tuple[int, int], ...] = tuple(
        (int(edges[i]), int(edges[i + 1])) for i in range(n_groups)
    )

    for test_group_ids in combinations(range(n_groups), n_test_groups):
        test_blocks = tuple(group_ranges[g] for g in test_group_ids)
        train_idx, embargo_mask = _purge_and_embargo(n_samples, test_blocks, embargo)
        test_idx = np.concatenate([np.arange(lo, hi, dtype=np.int64) for lo, hi in test_blocks])
        yield CPCVSplit(
            train_index=train_idx,
            test_index=test_idx,
            embargo_mask=embargo_mask,
        )


def estimate_pbo(oos_matrix: NDArray[np.float64]) -> float:
    """Probability of Backtest Overfitting.

    Bailey et al. (2017) logit-rank estimator. ``oos_matrix`` is shape
    (n_paths, n_strategies); each row is the OOS performance of all
    strategies on one CPCV combinatorial path. The PBO is the fraction
    of paths where the *in-sample best* strategy is below median OOS.

    Returns a scalar in [0, 1]. Lower is better; >= 0.5 is no better
    than a random selection from the strategy family.
    """
    if oos_matrix.ndim != 2:
        raise ValueError(
            f"oos_matrix must be 2-D (paths × strategies), got shape {oos_matrix.shape}"
        )
    n_paths, n_strategies = oos_matrix.shape
    if n_paths < 2 or n_strategies < 2:
        raise ValueError(
            f"PBO requires at least 2 paths and 2 strategies, got {n_paths} × {n_strategies}"
        )

    overfits = 0
    for path_ix in range(n_paths):
        is_scores = np.delete(oos_matrix, path_ix, axis=0).mean(axis=0)
        best_is = int(np.argmax(is_scores))
        oos_rank = (oos_matrix[path_ix] <= oos_matrix[path_ix, best_is]).sum()
        # Rank is 1-indexed: N_strats worst, 1 best. Below median → overfit.
        if oos_rank <= n_strategies / 2:
            overfits += 1
    return float(overfits / n_paths)


def probabilistic_sharpe_ratio(
    returns: NDArray[np.float64],
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Probabilistic Sharpe Ratio (Lopez de Prado 2018, Eq. 14.1).

    PSR = Φ( (SR − SR*) · √(T − 1) / √(1 − γ₃·SR + (γ₄ − 1)/4 · SR²) )

    Corrects the observed Sharpe for its own sampling distribution under
    non-normal returns (skewness γ₃, kurtosis γ₄). Returns a probability
    in [0, 1] that the true Sharpe exceeds ``sr_benchmark``.

    Degenerate cases (n ≤ 1, zero variance, non-finite inputs) return NaN
    rather than raising, so aggregate reports do not crash on empty folds.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1:
        raise ValueError(f"returns must be 1-D, got shape {r.shape}")
    n = r.size
    if n < 2 or not np.all(np.isfinite(r)):
        return math.nan
    std = r.std(ddof=1)
    if std <= 0:
        return math.nan

    mean = r.mean()
    sr = mean / std * math.sqrt(periods_per_year)
    sr_star = float(sr_benchmark)

    centered = r - mean
    m2 = float((centered**2).mean())
    if m2 <= 0:
        return math.nan
    m3 = float((centered**3).mean())
    m4 = float((centered**4).mean())
    skew = m3 / (m2**1.5)
    kurt = m4 / (m2**2)

    denom_sq = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom_sq <= 0 or not math.isfinite(denom_sq):
        return math.nan
    z = (sr - sr_star) * math.sqrt(n - 1) / math.sqrt(denom_sq)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _newey_west_effective_size(
    returns: NDArray[np.float64],
    lag: int,
) -> float:
    """Effective sample size under Newey–West HAC correction.

    Given residuals ``r`` of length ``T``, the Bartlett-kernel Newey–West
    variance estimator inflates the naive variance by

        c(L) = 1 + 2 · Σ_{k=1..L}  w_k · ρ_k       with  w_k = 1 − k/(L+1),

    where ρ_k is the lag-k autocorrelation of ``r``. The "effective sample
    size" is then ``T / max(c(L), 1e-12)`` — under positive serial
    correlation this is materially smaller than ``T``; under
    over-differencing (negative autocorrelation) it is larger.

    References: Newey & West (1987) *Econometrica* 55; Newey & West (1994)
    *Review of Economic Studies* 61.
    """
    n = returns.size
    if lag < 0:
        raise ValueError(f"lag must be >= 0, got {lag}")
    if n < 2 or lag == 0:
        return float(n)
    centered = returns - returns.mean()
    gamma0 = float((centered * centered).mean())
    if gamma0 <= 0:
        return float(n)
    max_lag = min(lag, n - 1)
    correction = 1.0
    for k in range(1, max_lag + 1):
        gamma_k = float((centered[:-k] * centered[k:]).mean())
        rho_k = gamma_k / gamma0
        weight = 1.0 - k / (max_lag + 1)
        correction += 2.0 * weight * rho_k
    # Fail-closed against pathological inputs: keep effective_n positive,
    # strictly less than 2T, and finite. Correction ≤ 0 is degenerate.
    correction = max(correction, 1e-12)
    return float(n) / correction


def _newey_west_auto_lag(n: int) -> int:
    """Newey–West (1994) automatic bandwidth rule.

    L* = floor(4 · (T/100)^(2/9)).
    Returns 0 for n < 4 (no HAC correction possible); the caller should
    treat that as "fallback to vanilla PSR".
    """
    if n < 4:
        return 0
    return int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def probabilistic_sharpe_ratio_hac(
    returns: NDArray[np.float64],
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
    lag: int | None = None,
) -> float:
    """HAC-adjusted Probabilistic Sharpe Ratio (Newey–West, Bartlett kernel).

    The vanilla PSR denominator uses the naive ``√(T − 1)`` sample-size
    scaling, which *inflates* the confidence statement under positive
    serial correlation. This function replaces ``T`` with the
    Newey–West effective sample size before applying Lopez de Prado's
    skew/kurt correction:

        PSR_HAC = Φ( (SR − SR*) · √(T_eff − 1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )

    with ``T_eff = T / (1 + 2·Σ_{k≤L} w_k ρ_k)`` and Bartlett weights
    ``w_k = 1 − k/(L+1)``.

    Parameters
    ----------
    returns
        1-D array of periodic (daily/weekly/…) returns of the strategy.
    sr_benchmark
        Null-hypothesis Sharpe ratio (annualised, same units as the
        ``periods_per_year`` scaling). Default 0.
    periods_per_year
        Number of ``returns`` observations per year. 252 for daily
        business-day returns.
    lag
        Explicit Newey–West truncation lag ``L``. If ``None``, the
        Newey–West (1994) automatic bandwidth ``L* = floor(4·(T/100)^(2/9))``
        is used.

    Returns
    -------
    float
        Probability in [0, 1] that the true Sharpe exceeds
        ``sr_benchmark`` under the HAC-adjusted sampling distribution.
        Degenerate inputs (n ≤ 2, zero variance, non-finite) return NaN.

    Notes
    -----
    White-noise returns yield ``PSR_HAC ≈ PSR`` because all ``ρ_k → 0``.
    Positive first-order autocorrelation (regime-following strategies)
    collapses the effective sample and drives ``PSR_HAC < PSR``. Negative
    autocorrelation (mean-reverting noise) pushes ``PSR_HAC > PSR``.

    References
    ----------
    Newey & West (1987), *Econometrica* 55(3): 703–708.
    Lopez de Prado (2018), *Advances in Financial ML*, Ch. 14.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1:
        raise ValueError(f"returns must be 1-D, got shape {r.shape}")
    n = r.size
    if n < 2 or not np.all(np.isfinite(r)):
        return math.nan
    std = r.std(ddof=1)
    if std <= 0:
        return math.nan

    mean = r.mean()
    sr = mean / std * math.sqrt(periods_per_year)
    sr_star = float(sr_benchmark)

    centered = r - mean
    m2 = float((centered**2).mean())
    if m2 <= 0:
        return math.nan
    m3 = float((centered**3).mean())
    m4 = float((centered**4).mean())
    skew = m3 / (m2**1.5)
    kurt = m4 / (m2**2)

    denom_sq = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom_sq <= 0 or not math.isfinite(denom_sq):
        return math.nan

    effective_lag = _newey_west_auto_lag(n) if lag is None else int(lag)
    n_eff = _newey_west_effective_size(r, effective_lag)
    if n_eff < 2 or not math.isfinite(n_eff):
        return math.nan

    z = (sr - sr_star) * math.sqrt(n_eff - 1.0) / math.sqrt(denom_sq)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def rolling_probabilistic_sharpe(
    returns: NDArray[np.float64],
    window: int,
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
) -> NDArray[np.float64]:
    """Rolling PSR over a fixed window.

    Returns an array of length ``len(returns)`` with NaN for the first
    ``window - 1`` entries (analogous to ``pandas.Series.rolling``).
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1:
        raise ValueError(f"returns must be 1-D, got shape {r.shape}")
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    n = r.size
    out = np.full(n, math.nan, dtype=np.float64)
    if n < window:
        return out
    for end in range(window, n + 1):
        out[end - 1] = probabilistic_sharpe_ratio(
            r[end - window : end],
            sr_benchmark=sr_benchmark,
            periods_per_year=periods_per_year,
        )
    return out
