# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property tests for INV-HO-SPARSE — sparse simplicial higher-order Kuramoto.

INV-HO-SPARSE: triangle index rows satisfy ``i < j < k``, lex-sorted, deduped;
σ₂ = 0 reduces the sparse RHS to a pure pairwise term; a graph with no
triangles produces zero triadic contribution; ``R(t) ∈ [0, 1]`` (INV-K1) under
evolution; finite inputs produce finite outputs (INV-HPC2); the integrator is
deterministic given a fixed seed (INV-HPC1).
"""

from __future__ import annotations

import numpy as np
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from core.physics.higher_order_kuramoto import (
    HigherOrderSparseConfig,
    build_sparse_triangle_index,
    run_sparse_higher_order,
    triadic_rhs_sparse,
    validate_sparse_triangle_index,
)

from .strategies import boolean_adjacency, phase_vectors, triangle_indices


def _no_triangle_adj(n: int) -> NDArray[np.bool_]:
    """A path / star graph with no triangles."""
    adj = np.zeros((n, n), dtype=bool)
    for i in range(n - 1):
        adj[i, i + 1] = True
        adj[i + 1, i] = True
    return adj


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(adj=boolean_adjacency())
def test_triangle_index_unique_sorted(adj: NDArray[np.bool_]) -> None:
    """INV-HO-SPARSE: built triangle index must validate (i<j<k, sorted, dedup)."""
    idx = build_sparse_triangle_index(adj, max_triangles=None)
    # Re-validation should pass without raising — the contract.
    validate_sparse_triangle_index(idx)
    if idx.n_triangles > 0:
        # Strict ordering on every row.
        assert (idx.i < idx.j).all(), (
            "INV-HO-SPARSE VIOLATED: triangle index must satisfy i < j. "
            f"Observed first failing row={(int(idx.i[0]), int(idx.j[0]), int(idx.k[0]))}, "
            "expected strictly increasing. Tolerance: integer < (no slack). "
            f"Context: n_triangles={idx.n_triangles}, n_nodes={idx.n_nodes}."
        )
        assert (idx.j < idx.k).all(), (
            "INV-HO-SPARSE VIOLATED: triangle index must satisfy j < k. "
            f"Observed first failing row={(int(idx.i[0]), int(idx.j[0]), int(idx.k[0]))}, "
            "expected strictly increasing. Tolerance: integer < (no slack). "
            f"Context: n_triangles={idx.n_triangles}, n_nodes={idx.n_nodes}."
        )
        # Deduplication: stack rows and check uniqueness.
        rows = np.stack([idx.i, idx.j, idx.k], axis=1)
        unique_rows = np.unique(rows, axis=0)
        assert unique_rows.shape[0] == rows.shape[0], (
            "INV-HO-SPARSE VIOLATED: triangle index must be deduplicated. "
            f"Observed |rows|={rows.shape[0]}, |unique|={unique_rows.shape[0]}, "
            "expected equal. Tolerance: set-equality (no slack). "
            f"Context: n_nodes={idx.n_nodes}."
        )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(min_value=3, max_value=8),
    sigma1=st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False),
    data=st.data(),
)
def test_sigma2_zero_matches_pairwise(n: int, sigma1: float, data: st.DataObject) -> None:
    """INV-HO-SPARSE: σ₂ = 0 ⇒ sparse RHS ≡ 0 (only pairwise term remains)."""
    theta = data.draw(phase_vectors(n))
    idx = data.draw(triangle_indices(n))
    rhs = triadic_rhs_sparse(theta, idx, sigma2=0.0)
    # Tolerance derivation: when σ₂ = 0 the function short-circuits to a
    # pre-zeroed buffer — no arithmetic is performed.
    assert np.array_equal(rhs, np.zeros(n, dtype=np.float64)), (
        "INV-HO-SPARSE VIOLATED: σ₂ = 0 must yield identically-zero triadic RHS. "
        f"Observed max|rhs|={float(np.abs(rhs).max()):.3e}, expected exact 0. "
        "Tolerance: bit-exact (short-circuit path). "
        f"Context: N={n}, n_triangles={idx.n_triangles}, σ₁={sigma1:.3f}."
    )


@settings(
    deadline=2000,
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(min_value=3, max_value=8),
    sigma2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    data=st.data(),
)
def test_no_triangles_zero_triadic(n: int, sigma2: float, data: st.DataObject) -> None:
    """INV-HO-SPARSE: graph without triangles ⇒ zero triadic contribution."""
    adj = _no_triangle_adj(n)
    idx = build_sparse_triangle_index(adj)
    assume(idx.n_triangles == 0)
    theta = data.draw(phase_vectors(n))
    rhs = triadic_rhs_sparse(theta, idx, sigma2=float(sigma2))
    # Tolerance derivation: the early-return branch fires whenever
    # ``index.n_triangles == 0``; the buffer is allocated as zeros.
    assert np.array_equal(rhs, np.zeros(n, dtype=np.float64)), (
        "INV-HO-SPARSE VIOLATED: a triangle-free graph must yield zero triadic RHS. "
        f"Observed max|rhs|={float(np.abs(rhs).max()):.3e}, expected exact 0. "
        "Tolerance: bit-exact (early-return path). "
        f"Context: N={n}, σ₂={sigma2:.3f}, graph=path."
    )


@settings(
    deadline=2000,
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(min_value=4, max_value=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_R_bounds_under_evolution(n: int, seed: int) -> None:
    """INV-K1 / INV-HO-SPARSE: ``R(t) ∈ [0, 1]`` for every step of evolution."""
    rng = np.random.default_rng(seed)
    # K_n complete graph maximises triangle count; bounded N keeps cost low.
    adj = np.ones((n, n), dtype=bool)
    np.fill_diagonal(adj, False)
    omega = rng.standard_normal(n).astype(np.float64)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, n).astype(np.float64)
    cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.5)
    result = run_sparse_higher_order(adj, omega, theta0, cfg=cfg, dt=0.01, steps=50)

    R = result.order_parameter
    # Tolerance derivation: INV-K1 is ``0 ≤ |z| ≤ 1`` exactly. The
    # implementation explicitly clips to ``[0, 1]`` (see _order_parameter_sparse),
    # so no slack is needed.
    assert np.isfinite(R).all(), (
        "INV-K1 VIOLATED: R(t) must be finite under evolution. "
        f"Observed any-NaN={bool(np.isnan(R).any())}, "
        f"any-Inf={bool(np.isinf(R).any())}, expected all finite. "
        "Tolerance: float finiteness (no slack). "
        f"Context: N={n}, seed={seed}, steps=50."
    )
    assert (R >= 0.0).all() and (R <= 1.0).all(), (
        "INV-K1 VIOLATED: R(t) must lie in [0, 1] for all t. "
        f"Observed min={float(R.min()):.6f}, max={float(R.max()):.6f}, "
        "expected ∈ [0, 1]. Tolerance: closed interval (R explicitly clipped). "
        f"Context: N={n}, seed={seed}, steps=50, sigma2=0.5."
    )


@settings(
    deadline=2000,
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(min_value=4, max_value=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_finite_outputs(n: int, seed: int) -> None:
    """INV-HPC2: finite inputs produce finite outputs across the trajectory."""
    rng = np.random.default_rng(seed)
    # K3-like adjacency for sparse-but-non-trivial triangle count.
    adj = np.zeros((n, n), dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            if (i + j) % 2 == 0:
                adj[i, j] = True
                adj[j, i] = True
    omega = rng.standard_normal(n).astype(np.float64)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, n).astype(np.float64)
    cfg = HigherOrderSparseConfig(sigma1=0.8, sigma2=0.4)
    result = run_sparse_higher_order(adj, omega, theta0, cfg=cfg, dt=0.005, steps=40)

    violations: list[str] = []
    if not np.isfinite(result.phases).all():
        violations.append("phases")
    if not np.isfinite(result.order_parameter).all():
        violations.append("order_parameter")
    if not np.isfinite(result.triadic_contribution).all():
        violations.append("triadic_contribution")
    if not np.isfinite(result.time).all():
        violations.append("time")
    assert not violations, (
        "INV-HPC2 VIOLATED: finite inputs must produce finite outputs. "
        f"Observed non-finite={violations}, expected none. "
        "Tolerance: float finiteness (no slack). "
        f"Context: N={n}, seed={seed}, steps=40, dt=0.005."
    )


def test_deterministic_with_fixed_seed() -> None:
    """INV-HPC1: bit-identical output under repeated runs with the same inputs."""
    n = 5
    rng = np.random.default_rng(42)
    adj = np.zeros((n, n), dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            adj[i, j] = True
            adj[j, i] = True
    omega = rng.standard_normal(n).astype(np.float64)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, n).astype(np.float64)
    cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.5)

    r1 = run_sparse_higher_order(adj, omega, theta0, cfg=cfg, dt=0.01, steps=30)
    r2 = run_sparse_higher_order(adj, omega, theta0, cfg=cfg, dt=0.01, steps=30)

    assert np.array_equal(r1.phases, r2.phases), (
        "INV-HPC1 VIOLATED: two runs with identical inputs must produce "
        "bit-identical phases. "
        f"Observed max|Δ|={float(np.abs(r1.phases - r2.phases).max()):.3e}, "
        "expected exact 0. Tolerance: bit-exact (no RNG, deterministic RK4). "
        f"Context: N={n}, steps=30."
    )
    assert np.array_equal(r1.order_parameter, r2.order_parameter), (
        "INV-HPC1 VIOLATED: order_parameter trajectories must be bit-identical. "
        f"Observed max|Δ|="
        f"{float(np.abs(r1.order_parameter - r2.order_parameter).max()):.3e}, "
        "expected exact 0. Tolerance: bit-exact. "
        f"Context: N={n}, steps=30."
    )
    assert r1.n_triangles == r2.n_triangles, (
        "INV-HPC1 VIOLATED: triangle counts must agree across runs. "
        f"Observed r1={r1.n_triangles}, r2={r2.n_triangles}, expected equal. "
        "Tolerance: integer equality (no slack)."
    )
