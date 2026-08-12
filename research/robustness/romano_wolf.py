# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Romano-Wolf stepwise multiple testing (FWER-controlled strategy selection).

White's Reality Check and Hansen's SPA answer a *composite* question — "is the
**best** of K strategies better than the benchmark?" — and return a single
p-value. They do not tell you **which** strategies have genuine edge. Reporting
every strategy that individually clears a threshold instead inflates the
family-wise error rate (FWER): with K candidates at level α the chance of at
least one false discovery approaches ``1 − (1 − α)^K`` → ~1 for large K.

Romano & Wolf (2005, *Econometrica* 73(4):1237-1282, "Stepwise Multiple Testing
as Formalized Data Snooping") give a stepdown procedure that identifies the full
set of out-performing strategies while controlling

    FWER = P(reject at least one true null) ≤ α   (asymptotically),

without assuming independence — cross-strategy dependence is captured by a joint
block bootstrap of the studentised statistics. This is the per-strategy
counterpart to the composite reality check already in this package
(``white_reality_check``) and the Kuramoto-scoped Hansen SPA in
``core/kuramoto/oos_validation.spa_test``.

Procedure (studentised stepdown):
  1. wₖ = √T · mean_t f_k,t / sₖ          (sₖ = sample SD of strategy k)
  2. Block-bootstrap centred studentised statistics z*_{k,b}.
  3. Step j: cⱼ = (1−α) quantile of max over the not-yet-rejected set of z*;
     reject every active k with wₖ > cⱼ. Repeat until no new rejection.
The not-yet-rejected ("active") set shrinks each step, so later critical values
are smaller — a strictly more powerful test than a single-step max correction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

__all__ = ["RomanoWolfResult", "romano_wolf_stepm"]


@dataclass(frozen=True)
class RomanoWolfResult:
    """Outcome of a Romano-Wolf stepdown run.

    Attributes:
        rejected: Boolean mask (length K); True ⇒ strategy k has edge at FWER ≤ α.
        statistics: Studentised one-sided statistics wₖ = √T·mean/SD.
        critical_values: The stepdown critical value applied at each round.
        n_rejected: Number of strategies rejected (= edge-bearing).
        alpha: Target family-wise error rate.
        n_periods: Number of periods T.
        n_strategies: Number of strategies K.
        n_bootstrap: Bootstrap resamples used.
        block_size: Circular-block length.
    """

    rejected: npt.NDArray[np.bool_]
    statistics: npt.NDArray[np.float64]
    critical_values: tuple[float, ...]
    n_rejected: int
    alpha: float
    n_periods: int
    n_strategies: int
    n_bootstrap: int
    block_size: int


def _validate(
    performance: npt.NDArray[np.float64],
    alpha: float,
    n_bootstrap: int,
    block_size: int,
) -> None:
    if performance.ndim != 2:
        raise ValueError(
            f"romano_wolf_stepm: performance must be 2-D (T, K); "
            f"got ndim={performance.ndim} shape={performance.shape}"
        )
    t_periods, k_strategies = performance.shape
    if t_periods < 2:
        raise ValueError(f"romano_wolf_stepm: need ≥ 2 periods, got T={t_periods}")
    if k_strategies < 1:
        raise ValueError(f"romano_wolf_stepm: need ≥ 1 strategy, got K={k_strategies}")
    if not bool(np.all(np.isfinite(performance))):
        raise ValueError(
            "romano_wolf_stepm: performance contains non-finite values (NaN/Inf); "
            "fail-closed — a snooping correction on undefined returns is meaningless"
        )
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"romano_wolf_stepm: alpha must lie in (0, 1), got {alpha}")
    if n_bootstrap < 1:
        raise ValueError(f"romano_wolf_stepm: n_bootstrap must be ≥ 1, got {n_bootstrap}")
    if not 1 <= block_size <= t_periods:
        raise ValueError(
            f"romano_wolf_stepm: block_size must lie in [1, T]={t_periods}, got {block_size}"
        )


def romano_wolf_stepm(
    performance: npt.ArrayLike,
    *,
    alpha: float = 0.05,
    n_bootstrap: int = 2000,
    block_size: int = 10,
    seed: int = 0,
) -> RomanoWolfResult:
    """Identify edge-bearing strategies with FWER ≤ ``alpha`` (Romano-Wolf 2005).

    Args:
        performance: ``performance[t, k]`` is strategy ``k``'s performance
            differential versus the benchmark at period ``t`` (higher better).
        alpha: Target family-wise error rate.
        n_bootstrap: Circular-block bootstrap resamples.
        block_size: Block length (preserves serial/cross dependence).
        seed: RNG seed (deterministic output).

    Returns:
        A :class:`RomanoWolfResult` whose ``rejected`` mask flags every strategy
        whose superiority survives the family-wise correction.

    Raises:
        ValueError: on non-2-D / <2 periods / no strategies / non-finite input /
            alpha∉(0,1) / non-positive bootstrap / out-of-range block size.
            Fail-closed; no silent repair.
    """
    perf = np.asarray(performance, dtype=np.float64)
    _validate(perf, alpha, n_bootstrap, block_size)

    t_periods, k_strategies = perf.shape
    sqrt_t = float(np.sqrt(t_periods))
    mean_diff = perf.mean(axis=0)
    std_diff = perf.std(axis=0, ddof=1)
    # A zero-variance strategy carries no testable signal: drive its statistic to
    # −inf so it can never be rejected (bounds: degenerate column, not physics).
    safe_std = np.where(std_diff > 0.0, std_diff, np.inf)
    statistics = sqrt_t * mean_diff / safe_std

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(t_periods / block_size))
    offsets = np.arange(block_size)
    boot = np.empty((n_bootstrap, k_strategies), dtype=np.float64)
    for b in range(n_bootstrap):
        starts = rng.integers(0, t_periods, size=n_blocks)
        idx = (starts[:, None] + offsets[None, :]).ravel()[:t_periods] % t_periods
        boot_mean = perf[idx].mean(axis=0)
        # Centre on the observed mean and studentise by the SAME SD → H0 of no edge.
        boot[b] = sqrt_t * (boot_mean - mean_diff) / safe_std

    rejected = np.zeros(k_strategies, dtype=np.bool_)
    critical_values: list[float] = []
    while True:
        active = ~rejected
        if not bool(active.any()):
            break
        max_active = boot[:, active].max(axis=1)
        crit = float(np.quantile(max_active, 1.0 - alpha))
        critical_values.append(crit)
        new_reject = active & (statistics > crit)
        if not bool(new_reject.any()):
            break
        rejected |= new_reject

    return RomanoWolfResult(
        rejected=rejected,
        statistics=statistics,
        critical_values=tuple(critical_values),
        n_rejected=int(rejected.sum()),
        alpha=alpha,
        n_periods=t_periods,
        n_strategies=k_strategies,
        n_bootstrap=n_bootstrap,
        block_size=block_size,
    )
