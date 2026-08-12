# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""White's Reality Check for data-snooping over a set of strategies.

When the *best* of ``K`` candidate strategies is selected and reported, its
in-sample superiority is contaminated by the search itself: with enough
candidates, some strategy beats a benchmark by luck alone. A naive per-strategy
t-test on the winner is therefore optimistically biased and routinely
manufactures spurious significance.

White's Reality Check (White, 2000, *Econometrica* 68(5):1097-1126) tests the
composite null

    H0: max_k E[f_k] ≤ 0

where ``f_k,t`` is strategy ``k``'s performance differential against the
benchmark at time ``t`` (higher = better). The test statistic is the studentised
best mean ``V = √T · max_k mean_t f_k,t`` and its null distribution is obtained
by a **stationary / circular block bootstrap** that resamples the rows of ``f``
and **re-centres** each strategy by its own mean (imposing H0). The p-value is
the bootstrap tail mass at or beyond the observed ``V``.

This is the strategy-selection counterpart to the Deflated Sharpe Ratio (already
in ``research/microstructure/robustness.deflated_sharpe``): DSR haircuts a single
Sharpe by the number of trials; the Reality Check works directly on the joint
bootstrap of the whole candidate set, so it also captures cross-strategy
dependence via the block structure. No result is admissible without one of these
corrections (CHECKPOINT: "no result without null models and baselines").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

__all__ = ["WhiteRealityCheckResult", "white_reality_check"]


@dataclass(frozen=True)
class WhiteRealityCheckResult:
    """Outcome of a White Reality Check run.

    Attributes:
        p_value: Bootstrap p-value for H0 (max strategy has no edge). Small ⇒
            the best strategy survives the data-snooping correction.
        statistic: Observed ``V = √T · max_k mean_t f_k,t``.
        best_strategy: Index of the strategy attaining the max mean differential.
        n_periods: Number of time periods ``T``.
        n_strategies: Number of candidate strategies ``K``.
        n_bootstrap: Bootstrap resamples used.
        block_size: Circular-block length (dependence-preserving).
    """

    p_value: float
    statistic: float
    best_strategy: int
    n_periods: int
    n_strategies: int
    n_bootstrap: int
    block_size: int


def _validate(performance: npt.NDArray[np.float64], n_bootstrap: int, block_size: int) -> None:
    if performance.ndim != 2:
        raise ValueError(
            f"white_reality_check: performance must be 2-D (T, K); "
            f"got ndim={performance.ndim} shape={performance.shape}"
        )
    t_periods, k_strategies = performance.shape
    if t_periods < 2:
        raise ValueError(
            f"white_reality_check: need ≥ 2 time periods to bootstrap, got T={t_periods}"
        )
    if k_strategies < 1:
        raise ValueError(f"white_reality_check: need ≥ 1 strategy, got K={k_strategies}")
    if not bool(np.all(np.isfinite(performance))):
        raise ValueError(
            "white_reality_check: performance contains non-finite values (NaN/Inf); "
            "fail-closed — a snooping correction on undefined returns is meaningless"
        )
    if n_bootstrap < 1:
        raise ValueError(f"white_reality_check: n_bootstrap must be ≥ 1, got {n_bootstrap}")
    if not 1 <= block_size <= t_periods:
        raise ValueError(
            f"white_reality_check: block_size must lie in [1, T]={t_periods}, got {block_size}"
        )


def white_reality_check(
    performance: npt.ArrayLike,
    *,
    n_bootstrap: int = 2000,
    block_size: int = 10,
    seed: int = 0,
) -> WhiteRealityCheckResult:
    """Run White's Reality Check on a ``(T, K)`` matrix of performance differentials.

    Args:
        performance: ``performance[t, k]`` is strategy ``k``'s performance
            differential versus the benchmark at period ``t`` (higher is better,
            e.g. excess return or negative-loss difference).
        n_bootstrap: Number of circular-block bootstrap resamples.
        block_size: Circular-block length; preserves serial/cross dependence.
            ``1`` reduces to an i.i.d. bootstrap.
        seed: Seed for the bootstrap RNG (deterministic output).

    Returns:
        A :class:`WhiteRealityCheckResult`. ``p_value`` uses the
        ``(count + 1)/(n_bootstrap + 1)`` convention, so it lies in ``(0, 1]``
        and never reports an impossible exact zero.

    Raises:
        ValueError: on non-2-D / fewer than 2 periods / no strategies /
            non-finite input / non-positive bootstrap count / out-of-range
            block size. Fail-closed; no silent repair.
    """
    perf = np.asarray(performance, dtype=np.float64)
    _validate(perf, n_bootstrap, block_size)

    t_periods, k_strategies = perf.shape
    sqrt_t = float(np.sqrt(t_periods))
    mean_diff = perf.mean(axis=0)  # (K,)
    best_strategy = int(np.argmax(mean_diff))
    statistic = sqrt_t * float(mean_diff[best_strategy])

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(t_periods / block_size))
    offsets = np.arange(block_size)
    exceed = 0
    for _ in range(n_bootstrap):
        starts = rng.integers(0, t_periods, size=n_blocks)
        idx = (starts[:, None] + offsets[None, :]).ravel()[:t_periods] % t_periods
        # Re-centre by each strategy's own mean → imposes the H0 of no edge.
        boot_stat = sqrt_t * float((perf[idx].mean(axis=0) - mean_diff).max())
        if boot_stat >= statistic:
            exceed += 1

    p_value = (exceed + 1) / (n_bootstrap + 1)
    return WhiteRealityCheckResult(
        p_value=p_value,
        statistic=statistic,
        best_strategy=best_strategy,
        n_periods=t_periods,
        n_strategies=k_strategies,
        n_bootstrap=n_bootstrap,
        block_size=block_size,
    )
