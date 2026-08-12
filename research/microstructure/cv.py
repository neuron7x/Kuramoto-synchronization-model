"""Purged & embargoed K-fold cross-validation for time-series signals.

Standard K-fold leaks information in time-series problems because a
training row whose prediction horizon overlaps the test fold has
effectively "seen" the test label. Lopez de Prado (2018, AFML Ch. 7)
formalises the correction:

    * PURGE   drop training rows whose [t, t+horizon] overlaps the
              test fold; these rows' targets are partially measured
              inside the test window.

    * EMBARGO drop training rows immediately after the test fold to
              prevent serial correlation leakage from pad-row
              neighbours of test labels.

This module provides pure-function index generators + per-fold IC
aggregation. Deterministic. No RNG.

Complement to R1 (block bootstrap): where block-bootstrap preserves
autocorrelation inside CI estimates, purged K-fold is the canonical
OOS estimator for time-series-dependent signals.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr

DEFAULT_K: Final[int] = 5
DEFAULT_EMBARGO_SEC: Final[int] = 60


@dataclass(frozen=True)
class PurgedKFoldReport:
    """Aggregate OOS IC across purged K-fold."""

    k: int
    horizon_rows: int
    embargo_rows: int
    ic_per_fold: tuple[float, ...]
    ic_mean: float
    ic_median: float
    ic_std: float
    ic_min: float
    ic_max: float
    pos_fold_frac: float
    n_rows_total: int
    n_train_rows_per_fold: tuple[int, ...]
    n_test_rows_per_fold: tuple[int, ...]


def purged_kfold_indices(
    n_rows: int,
    *,
    k: int = DEFAULT_K,
    horizon_rows: int,
    embargo_rows: int = DEFAULT_EMBARGO_SEC,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """Yield (train_idx, test_idx) for each of K contiguous folds.

    Splits are contiguous: fold i covers rows [i · fold_size, (i+1) · fold_size).
    Training indices exclude the purge zone
    [test_start - horizon_rows, test_end) and the embargo zone
    [test_end, test_end + embargo_rows).
    """
    if k < 2:
        raise ValueError(f"k must be >= 2, got {k}")
    if n_rows < k:
        raise ValueError(f"n_rows={n_rows} must be >= k={k}")
    if horizon_rows < 0:
        raise ValueError(f"horizon_rows must be >= 0, got {horizon_rows}")
    if embargo_rows < 0:
        raise ValueError(f"embargo_rows must be >= 0, got {embargo_rows}")

    fold_size = n_rows // k
    for i in range(k):
        test_start = i * fold_size
        test_end = (i + 1) * fold_size if i < k - 1 else n_rows
        purge_lo = max(0, test_start - horizon_rows)
        embargo_hi = min(n_rows, test_end + embargo_rows)

        train_mask = np.ones(n_rows, dtype=bool)
        train_mask[purge_lo:test_end] = False
        train_mask[test_end:embargo_hi] = False

        train_idx = np.where(train_mask)[0]
        test_idx = np.arange(test_start, test_end, dtype=np.int64)
        yield train_idx.astype(np.int64), test_idx


def _pooled_spearman(x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 30:
        return float("nan")
    xs = x[mask]
    ys = y[mask]
    if float(np.std(xs)) < 1e-14 or float(np.std(ys)) < 1e-14:
        return float("nan")
    rho, _ = spearmanr(xs, ys)
    return float(rho) if np.isfinite(rho) else float("nan")


def purged_kfold_ic(
    signal_panel: NDArray[np.float64],
    target_panel: NDArray[np.float64],
    *,
    k: int = DEFAULT_K,
    horizon_rows: int,
    embargo_rows: int = DEFAULT_EMBARGO_SEC,
) -> PurgedKFoldReport:
    """Compute IC on each test fold under purged K-fold.

    Accepts 2D panels (rows × symbols). Each fold's test IC is the
    pooled Spearman over all (symbol, row) pairs in the test window.
    """
    if signal_panel.shape != target_panel.shape:
        raise ValueError(
            f"signal/target panel shape mismatch: {signal_panel.shape} vs {target_panel.shape}"
        )
    n = int(signal_panel.shape[0])

    ics: list[float] = []
    train_counts: list[int] = []
    test_counts: list[int] = []
    for train_idx, test_idx in purged_kfold_indices(
        n, k=k, horizon_rows=horizon_rows, embargo_rows=embargo_rows
    ):
        s_test = signal_panel[test_idx].ravel()
        t_test = target_panel[test_idx].ravel()
        ic = _pooled_spearman(s_test, t_test)
        ics.append(ic)
        train_counts.append(int(train_idx.size))
        test_counts.append(int(test_idx.size))

    arr = np.asarray(ics, dtype=np.float64)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        mean = median = std = mn = mx = float("nan")
        pos_frac = 0.0
    else:
        mean = float(finite.mean())
        median = float(np.median(finite))
        std = float(finite.std(ddof=1)) if finite.size > 1 else float("nan")
        mn = float(finite.min())
        mx = float(finite.max())
        pos_frac = float((finite > 0.0).mean())

    return PurgedKFoldReport(
        k=k,
        horizon_rows=horizon_rows,
        embargo_rows=embargo_rows,
        ic_per_fold=tuple(float(x) for x in ics),
        ic_mean=mean,
        ic_median=median,
        ic_std=std,
        ic_min=mn,
        ic_max=mx,
        pos_fold_frac=pos_frac,
        n_rows_total=n,
        n_train_rows_per_fold=tuple(train_counts),
        n_test_rows_per_fold=tuple(test_counts),
    )
