# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CPCV + PBO + PSR suite bound to the frozen Kuramoto evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from research.robustness.cpcv import (
    _newey_west_auto_lag,
    estimate_pbo,
    probabilistic_sharpe_ratio,
    probabilistic_sharpe_ratio_hac,
)

from .kuramoto_contract import KuramotoRobustnessContract

PBO_PASS_THRESHOLD: Final[float] = 0.50
PSR_PASS_THRESHOLD: Final[float] = 0.95
LOO_PBO_PASS_THRESHOLD: Final[float] = 0.50


PBO_TAUTOLOGICAL_CUTOFF: Final[int] = 3
PBO_WEAK_CUTOFF: Final[int] = 5


def _pbo_interpretation(n_candidates: int) -> str:
    """Label a PBO measurement by its candidate count.

    Fewer than 3 strategies: 'tautological' (best-IS is trivially best).
    Fewer than 5 strategies: 'weak' (low statistical power).
    5 or more: 'admissible'.
    """
    if n_candidates < PBO_TAUTOLOGICAL_CUTOFF:
        return "tautological"
    if n_candidates < PBO_WEAK_CUTOFF:
        return "weak"
    return "admissible"


@dataclass(frozen=True)
class KuramotoCPCVResult:
    """Aggregate of the CPCV/PBO/PSR suite on frozen evidence."""

    fold_sharpes: tuple[float, ...]
    pbo: float
    pbo_pass: bool
    pbo_candidate_count: int
    pbo_interpretation: str
    psr_daily: float
    psr_pass: bool
    psr_hac_daily: float
    psr_hac_pass: bool
    psr_hac_lag: int
    annualised_sharpe: float
    n_bars: int
    n_folds: int
    loo_pbo: float | None
    loo_pbo_pass: bool
    loo_n_strategies: int
    loo_pbo_interpretation: str


def _fold_oos_matrix(fold_sharpes: tuple[float, ...]) -> NDArray[np.float64]:
    """Build an OOS matrix from per-fold Sharpe values for PBO estimation.

    The frozen evidence bundle ships one Sharpe per walk-forward fold
    (single anchor strategy). To stress PBO we build a 2-strategy family:
    anchor vs shifted-by-median mirror — which is a conservative upper
    bound since the two "strategies" are highly correlated. A more
    generous PBO would require the full parameter grid from the spike.
    """
    arr = np.asarray(fold_sharpes, dtype=np.float64)
    mirror = arr - float(np.median(arr))
    return np.column_stack([arr, mirror])


def _loo_oos_matrix(loo_grid: pd.DataFrame) -> NDArray[np.float64]:
    """Build an OOS matrix of (folds × strategies) from the LOO grid.

    Each non-baseline LOO row is one strategy variant whose per-fold
    Sharpes live in columns ``fold1..fold5``. We transpose so rows are
    CPCV paths (folds) and columns are strategies, matching
    :func:`research.robustness.cpcv.estimate_pbo` shape expectations.
    The baseline row is excluded: including it would guarantee best-IS
    capture every time and trivialise the PBO.
    """
    perturbations = loo_grid[loo_grid["loo_type"] != "baseline_full"]
    folds = perturbations[["fold1", "fold2", "fold3", "fold4", "fold5"]].to_numpy(dtype=np.float64)
    # folds shape is (n_strategies, n_folds); transpose to (n_folds, n_strategies)
    out: NDArray[np.float64] = folds.T
    return out


def run_kuramoto_cpcv_suite(
    contract: KuramotoRobustnessContract,
) -> KuramotoCPCVResult:
    """Compute CPCV-family metrics against the frozen contract.

    The frozen bundle already carries OOS fold Sharpes (spike walk-
    forward) and the full daily strategy equity. We therefore reuse the
    pre-computed fold sharpes for PBO and the daily return stream for
    PSR. No re-simulation is performed — this suite is *read-only* on
    frozen artifacts by design.

    When the contract carries the optional LOO grid, a *second* PBO is
    computed on the real (folds × LOO-perturbations) OOS matrix — this
    is the honest Bailey et al. PBO and is non-trivial by construction.
    """
    daily = contract.daily_strategy_returns().to_numpy(dtype=np.float64)
    fold_sharpes = tuple(float(s) for s in contract.fold_metrics["sharpe"].to_numpy())
    psr = probabilistic_sharpe_ratio(
        daily,
        sr_benchmark=0.0,
        periods_per_year=252,
    )
    psr_hac_lag = _newey_west_auto_lag(int(daily.size))
    psr_hac = probabilistic_sharpe_ratio_hac(
        daily,
        sr_benchmark=0.0,
        periods_per_year=252,
        lag=psr_hac_lag,
    )
    oos = _fold_oos_matrix(fold_sharpes)
    pbo = estimate_pbo(oos)
    std = float(np.std(daily, ddof=1))
    sr = float(np.mean(daily) / std * np.sqrt(252)) if std > 0 and np.isfinite(std) else 0.0

    loo_pbo: float | None = None
    loo_pbo_pass = True
    loo_n_strategies = 0
    if contract.loo_grid is not None:
        loo_oos = _loo_oos_matrix(contract.loo_grid)
        loo_n_strategies = int(loo_oos.shape[1])
        if loo_oos.shape[0] >= 2 and loo_n_strategies >= 2:
            loo_pbo = estimate_pbo(loo_oos)
            loo_pbo_pass = loo_pbo < LOO_PBO_PASS_THRESHOLD

    # The fold-mirror PBO uses exactly 2 "strategies" (anchor + median-
    # shifted mirror); by construction this is below PBO_TAUTOLOGICAL_CUTOFF
    # and the interpretation is always 'tautological'. It is retained as
    # a sanity-check baseline; the LOO-grid PBO is the decision-grade one.
    fold_mirror_candidate_count = 2
    return KuramotoCPCVResult(
        fold_sharpes=fold_sharpes,
        pbo=pbo,
        pbo_pass=pbo < PBO_PASS_THRESHOLD,
        pbo_candidate_count=fold_mirror_candidate_count,
        pbo_interpretation=_pbo_interpretation(fold_mirror_candidate_count),
        psr_daily=psr,
        psr_pass=(psr >= PSR_PASS_THRESHOLD) if np.isfinite(psr) else False,
        psr_hac_daily=psr_hac,
        psr_hac_pass=(psr_hac >= PSR_PASS_THRESHOLD) if np.isfinite(psr_hac) else False,
        psr_hac_lag=psr_hac_lag,
        annualised_sharpe=sr,
        n_bars=int(daily.size),
        n_folds=len(fold_sharpes),
        loo_pbo=loo_pbo,
        loo_pbo_pass=loo_pbo_pass,
        loo_n_strategies=loo_n_strategies,
        loo_pbo_interpretation=_pbo_interpretation(loo_n_strategies),
    )
