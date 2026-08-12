# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Null falsification audit for a strategy's return stream.

Four orthogonal null families are executed against a single observed
Sharpe and an empirical p-value is computed for each:

1. **Permuted target** — shuffle realised returns; keep signal fixed.
2. **Block-permuted signal** — stationary bootstrap of signal blocks
   preserving autocorrelation; match to true targets.
3. **Inverted signal** — negate the signal; should collapse Sharpe.
4. **Lag surrogate** — lag the signal by a random integer in
   ``[min_lag, max_lag]``; destroys the information edge.

Each family uses ``n_bootstrap`` resamples under a seeded
:class:`numpy.random.Generator`. The result is a frozen dataclass
carrying the null distribution, the observed statistic, and
:math:`p = (\\#\\{null \\ge observed\\} + 1) / (B + 1)` with the
standard Davison & Hinkley (1997) continuity correction.

Pure-function API. No I/O. No writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

NullFamily = Literal[
    "permuted_target",
    "block_permuted_signal",
    "inverted_signal",
    "lag_surrogate",
]


@dataclass(frozen=True)
class NullAuditResult:
    """One null family's bootstrap distribution and p-value."""

    family: NullFamily
    observed_sharpe: float
    null_sharpes: tuple[float, ...]
    p_value: float
    n_bootstrap: int


def _sharpe(returns: NDArray[np.float64], periods_per_year: int) -> float:
    """Annualised Sharpe with ddof=1; returns 0.0 on degenerate variance."""
    if returns.size < 2:
        return 0.0
    std = returns.std(ddof=1)
    if std <= 0 or not np.isfinite(std):
        return 0.0
    return float(returns.mean() / std * np.sqrt(periods_per_year))


def _strategy_returns(
    signal: NDArray[np.float64],
    target: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Element-wise product assuming ``signal`` already respects lag."""
    if signal.shape != target.shape:
        raise ValueError(f"signal/target shape mismatch: {signal.shape} vs {target.shape}")
    return signal * target


def _p_value(observed: float, null: NDArray[np.float64]) -> float:
    """One-sided upper-tail p-value with +1 continuity correction."""
    exceedances = int((null >= observed).sum())
    return float((exceedances + 1) / (null.size + 1))


def _stationary_bootstrap_indices(
    n: int,
    mean_block: int,
    rng: np.random.Generator,
) -> NDArray[np.int64]:
    """Politis & Romano (1994) stationary bootstrap indices.

    Draws geometric block lengths with mean ``mean_block`` and random
    start points uniform on ``[0, n)``. Returns ``n`` indices.
    """
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}")
    if mean_block < 1:
        raise ValueError(f"mean_block must be >= 1, got {mean_block}")
    p = 1.0 / mean_block
    idx = np.empty(n, dtype=np.int64)
    current = int(rng.integers(0, n))
    for i in range(n):
        idx[i] = current
        if rng.random() < p:
            current = int(rng.integers(0, n))
        else:
            current = (current + 1) % n
    return idx


def _block_permute(
    signal: NDArray[np.float64],
    mean_block: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """Stationary bootstrap of a 1-D signal preserving autocorrelation."""
    idx = _stationary_bootstrap_indices(signal.size, mean_block, rng)
    return signal[idx]


def run_null_falsification_audit(
    signal: NDArray[np.float64],
    target: NDArray[np.float64],
    *,
    n_bootstrap: int = 1000,
    seed: int = 42,
    periods_per_year: int = 252,
    mean_block: int = 21,
    lag_range: tuple[int, int] = (5, 60),
) -> tuple[NullAuditResult, ...]:
    """Run the four-family null audit.

    Parameters
    ----------
    signal
        1-D array of the strategy's lagged position. Must not contain
        future information; no additional lag is applied here.
    target
        1-D array of realised returns, aligned with ``signal``.
    n_bootstrap
        Number of null resamples per family.
    seed
        Seed for the shared PCG64 stream (deterministic audit).
    periods_per_year
        Sharpe annualisation factor (252 for daily, 365 for 24x7, etc.).
    mean_block
        Mean block length for the stationary bootstrap (family 2).
    lag_range
        Inclusive ``[min_lag, max_lag]`` for the lag-surrogate family.

    Returns
    -------
    tuple of four :class:`NullAuditResult`, one per family.
    """
    sig = np.asarray(signal, dtype=np.float64)
    tgt = np.asarray(target, dtype=np.float64)
    if sig.ndim != 1 or tgt.ndim != 1:
        raise ValueError(f"signal and target must be 1-D, got {sig.shape} and {tgt.shape}")
    if sig.size != tgt.size:
        raise ValueError(f"signal/target length mismatch: {sig.size} vs {tgt.size}")
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be >= 1, got {n_bootstrap}")
    lo, hi = lag_range
    if not 1 <= lo <= hi <= sig.size // 2:
        raise ValueError(
            f"lag_range must satisfy 1 <= lo <= hi <= n/2, got ({lo}, {hi}) with n={sig.size}"
        )

    rng = np.random.default_rng(seed)
    observed_returns = _strategy_returns(sig, tgt)
    observed_sharpe = _sharpe(observed_returns, periods_per_year)

    def _collect(
        family: NullFamily,
        distribution: NDArray[np.float64],
    ) -> NullAuditResult:
        return NullAuditResult(
            family=family,
            observed_sharpe=observed_sharpe,
            null_sharpes=tuple(float(x) for x in distribution),
            p_value=_p_value(observed_sharpe, distribution),
            n_bootstrap=n_bootstrap,
        )

    # Family 1: permuted target.
    null_1 = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        perm = rng.permutation(tgt)
        null_1[b] = _sharpe(_strategy_returns(sig, perm), periods_per_year)

    # Family 2: block-permuted signal.
    null_2 = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        perm = _block_permute(sig, mean_block, rng)
        null_2[b] = _sharpe(_strategy_returns(perm, tgt), periods_per_year)

    # Family 3: inverted signal — *degenerate* null (single-point collapse).
    # We still bootstrap-sample the magnitude to get a distribution of
    # inverted-signal performance across reshuffles of the time index.
    null_3 = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        reindex = rng.permutation(sig.size)
        null_3[b] = _sharpe(_strategy_returns(-sig[reindex], tgt[reindex]), periods_per_year)

    # Family 4: lag surrogate.
    null_4 = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        lag = int(rng.integers(lo, hi + 1))
        lagged = np.roll(sig, lag)
        null_4[b] = _sharpe(_strategy_returns(lagged, tgt), periods_per_year)

    return (
        _collect("permuted_target", null_1),
        _collect("block_permuted_signal", null_2),
        _collect("inverted_signal", null_3),
        _collect("lag_surrogate", null_4),
    )
