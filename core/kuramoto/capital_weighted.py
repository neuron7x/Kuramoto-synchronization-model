# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capital-weighted (β) Kuramoto coupling primitives — opt-in research module.

Status
------
EXPERIMENTAL. Pure NumPy. No alpha claim. Every primitive in this module is a
deterministic function of inputs; the module never registers itself with the
default :class:`KuramotoConfig` or :class:`KuramotoEngine` paths. Callers must
import and invoke explicitly.

Background
----------
Following Kathiravelu's adaptive-coupling formulation for trading-flow
crowding (SSRN), the Kuramoto coupling between two oscillators ``i`` and ``j``
is modulated by a capital concentration ratio derived from limit-order-book
depth (level-2). The functional form used here is

.. math::

    K_{ij}^{\beta}(t) = K_0 \\cdot \bigl(1 + \\gamma\\, r_{ij}(t)^{2\\delta}\bigr)^{(\beta - 1)/2}

with edgewise capital ratio :math:`r_{ij} = \\sqrt{r_i r_j}` and node-level
ratio :math:`r_i = m_i / \\mathrm{median}(m)` where :math:`m_i` is the L2 depth
mass (mid-price weighted bid+ask volume).

The shape parameter :math:`\beta` lives in ``[beta_min, beta_max]`` (the
default ``[0.25, 4.0]`` corresponds to the SSRN sensitivity sweep).
:math:`\beta = 1` exactly recovers the baseline coupling.

Invariants
----------
- ``K_ij`` is finite, non-negative, symmetric, zero on the diagonal
  (``INV-KBETA``).
- Uniform multiplicative depth scaling is invariant: scaling all depths by
  ``c > 0`` leaves :math:`K_{ij}^{\beta}` unchanged because the ratio
  :math:`r_i` and the Gini-derived :math:`\beta` are scale-free.
- Future-snapshot leakage is rejected when ``fail_on_future_l2=True``.

No-alpha disclaimer
-------------------
This module exposes a primitive for academic experimentation. It does not
constitute a trading signal nor a claim of out-of-sample edge. All defaults
preserve existing engine behavior because no GeoSync entry point auto-imports
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "L2DepthSnapshot",
    "CapitalWeightedCouplingConfig",
    "CapitalWeightedCouplingResult",
    "compute_l2_depth_mass",
    "estimate_scalar_beta",
    "compute_capital_ratio",
    "compute_k_beta",
    "build_capital_weighted_adjacency",
]


_FLOAT_FINITE_TOL: Final[float] = 1e-12


@dataclass(frozen=True, slots=True)
class L2DepthSnapshot:
    """Limit-order-book level-2 snapshot for ``N`` instruments at ``L`` levels.

    Parameters
    ----------
    timestamp_ns:
        Snapshot epoch in nanoseconds. Used for look-ahead validation.
    bid_sizes:
        Shape ``(N, L)`` non-negative bid sizes.
    ask_sizes:
        Shape ``(N, L)`` non-negative ask sizes.
    mid_prices:
        Shape ``(N,)`` strictly positive mid prices.
    """

    timestamp_ns: int
    bid_sizes: NDArray[np.float64]
    ask_sizes: NDArray[np.float64]
    mid_prices: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CapitalWeightedCouplingConfig:
    """Hyperparameters for capital-weighted β coupling.

    All defaults are conservative and reproduce the SSRN baseline sensitivity
    sweep. ``beta=1`` exactly recovers the input baseline coupling matrix.
    """

    K0: float = 1.0
    gamma: float = 1.0
    delta: float = 1.0
    beta_min: float = 0.25
    beta_max: float = 4.0
    r_floor: float = 1e-12
    normalize: bool = True
    fail_on_future_l2: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(
            [self.K0, self.gamma, self.delta, self.beta_min, self.beta_max, self.r_floor]
        ).all():
            raise ValueError("CapitalWeightedCouplingConfig fields must be finite.")
        if self.K0 < 0.0:
            raise ValueError("K0 must be non-negative.")
        if self.gamma < 0.0:
            raise ValueError("gamma must be non-negative.")
        if self.delta <= 0.0:
            raise ValueError("delta must be > 0.")
        if self.beta_min <= 0.0:
            raise ValueError("beta_min must be > 0.")
        if self.beta_max < self.beta_min:
            raise ValueError("beta_max must be >= beta_min.")
        if self.r_floor <= 0.0:
            raise ValueError("r_floor must be > 0.")


@dataclass(frozen=True, slots=True)
class CapitalWeightedCouplingResult:
    """Result of :func:`build_capital_weighted_adjacency`.

    Attributes
    ----------
    coupling:
        ``(N, N)`` symmetric, zero-diagonal, non-negative coupling matrix.
    beta:
        Scalar β actually applied (clipped to ``[beta_min, beta_max]``).
    r:
        ``(N,)`` per-node capital ratio.
    depth_mass:
        ``(N,)`` non-negative depth-mass vector (zeros if fallback).
    used_fallback:
        ``True`` when no L2 snapshot was provided and the baseline coupling
        was returned unchanged.
    reason:
        Human-readable explanation when ``used_fallback`` is ``True`` (else "").
    floor_engaged:
        ``True`` if a ``cfg.r_floor`` event was detected during ratio
        construction — either because ``median(depth_mass)`` fell below the
        floor (and was clamped to keep the division finite) or because at
        least one per-node ratio :math:`r_i` is at or below the floor (e.g.
        a zero-depth node). The coupling matrix remains a valid
        ``INV-KBETA`` object (finite, symmetric, zero diagonal); the flag is
        informational so callers can log or fail-loud as desired. Closes
        ⊛-audit AP-#5 (silent fallback) — see ``floor_diagnostic`` for the
        human-readable reason. Note: per-node ``r_i`` is **not** clamped
        (absolute clamps would break scale invariance ``INV-KBETA``); only
        the median is clamped, and only when needed for finite division.
    floor_diagnostic:
        Empty string when ``floor_engaged`` is ``False``. Otherwise a short
        token describing which event engaged: ``"median_clamped"``,
        ``"r_below_floor"``, or ``"median_clamped+r_below_floor"``.
    """

    coupling: NDArray[np.float64]
    beta: float
    r: NDArray[np.float64]
    depth_mass: NDArray[np.float64]
    used_fallback: bool
    reason: str
    floor_engaged: bool = False
    floor_diagnostic: str = ""


def _validate_snapshot(snapshot: L2DepthSnapshot) -> None:
    bid = snapshot.bid_sizes
    ask = snapshot.ask_sizes
    mid = snapshot.mid_prices

    for name, arr in (("bid_sizes", bid), ("ask_sizes", ask), ("mid_prices", mid)):
        if not isinstance(arr, np.ndarray):
            raise ValueError(f"{name} must be an ndarray, got {type(arr).__name__}.")
        if arr.dtype != np.float64:
            raise ValueError(f"{name} must be float64, got {arr.dtype}.")
        if not np.isfinite(arr).all():
            raise ValueError(f"{name} contains non-finite values.")

    if bid.ndim != 2 or ask.ndim != 2:
        raise ValueError("bid_sizes and ask_sizes must be rank-2 (N, L).")
    if bid.shape != ask.shape:
        raise ValueError("bid_sizes and ask_sizes must share shape.")
    if mid.ndim != 1:
        raise ValueError("mid_prices must be rank-1 (N,).")
    if mid.shape[0] != bid.shape[0]:
        raise ValueError("mid_prices length must match number of instruments.")
    if (bid < 0.0).any() or (ask < 0.0).any():
        raise ValueError("bid_sizes and ask_sizes must be non-negative.")
    if (mid <= 0.0).any():
        raise ValueError("mid_prices must be strictly positive.")


def compute_l2_depth_mass(snapshot: L2DepthSnapshot) -> NDArray[np.float64]:
    """Return per-instrument depth mass ``m_i = mid_i * Σ_l (bid_i,l + ask_i,l)``.

    Output is non-negative and finite by construction.
    """
    _validate_snapshot(snapshot)
    total_size = snapshot.bid_sizes.sum(axis=1) + snapshot.ask_sizes.sum(axis=1)
    mass: NDArray[np.float64] = (snapshot.mid_prices * total_size).astype(np.float64, copy=False)
    if not np.isfinite(mass).all():
        raise ValueError("depth_mass overflow encountered.")
    return mass


def _gini(x: NDArray[np.float64]) -> float:
    """Population Gini coefficient on a non-negative vector.

    Returns 0.0 when all entries are equal or when the total mass is zero.
    """
    if x.size == 0:
        return 0.0
    if (x < 0.0).any():
        raise ValueError("Gini input must be non-negative.")
    total = float(x.sum())
    if total <= 0.0:
        return 0.0
    sorted_x = np.sort(x)
    n = sorted_x.size
    weights = np.arange(1, n + 1, dtype=np.float64)
    g = (2.0 * float((weights * sorted_x).sum()) / (n * total)) - (n + 1.0) / n
    # bounds: Gini is mathematically in [0, 1 - 1/n] -> clamp to [0,1] for safety.
    return float(np.clip(g, 0.0, 1.0))


def estimate_scalar_beta(
    depth_mass: NDArray[np.float64],
    *,
    beta_min: float,
    beta_max: float,
) -> float:
    """Map depth-mass concentration to a bounded scalar β.

    The mapping uses ``1 - Gini(depth_mass)`` as a uniformity score in
    ``[0, 1]`` and linearly interpolates between ``beta_min`` and
    ``beta_max`` so that:

    - perfectly uniform depth (Gini=0)  → β = beta_max
    - maximally concentrated depth     → β = beta_min
    - empty / zero-mass input          → β = 1.0 (neutral, no effect)

    Returns
    -------
    float in ``[beta_min, beta_max]`` (or exactly 1.0 for the neutral case).
    """
    if beta_min <= 0.0 or beta_max < beta_min:
        raise ValueError("Require 0 < beta_min <= beta_max.")
    if depth_mass.size == 0:
        return 1.0
    if not np.isfinite(depth_mass).all() or (depth_mass < 0.0).any():
        raise ValueError("depth_mass must be finite and non-negative.")
    if float(depth_mass.sum()) <= 0.0:
        return 1.0
    uniformity = 1.0 - _gini(depth_mass)
    beta = beta_min + uniformity * (beta_max - beta_min)
    # bounds: numerical safety; mathematical range already guaranteed.
    return float(np.clip(beta, beta_min, beta_max))


def compute_capital_ratio(
    depth_mass: NDArray[np.float64],
    *,
    floor: float,
) -> tuple[NDArray[np.float64], bool, str]:
    """Per-node capital ratio ``r_i = depth_mass_i / median(depth_mass)``.

    The median is floored by ``floor`` so the ratio is finite even for
    degenerate depth vectors. Per-node ratios that land at or below ``floor``
    are detected and surfaced via the ``floor_engaged`` flag, but **not
    clamped**. Clamping per element would be an absolute (not scale-free)
    modification that breaks ``INV-KBETA`` scale invariance, so we preserve
    the raw ratio (including legitimate zeros for empty-depth nodes) and
    expose the event for caller-side handling.

    Returns
    -------
    r:
        ``(N,)`` non-negative ratio vector.
    floor_engaged:
        ``True`` if either the median was clamped to ``floor`` or any
        per-node :math:`r_i` is below ``floor`` (e.g. zero-depth node).
        Closes ⊛-audit AP-#5 (silent fallback) by making the floor event
        observable to callers.
    floor_diagnostic:
        Empty string when ``floor_engaged`` is ``False``. Otherwise a short
        token: ``"median_clamped"``, ``"r_below_floor"``, or
        ``"median_clamped+r_below_floor"``.

    Raises
    ------
    ValueError
        If ``floor <= 0`` or ``depth_mass`` contains non-finite / negative
        entries.
    """
    if floor <= 0.0:
        raise ValueError("floor must be > 0.")
    if depth_mass.size == 0:
        return np.zeros(0, dtype=np.float64), False, ""
    if not np.isfinite(depth_mass).all() or (depth_mass < 0.0).any():
        raise ValueError("depth_mass must be finite and non-negative.")
    med = float(np.median(depth_mass))
    median_clamped = med < floor
    if median_clamped:
        # bounds: median floor for numerical stability — observable via
        # floor_engaged in CapitalWeightedCouplingResult (⊛-audit AP-#5).
        med = floor
    r: NDArray[np.float64] = (depth_mass / med).astype(np.float64, copy=False)
    # Observability-only: detect that some per-node ratios are at or below the
    # floor (e.g. a node with zero depth while the rest of the book is
    # healthy). We DO NOT clamp r here — clamping would be an absolute (not
    # scale-free) modification and would break the scale-invariance invariant
    # tested in test_uniform_scale_invariance / test_scale_invariance_under_
    # uniform_depth_scaling. The flag is purely informational so callers can
    # log or fail-loud when zero-depth nodes appear (closes ⊛-audit AP-#5).
    r_below_floor = bool(np.any(r < floor))
    if not np.isfinite(r).all():
        raise ValueError("capital ratio became non-finite.")
    floor_engaged = median_clamped or r_below_floor
    if median_clamped and r_below_floor:
        diagnostic = "median_clamped+r_below_floor"
    elif median_clamped:
        diagnostic = "median_clamped"
    elif r_below_floor:
        diagnostic = "r_below_floor"
    else:
        diagnostic = ""
    return r, floor_engaged, diagnostic


def compute_k_beta(
    r: NDArray[np.float64],
    beta: float,
    cfg: CapitalWeightedCouplingConfig,
) -> NDArray[np.float64]:
    """Edgewise scalar coupling envelope ``K0 * (1 + γ r^{2δ})^{(β-1)/2}``.

    Operates on either a per-node vector (returns a vector) or an edgewise
    matrix (returns a matrix); only its multiplicative form is used. ``r`` is
    the input edgewise ratio (``r_ij`` or ``r_i``). Output is non-negative
    and finite.
    """
    if not np.isfinite(beta):
        raise ValueError("beta must be finite.")
    if (r < 0.0).any():
        raise ValueError("r must be non-negative.")
    exponent = 0.5 * (beta - 1.0)
    base = 1.0 + cfg.gamma * np.power(r, 2.0 * cfg.delta)
    envelope: NDArray[np.float64] = (cfg.K0 * np.power(base, exponent)).astype(
        np.float64, copy=False
    )
    if not np.isfinite(envelope).all():
        raise ValueError("K_beta envelope produced non-finite values.")
    return envelope


def _validate_baseline_adj(adj: NDArray[np.float64]) -> None:
    if adj.ndim != 2 or adj.shape[0] != adj.shape[1]:
        raise ValueError("baseline_adj must be square (N, N).")
    if not np.isfinite(adj).all():
        raise ValueError("baseline_adj contains non-finite values.")
    if (adj < -_FLOAT_FINITE_TOL).any():
        raise ValueError("baseline_adj must be non-negative.")
    if not np.allclose(adj, adj.T, atol=1e-10):
        raise ValueError("baseline_adj must be symmetric.")
    if not np.allclose(np.diag(adj), 0.0, atol=1e-12):
        raise ValueError("baseline_adj must have zero diagonal.")


def build_capital_weighted_adjacency(
    baseline_adj: NDArray[np.float64],
    snapshot: L2DepthSnapshot | None,
    signal_timestamp_ns: int,
    cfg: CapitalWeightedCouplingConfig,
) -> CapitalWeightedCouplingResult:
    """Construct β-modulated coupling from a baseline adjacency and L2 snapshot.

    Parameters
    ----------
    baseline_adj:
        ``(N, N)`` symmetric, non-negative, zero-diagonal coupling matrix.
    snapshot:
        L2 depth snapshot at signal time; ``None`` triggers a logged fallback
        that returns the baseline unchanged.
    signal_timestamp_ns:
        Decision-time epoch in nanoseconds. Snapshot timestamps strictly
        after this value are rejected when
        ``cfg.fail_on_future_l2`` is true.
    cfg:
        :class:`CapitalWeightedCouplingConfig`.

    Returns
    -------
    :class:`CapitalWeightedCouplingResult`. The result carries
    ``floor_engaged`` (and a short ``floor_diagnostic`` token) so the caller
    can detect when ``cfg.r_floor`` was applied to the median or any
    per-node ratio — the silent-fallback gap closed by ⊛-audit AP-#5. The
    coupling matrix remains valid (finite, symmetric, zero-diagonal,
    non-negative) regardless of the flag.
    """
    _validate_baseline_adj(baseline_adj)
    n = baseline_adj.shape[0]

    if snapshot is None:
        return CapitalWeightedCouplingResult(
            coupling=baseline_adj.astype(np.float64, copy=True),
            beta=1.0,
            r=np.ones(n, dtype=np.float64),
            depth_mass=np.zeros(n, dtype=np.float64),
            used_fallback=True,
            reason="no_l2_snapshot",
        )

    if cfg.fail_on_future_l2 and snapshot.timestamp_ns > signal_timestamp_ns:
        raise ValueError(
            "L2 snapshot timestamp_ns is after signal_timestamp_ns; look-ahead leakage rejected."
        )

    if snapshot.bid_sizes.shape[0] != n:
        raise ValueError(
            f"snapshot has {snapshot.bid_sizes.shape[0]} instruments but "
            f"baseline adjacency is {n}x{n}."
        )

    depth_mass = compute_l2_depth_mass(snapshot)
    r_node, floor_engaged, floor_diagnostic = compute_capital_ratio(depth_mass, floor=cfg.r_floor)
    beta = estimate_scalar_beta(depth_mass, beta_min=cfg.beta_min, beta_max=cfg.beta_max)

    # Edgewise ratio r_ij = sqrt(r_i * r_j); zero diagonal preserved.
    r_outer = np.sqrt(np.outer(r_node, r_node))
    envelope = compute_k_beta(r_outer, beta, cfg)
    coupling: NDArray[np.float64] = (baseline_adj * envelope).astype(np.float64, copy=False)
    np.fill_diagonal(coupling, 0.0)
    coupling = 0.5 * (coupling + coupling.T)  # enforce exact symmetry

    if cfg.normalize and float(baseline_adj.sum()) > 0.0:
        scale = float(baseline_adj.sum()) / max(float(coupling.sum()), _FLOAT_FINITE_TOL)
        coupling = coupling * scale
        np.fill_diagonal(coupling, 0.0)

    if not np.isfinite(coupling).all():
        raise ValueError("capital-weighted coupling contains non-finite values.")
    if (coupling < -_FLOAT_FINITE_TOL).any():
        raise ValueError("capital-weighted coupling must be non-negative.")
    if not np.allclose(coupling, coupling.T, atol=1e-10):
        raise ValueError("capital-weighted coupling lost symmetry.")

    return CapitalWeightedCouplingResult(
        coupling=coupling,
        beta=beta,
        r=r_node,
        depth_mass=depth_mass,
        used_fallback=False,
        reason="",
        floor_engaged=floor_engaged,
        floor_diagnostic=floor_diagnostic,
    )
