# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Hypothesis strategies for the four research-grade invariant property tests.

Each strategy is deterministic given a Hypothesis seed and emits NumPy
``float64`` arrays matching the production module type contracts:

- :func:`l2_depth_snapshots` — :class:`L2DepthSnapshot` with positive sizes,
  positive prices, and timestamps that satisfy the no-look-ahead contract.
- :func:`weight_matrices` — symmetric, non-negative, zero-diagonal matrices
  on ``N ∈ [3, 12]`` for Ricci-flow inputs.
- :func:`curvature_dicts` — plausible Ollivier-Ricci curvature in ``[-1, 1]``
  conditioned on a weight matrix.
- :func:`ambiguity_sets` — :class:`AmbiguitySet` instances with non-negative
  per-metric radii drawn over the EnergyModel metric universe.
- :func:`phase_vectors` — phases in ``[0, 2π)`` (standard Kuramoto support).
- :func:`triangle_indices` — boolean adjacency matrices that yield valid
  :class:`SparseTriangleIndex` rows with strictly increasing ``i<j<k``.

INV-KBETA / INV-RC-FLOW / INV-FE-ROBUST / INV-HO-SPARSE.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from hypothesis import strategies as st
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import L2DepthSnapshot
from core.physics.higher_order_kuramoto import (
    SparseTriangleIndex,
    build_sparse_triangle_index,
)
from tacl.dr_free import AmbiguitySet
from tacl.energy_model import DEFAULT_THRESHOLDS

__all__ = [
    "l2_depth_snapshots",
    "weight_matrices",
    "curvature_dicts",
    "ambiguity_sets",
    "phase_vectors",
    "triangle_indices",
    "boolean_adjacency",
]


# Bounded, finite-precision-safe ranges — the production validators reject
# non-finite values, so strategies must keep magnitudes well below 1e150.
_MIN_N: Final[int] = 3
_MAX_N: Final[int] = 12
_MIN_LEVELS: Final[int] = 1
_MAX_LEVELS: Final[int] = 6


def _finite_floats(
    *, min_value: float, max_value: float, allow_zero: bool = True
) -> st.SearchStrategy[float]:
    """``float64`` strategy that excludes NaN/Inf and (optionally) zero."""
    base = st.floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
        width=64,
    )
    if not allow_zero:
        return base.filter(lambda x: x != 0.0)
    return base


@st.composite
def l2_depth_snapshots(draw: st.DrawFn, *, min_n: int = _MIN_N) -> L2DepthSnapshot:
    """Generate a valid :class:`L2DepthSnapshot`.

    Bid/ask sizes are non-negative, mid prices strictly positive, and the
    snapshot ``timestamp_ns`` is strictly less than ``signal_timestamp_ns``
    so the default ``fail_on_future_l2`` guard in
    :func:`build_capital_weighted_adjacency` is not tripped by construction.
    """
    n = draw(st.integers(min_value=min_n, max_value=_MAX_N))
    levels = draw(st.integers(min_value=_MIN_LEVELS, max_value=_MAX_LEVELS))

    # Sizes: non-negative, bounded; prices: strictly positive, bounded.
    bid_strategy = st.lists(
        _finite_floats(min_value=0.0, max_value=1e6),
        min_size=n * levels,
        max_size=n * levels,
    )
    ask_strategy = st.lists(
        _finite_floats(min_value=0.0, max_value=1e6),
        min_size=n * levels,
        max_size=n * levels,
    )
    mid_strategy = st.lists(
        _finite_floats(min_value=1e-3, max_value=1e6),
        min_size=n,
        max_size=n,
    )

    bid_flat = draw(bid_strategy)
    ask_flat = draw(ask_strategy)
    mid_list = draw(mid_strategy)

    bid = np.asarray(bid_flat, dtype=np.float64).reshape(n, levels)
    ask = np.asarray(ask_flat, dtype=np.float64).reshape(n, levels)
    mid = np.asarray(mid_list, dtype=np.float64)

    # Timestamps fit comfortably in int64 ns; positive and finite.
    ts = draw(st.integers(min_value=0, max_value=10**18))
    return L2DepthSnapshot(
        timestamp_ns=ts,
        bid_sizes=bid,
        ask_sizes=ask,
        mid_prices=mid,
    )


@st.composite
def weight_matrices(
    draw: st.DrawFn, *, min_n: int = _MIN_N, max_n: int = _MAX_N
) -> NDArray[np.float64]:
    """Generate a symmetric, non-negative, zero-diagonal weight matrix.

    Shape ``(N, N)`` with ``N ∈ [min_n, max_n]``. Off-diagonal entries are
    drawn IID from ``[0, 1]`` and then symmetrised; the diagonal is zeroed.
    """
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    upper = draw(
        st.lists(
            _finite_floats(min_value=0.0, max_value=1.0),
            min_size=n * n,
            max_size=n * n,
        )
    )
    raw = np.asarray(upper, dtype=np.float64).reshape(n, n)
    sym = 0.5 * (raw + raw.T)
    np.fill_diagonal(sym, 0.0)
    return sym


@st.composite
def curvature_dicts(
    draw: st.DrawFn,
    weights: NDArray[np.float64],
) -> dict[tuple[int, int], float]:
    """Generate a plausible curvature dict for the given weight matrix.

    Keys are ``(i, j)`` with ``i<j`` and ``weights[i, j] > 0``. Values are
    drawn from ``[-1, 1]`` (standard Ollivier-Ricci range under a 1D
    embedding; the lower bound matches INV-RC1 commentary).
    """
    n = weights.shape[0]
    out: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if weights[i, j] <= 0.0:
                continue
            kappa = draw(_finite_floats(min_value=-1.0, max_value=1.0))
            out[(i, j)] = kappa
    return out


@st.composite
def ambiguity_sets(
    draw: st.DrawFn,
    *,
    max_radius: float = 5.0,
) -> AmbiguitySet:
    """Generate a valid :class:`AmbiguitySet` over EnergyModel metrics.

    Each radius is non-negative and finite. Subsetting the metric universe
    is allowed (missing keys default to radius 0 in DR-FREE).
    """
    metric_names = sorted(DEFAULT_THRESHOLDS.keys())
    chosen = draw(
        st.lists(
            st.sampled_from(metric_names),
            min_size=0,
            max_size=len(metric_names),
            unique=True,
        )
    )
    radii: dict[str, float] = {}
    for name in chosen:
        radii[name] = draw(_finite_floats(min_value=0.0, max_value=max_radius))
    return AmbiguitySet(radii=radii, mode="box")


@st.composite
def phase_vectors(draw: st.DrawFn, n: int) -> NDArray[np.float64]:
    """Generate a length-``n`` phase vector with entries in ``[0, 2π)``."""
    if n <= 0:
        raise ValueError("phase_vectors(n) requires n > 0.")
    flat = draw(
        st.lists(
            _finite_floats(min_value=0.0, max_value=float(2.0 * np.pi - 1e-9)),
            min_size=n,
            max_size=n,
        )
    )
    return np.asarray(flat, dtype=np.float64)


@st.composite
def boolean_adjacency(
    draw: st.DrawFn, *, min_n: int = _MIN_N, max_n: int = _MAX_N, p: float = 0.5
) -> NDArray[np.bool_]:
    """Generate a symmetric boolean adjacency matrix with probability ``p``."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    upper_triangle = draw(
        st.lists(
            st.booleans(),
            min_size=(n * (n - 1)) // 2,
            max_size=(n * (n - 1)) // 2,
        )
    )
    adj = np.zeros((n, n), dtype=bool)
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            if upper_triangle[idx]:
                adj[i, j] = True
                adj[j, i] = True
            idx += 1
    # bounds: ``p`` is referenced for API compatibility with future edge-density
    # control; current implementation defers entirely to Hypothesis booleans.
    _ = p
    return adj


@st.composite
def triangle_indices(draw: st.DrawFn, n: int) -> SparseTriangleIndex:
    """Generate a valid :class:`SparseTriangleIndex` for an ``n``-node graph.

    A boolean adjacency matrix is drawn and then passed through
    :func:`build_sparse_triangle_index` so the resulting triangle list is
    guaranteed to satisfy ``i<j<k``, lex-sorted, deduped, and in-bounds.
    """
    if n < 3:
        raise ValueError("triangle_indices(n) requires n >= 3.")
    upper_triangle = draw(
        st.lists(
            st.booleans(),
            min_size=(n * (n - 1)) // 2,
            max_size=(n * (n - 1)) // 2,
        )
    )
    adj = np.zeros((n, n), dtype=bool)
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            if upper_triangle[idx]:
                adj[i, j] = True
                adj[j, i] = True
            idx += 1
    return build_sparse_triangle_index(adj, max_triangles=None)
