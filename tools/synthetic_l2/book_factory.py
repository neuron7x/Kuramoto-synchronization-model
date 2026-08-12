# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic ``L2DepthSnapshot`` factory.

Produces fully-validated :class:`core.kuramoto.capital_weighted.L2DepthSnapshot`
instances from a chosen depth-mass regime. The factory is deterministic
under a fixed seed and never touches network or filesystem.

Pipeline
--------
1. Draw per-node *total* depth mass from the chosen regime (positive only).
2. Distribute that mass across ``n_levels`` per side using a geometric
   level-decay (level 0 deepest).
3. Apply optional bid/ask asymmetry (``bid_share = 0.5`` is symmetric).
4. Draw mid prices from the chosen distribution (``"lognormal"`` or
   ``"uniform"``).
5. Validate via the snapshot's own constructor contract.

The level-decay factor and the regime parameters carry sensible research
defaults; callers override only what they need.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import L2DepthSnapshot, _validate_snapshot

from .regimes import (
    DepthArray,
    bimodal_depth,
    pareto_depth,
    uniform_depth,
    winner_takes_most_depth,
)

__all__ = [
    "RegimeName",
    "MidPriceDistribution",
    "RegimeSpec",
    "synthesize_l2_snapshot",
]

RegimeName = Literal["uniform", "pareto", "winner", "bimodal"]
MidPriceDistribution = Literal["lognormal", "uniform"]

_DEFAULT_LEVEL_DECAY: Final[float] = 0.6
"""Geometric decay factor for per-level depth share.

Level 0 holds the largest share; level k holds ``decay**k`` weight before
normalisation. ``0.6`` mimics typical limit-order-book empirical decay
(Bouchaud, Farmer, Lillo) without claiming any specific market.
"""

_DEFAULT_MID_PRICE_LOC: Final[float] = 100.0
"""Geometric mean of the lognormal mid-price draw (in unitless price)."""

_DEFAULT_MID_PRICE_SIGMA: Final[float] = 0.5
"""Lognormal sigma for mid-price draw."""


@dataclass(frozen=True, slots=True)
class RegimeSpec:
    """Regime selection record.

    Attributes
    ----------
    name:
        Regime identifier.
    params:
        Regime-specific parameters (validated below).
    """

    name: RegimeName
    params: dict[str, float]


def _draw_total_depth(
    spec: RegimeSpec,
    n_nodes: int,
    rng: np.random.Generator,
) -> DepthArray:
    if spec.name == "uniform":
        mean = float(spec.params.get("mean", 1.0))
        jitter = float(spec.params.get("jitter", 0.1))
        return uniform_depth(n_nodes, mean=mean, jitter=jitter, rng=rng)
    if spec.name == "pareto":
        alpha = float(spec.params.get("alpha", 1.5))
        return pareto_depth(n_nodes, alpha=alpha, rng=rng)
    if spec.name == "winner":
        dominance = float(spec.params.get("dominance", 0.7))
        return winner_takes_most_depth(n_nodes, dominance=dominance, rng=rng)
    if spec.name == "bimodal":
        ratio = float(spec.params.get("ratio", 0.3))
        return bimodal_depth(n_nodes, ratio=ratio, rng=rng)
    # bounds: exhaustive over RegimeName Literal; a runtime-only branch for
    # callers passing an untyped string.
    raise ValueError(f"unknown regime: {spec.name!r}")


def _level_weights(n_levels: int, decay: float) -> NDArray[np.float64]:
    if n_levels <= 0:
        raise ValueError(f"n_levels must be > 0, got {n_levels}.")
    if not np.isfinite(decay) or not (0.0 < decay <= 1.0):
        raise ValueError(f"level_decay must lie in (0, 1], got {decay!r}.")
    raw: NDArray[np.float64] = np.power(decay, np.arange(n_levels, dtype=np.float64))
    total = float(raw.sum())
    if total <= 0.0:  # pragma: no cover — geometric series with decay>0 is positive.
        raise ValueError("level weights collapsed to zero.")
    return raw / total


def _draw_mid_prices(
    distribution: MidPriceDistribution,
    n_nodes: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    if distribution == "lognormal":
        prices: NDArray[np.float64] = (
            _DEFAULT_MID_PRICE_LOC * np.exp(rng.normal(0.0, _DEFAULT_MID_PRICE_SIGMA, size=n_nodes))
        ).astype(np.float64, copy=False)
        return prices
    if distribution == "uniform":
        prices = rng.uniform(low=10.0, high=1000.0, size=n_nodes).astype(np.float64, copy=False)
        return prices
    raise ValueError(f"unknown mid_price_distribution: {distribution!r}")


def synthesize_l2_snapshot(
    *,
    n_nodes: int = 64,
    n_levels: int = 5,
    regime: RegimeName | RegimeSpec = "pareto",
    mid_price_distribution: MidPriceDistribution = "lognormal",
    timestamp_ns: int = 0,
    seed: int = 20260425,
    bid_share: float = 0.5,
    level_decay: float = _DEFAULT_LEVEL_DECAY,
) -> L2DepthSnapshot:
    """Build a deterministic synthetic :class:`L2DepthSnapshot`.

    Parameters
    ----------
    n_nodes:
        Number of instruments. Default ``64``.
    n_levels:
        Number of price levels per side. Default ``5``.
    regime:
        Either a regime name (string) using default parameters, or a
        :class:`RegimeSpec` for custom parameters.
    mid_price_distribution:
        ``"lognormal"`` (default) or ``"uniform"``.
    timestamp_ns:
        Snapshot epoch in nanoseconds. Default ``0`` (suitable for tests).
    seed:
        Seed for the internal NumPy ``Generator``. Determinism contract:
        identical seed + identical parameters ⇒ identical snapshot.
    bid_share:
        Fraction of total per-node mass allocated to the bid side. Must lie
        in ``(0, 1)``; default ``0.5`` (symmetric).
    level_decay:
        Geometric decay factor across levels; default
        ``_DEFAULT_LEVEL_DECAY``.

    Returns
    -------
    L2DepthSnapshot
        Validated by the same routine that ``capital_weighted`` uses
        internally — guaranteed shape, dtype, finiteness, and sign.
    """
    if not isinstance(timestamp_ns, int):
        raise TypeError(f"timestamp_ns must be int, got {type(timestamp_ns).__name__}.")
    if timestamp_ns < 0:
        raise ValueError(f"timestamp_ns must be >= 0, got {timestamp_ns}.")
    if not isinstance(seed, int):
        raise TypeError(f"seed must be int, got {type(seed).__name__}.")
    if not np.isfinite(bid_share) or not (0.0 < bid_share < 1.0):
        raise ValueError(f"bid_share must lie in (0, 1), got {bid_share!r}.")

    spec = regime if isinstance(regime, RegimeSpec) else RegimeSpec(name=regime, params={})
    rng = np.random.default_rng(seed)

    total_depth = _draw_total_depth(spec, n_nodes, rng)
    weights = _level_weights(n_levels, level_decay)

    bid_total = total_depth * float(bid_share)
    ask_total = total_depth * float(1.0 - bid_share)
    bid_sizes: NDArray[np.float64] = np.outer(bid_total, weights).astype(np.float64, copy=False)
    ask_sizes: NDArray[np.float64] = np.outer(ask_total, weights).astype(np.float64, copy=False)

    mid_prices = _draw_mid_prices(mid_price_distribution, n_nodes, rng)

    snapshot = L2DepthSnapshot(
        timestamp_ns=int(timestamp_ns),
        bid_sizes=bid_sizes,
        ask_sizes=ask_sizes,
        mid_prices=mid_prices,
    )
    # Re-use the exact validation contract from capital_weighted to guarantee
    # the snapshot is admissible at the physics boundary.
    _validate_snapshot(snapshot)
    return snapshot
