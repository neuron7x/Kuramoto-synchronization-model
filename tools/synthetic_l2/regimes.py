# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Depth-mass concentration regimes for the synthetic L2 generator.

Each regime is a deterministic, seeded sampler that returns a strictly
positive ``(N,)`` depth array. Concentration profiles (uniform, heavy-tail,
winner-takes-most, bimodal) cover the qualitative space exercised by
``core.kuramoto.capital_weighted`` (β estimation, capital ratio, look-ahead
guard) without hitting any real exchange.

Determinism contract
--------------------
All public regime functions accept a ``numpy.random.Generator`` and never
read process-global RNG state. With identical generator state and identical
parameters they return bit-identical arrays.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "DepthArray",
    "uniform_depth",
    "pareto_depth",
    "winner_takes_most_depth",
    "bimodal_depth",
]

DepthArray = NDArray[np.float64]

_POSITIVE_FLOOR: Final[float] = 1e-9
"""Minimum positive depth — guards against zero-mass nodes that would break
:func:`core.kuramoto.capital_weighted.compute_capital_ratio` and produce
ill-defined Gini concentrations."""


def _validate_n(n: int) -> None:
    if not isinstance(n, int):
        raise TypeError(f"n must be int, got {type(n).__name__}.")
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}.")


def _ensure_positive(arr: DepthArray) -> DepthArray:
    """Floor strictly-positive (pre-existing positives untouched)."""
    # bounds: tooling-layer floor; protects downstream Gini / capital-ratio
    # consumers from divide-by-zero. Not a physics invariant.
    out: DepthArray = np.maximum(arr.astype(np.float64, copy=False), _POSITIVE_FLOOR)
    if not np.isfinite(out).all():
        raise ValueError("regime produced non-finite depth values.")
    return out


def uniform_depth(
    n: int,
    mean: float,
    jitter: float,
    rng: np.random.Generator,
) -> DepthArray:
    """Approximately uniform depth distribution.

    Parameters
    ----------
    n:
        Number of nodes (instruments).
    mean:
        Target mean depth mass per node, strictly positive.
    jitter:
        Multiplicative log-normal jitter standard deviation in ``[0, 1]``.
        ``0.0`` returns an exactly uniform vector ``(mean, mean, ..., mean)``.
    rng:
        Seeded NumPy generator.

    Returns
    -------
    DepthArray
        Strictly positive ``(n,)`` array centred on ``mean``.

    Notes
    -----
    Concentration metric (Gini) is small by construction: a tight log-normal
    perturbation around a single scale produces a near-equal allocation.
    """
    _validate_n(n)
    if not np.isfinite(mean) or mean <= 0.0:
        raise ValueError(f"mean must be finite and > 0, got {mean!r}.")
    if not np.isfinite(jitter) or jitter < 0.0 or jitter > 1.0:
        raise ValueError(f"jitter must lie in [0, 1], got {jitter!r}.")

    if jitter == 0.0:
        return _ensure_positive(np.full(n, float(mean), dtype=np.float64))

    log_noise = rng.normal(loc=0.0, scale=jitter, size=n).astype(np.float64, copy=False)
    arr: DepthArray = mean * np.exp(log_noise)
    return _ensure_positive(arr)


def pareto_depth(
    n: int,
    alpha: float,
    rng: np.random.Generator,
) -> DepthArray:
    """Heavy-tail Pareto-distributed depth (power-law shape ``alpha``).

    Parameters
    ----------
    n:
        Number of nodes.
    alpha:
        Pareto shape parameter, must be > 0. Smaller ``alpha`` ⇒ heavier
        tail ⇒ higher Gini. Typical research values: 1.0–2.5.
    rng:
        Seeded NumPy generator.

    Returns
    -------
    DepthArray
        Strictly positive ``(n,)`` Pareto sample (offset by 1 so the
        minimum mass is 1.0 before flooring).

    Notes
    -----
    Uses ``rng.pareto`` which returns ``X-1`` for shape ``α``; we add ``1.0``
    so depths are bounded below by 1 before the positive floor.
    """
    _validate_n(n)
    if not np.isfinite(alpha) or alpha <= 0.0:
        raise ValueError(f"alpha must be finite and > 0, got {alpha!r}.")

    sample: DepthArray = rng.pareto(alpha, size=n).astype(np.float64, copy=False) + 1.0
    return _ensure_positive(sample)


def winner_takes_most_depth(
    n: int,
    dominance: float,
    rng: np.random.Generator,
) -> DepthArray:
    """One node holds a fraction ``dominance`` of total depth mass.

    Parameters
    ----------
    n:
        Number of nodes; must be ``>= 2`` (otherwise dominance is trivial).
    dominance:
        Fraction of total mass concentrated in the winner; must be in
        ``[0.5, 0.9]``.
    rng:
        Seeded NumPy generator (used to permute which node is the winner
        and to add tiny log-normal jitter to losers).

    Returns
    -------
    DepthArray
        Strictly positive ``(n,)`` array. The winner's index is drawn
        uniformly via ``rng.integers``; the remaining mass is split nearly
        evenly with mild log-normal jitter so loser depths are not all
        identical (which would violate generic-position assumptions in
        downstream Ricci/spectral kernels).
    """
    _validate_n(n)
    if n < 2:
        raise ValueError(f"winner_takes_most_depth requires n >= 2, got {n}.")
    if not np.isfinite(dominance) or not (0.5 <= dominance <= 0.9):
        raise ValueError(f"dominance must lie in [0.5, 0.9], got {dominance!r}.")

    total = 1.0  # arbitrary unit mass; downstream code is scale-free
    winner_mass = dominance * total
    loser_total = (1.0 - dominance) * total
    base_loser = loser_total / float(n - 1)
    jitter = rng.normal(loc=0.0, scale=0.05, size=n - 1).astype(np.float64, copy=False)
    losers: DepthArray = base_loser * np.exp(jitter)
    # bounds: rescale jittered losers so their sum equals loser_total exactly,
    # preserving the dominance contract.
    losers *= loser_total / float(losers.sum())

    winner_idx = int(rng.integers(low=0, high=n))
    out: DepthArray = np.empty(n, dtype=np.float64)
    out[winner_idx] = winner_mass
    j = 0
    for i in range(n):
        if i == winner_idx:
            continue
        out[i] = losers[j]
        j += 1

    return _ensure_positive(out)


def bimodal_depth(
    n: int,
    ratio: float,
    rng: np.random.Generator,
) -> DepthArray:
    """Two clusters: a fraction ``ratio`` of nodes are "high", rest are "low".

    Parameters
    ----------
    n:
        Number of nodes; must be ``>= 2``.
    ratio:
        Fraction of nodes in the high cluster; must be in ``(0, 1)``. The
        high cluster has 10x the per-node mass of the low cluster.
    rng:
        Seeded NumPy generator.

    Returns
    -------
    DepthArray
        Strictly positive ``(n,)`` array with at least one node in each
        cluster (boundary cases ``ratio·n < 1`` are clamped to ``n_high=1``).

    Notes
    -----
    The cluster contrast is fixed at 10×; this is empirically sufficient to
    push the Gini coefficient above the uniform-regime ceiling while
    remaining below the Pareto / winner-takes-most floor. Cluster identities
    are scrambled by ``rng.permutation`` so node index carries no
    information.
    """
    _validate_n(n)
    if n < 2:
        raise ValueError(f"bimodal_depth requires n >= 2, got {n}.")
    if not np.isfinite(ratio) or not (0.0 < ratio < 1.0):
        raise ValueError(f"ratio must lie in (0, 1), got {ratio!r}.")

    # bounds: at least one node per cluster (clamped); pure-empty clusters
    # would degenerate to the uniform regime.
    n_high = int(round(ratio * n))
    n_high = max(1, min(n_high, n - 1))

    high_mass = 10.0
    low_mass = 1.0
    base = np.concatenate(
        [
            np.full(n_high, high_mass, dtype=np.float64),
            np.full(n - n_high, low_mass, dtype=np.float64),
        ]
    )
    log_noise = rng.normal(loc=0.0, scale=0.05, size=n).astype(np.float64, copy=False)
    base = base * np.exp(log_noise)
    permuted: DepthArray = rng.permutation(base).astype(np.float64, copy=False)
    return _ensure_positive(permuted)
