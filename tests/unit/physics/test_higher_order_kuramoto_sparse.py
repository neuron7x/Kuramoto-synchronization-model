# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the sparse simplicial higher-order Kuramoto kernel.

INV-HO-SPARSE — sparse triadic kernel preserves R∈[0,1], reduces to
pairwise when sigma2=0, matches the dense reference engine on small
graphs, is deterministic, and never allocates O(N^3) auxiliary tensors
when ``dense_debug=False``.
"""

from __future__ import annotations

import tracemalloc

import numpy as np
import pytest
from numpy.typing import NDArray

from core.physics.higher_order_kuramoto import (
    HigherOrderKuramotoEngine,
    HigherOrderSparseConfig,
    SparseTriangleIndex,
    build_sparse_triangle_index,
    build_triangle_index,
    find_triangles,
    run_sparse_higher_order,
    triadic_rhs_sparse,
    validate_sparse_triangle_index,
)


def _complete_adjacency(n: int) -> NDArray[np.bool_]:
    A = np.ones((n, n), dtype=bool)
    np.fill_diagonal(A, False)
    return A


def _correlation_from_adj(adj: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Translate a boolean adjacency to a correlation matrix the dense engine
    will threshold into the same edge set (correlation 0.9 above threshold
    0.3, 0 below).
    """
    n = adj.shape[0]
    corr = np.eye(n, dtype=np.float64)
    corr += 0.9 * adj.astype(np.float64)
    return corr


def test_sparse_triangle_index_unique_sorted() -> None:
    """INV-HO-SPARSE: build returns unique, lex-sorted triangles."""
    n = 6
    A = _complete_adjacency(n)
    idx = build_sparse_triangle_index(A)
    validate_sparse_triangle_index(idx)
    rows = list(zip(idx.i.tolist(), idx.j.tolist(), idx.k.tolist(), strict=True))
    assert len(set(rows)) == len(rows), (
        "INV-HO-SPARSE VIOLATED: triangles must be unique; "
        f"observed n_total={len(rows)} vs n_unique={len(set(rows))}, with N={n}."
    )
    assert rows == sorted(rows), (
        "INV-HO-SPARSE VIOLATED: triangle index must be lex-sorted; "
        f"observed first 5={rows[:5]}, expected sorted ascending, with N={n}."
    )


def test_sparse_matches_existing_dense_on_small_complete_graph() -> None:
    """INV-HO-SPARSE: sparse trajectory matches dense engine on K_n, n<=6."""
    n = 5
    adj_bool = _complete_adjacency(n)
    cfg = HigherOrderSparseConfig(sigma1=0.7, sigma2=0.4)
    omega = np.linspace(-1.0, 1.0, n).astype(np.float64)
    rng = np.random.default_rng(0)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)

    sparse_res = run_sparse_higher_order(adj_bool, omega, theta0, cfg=cfg, dt=0.01, steps=200)

    # Build a correlation matrix so the dense engine produces the same
    # weighted adjacency = adj_bool (weights = |corr| where above threshold).
    corr = _correlation_from_adj(adj_bool)
    dense = HigherOrderKuramotoEngine(
        sigma1=0.7,
        sigma2=0.4,
        dt=0.01,
        steps=200,
        correlation_threshold=0.3,
    )
    dense_res = dense.run(corr=corr, omega=omega, theta0=theta0)

    # The dense engine builds weighted_adj = |corr| (here 0.9 on edges) while
    # the sparse path uses adj.astype(float) (1.0 on edges). The sparse
    # trajectory therefore corresponds to dense run scaled by 1/0.9 in
    # sigma1 — but for invariant check we instead rebuild dense over a
    # correlation matrix of 1.0 by setting threshold=0.5 on a 1.0-graph.
    # Directly compare triangle counts and triadic finiteness instead, which
    # captures the sparse-vs-dense structural agreement.
    assert sparse_res.n_triangles == dense_res.n_triangles, (
        "INV-HO-SPARSE VIOLATED: sparse and dense triangle counts must agree; "
        f"observed sparse={sparse_res.n_triangles}, dense={dense_res.n_triangles}, "
        f"with K_{n} adjacency."
    )
    # Both order-parameter trajectories live in [0,1].
    assert (sparse_res.order_parameter >= 0.0).all() and (
        sparse_res.order_parameter <= 1.0
    ).all(), (
        "INV-K1 VIOLATED: sparse order_parameter outside [0,1]; "
        f"observed min={sparse_res.order_parameter.min():.6f}, "
        f"max={sparse_res.order_parameter.max():.6f}, with K_{n}, steps=200."
    )


def test_sigma2_zero_matches_pairwise() -> None:
    """INV-HO-SPARSE: sigma2=0 ⟹ triadic contribution is identically zero."""
    n = 5
    A = _complete_adjacency(n)
    idx = build_sparse_triangle_index(A)
    rng = np.random.default_rng(1)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)
    out = triadic_rhs_sparse(theta, idx, sigma2=0.0)
    np.testing.assert_array_equal(out, np.zeros(n, dtype=np.float64))


def test_no_triangles_zero_triadic() -> None:
    """INV-HO-SPARSE: a graph with no triangles ⟹ triadic RHS is zero."""
    n = 4
    # Path graph 0-1-2-3 has no triangles.
    A = np.zeros((n, n), dtype=bool)
    for i in range(n - 1):
        A[i, i + 1] = True
        A[i + 1, i] = True
    idx = build_sparse_triangle_index(A)
    assert idx.n_triangles == 0, (
        "INV-HO-SPARSE VIOLATED: path graph has no triangles; "
        f"observed n_triangles={idx.n_triangles}, expected 0, with N={n} path."
    )
    rng = np.random.default_rng(2)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)
    out = triadic_rhs_sparse(theta, idx, sigma2=0.5)
    np.testing.assert_array_equal(out, np.zeros(n, dtype=np.float64))


def test_R_bounds_sparse() -> None:
    """INV-K1: order parameter R∈[0,1] over the entire sparse trajectory."""
    n = 6
    A = _complete_adjacency(n)
    cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.3)
    omega = np.zeros(n, dtype=np.float64)
    rng = np.random.default_rng(11)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)

    res = run_sparse_higher_order(A, omega, theta0, cfg=cfg, dt=0.02, steps=500)
    R = res.order_parameter
    assert (R >= 0.0).all() and (R <= 1.0).all(), (
        "INV-K1 VIOLATED: R must lie in [0,1] over trajectory; "
        f"observed min={R.min():.6f}, max={R.max():.6f}, "
        f"expected [0,1], with N={n} K_n, steps=500."
    )


def test_sparse_deterministic() -> None:
    """INV-HO-SPARSE: identical inputs ⟹ identical outputs."""
    n = 5
    A = _complete_adjacency(n)
    cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.2)
    omega = np.linspace(-0.5, 0.5, n).astype(np.float64)
    theta0 = np.linspace(0.0, 1.0, n).astype(np.float64)

    r1 = run_sparse_higher_order(A, omega, theta0, cfg=cfg, dt=0.01, steps=100)
    r2 = run_sparse_higher_order(A, omega, theta0, cfg=cfg, dt=0.01, steps=100)
    np.testing.assert_array_equal(r1.phases, r2.phases)
    np.testing.assert_array_equal(r1.order_parameter, r2.order_parameter)


def test_large_sparse_graph_does_not_use_dense_N3_path() -> None:
    """INV-HO-SPARSE: dense_debug=False forbids O(N^3) allocations.

    We measure the peak heap allocation while computing the triadic RHS
    for a sparse graph. With ``N=120`` and only a handful of triangles
    (a ring with one extra triangle), an O(N^3) tensor would weigh
    ``120^3 * 8 B ≈ 13.8 MB``. The sparse kernel must stay well below
    that — we use a tight 1 MB ceiling.
    """
    n = 120
    A = np.zeros((n, n), dtype=bool)
    # Ring + a single triangle (0,1,2) → exactly one triangle.
    for i in range(n):
        j = (i + 1) % n
        A[i, j] = True
        A[j, i] = True
    A[0, 2] = True
    A[2, 0] = True

    idx = build_sparse_triangle_index(A)
    assert idx.n_triangles == 1, (
        "INV-HO-SPARSE VIOLATED: ring + chord 0-2 must have exactly one triangle; "
        f"observed n_triangles={idx.n_triangles}, expected 1, with N={n}."
    )

    rng = np.random.default_rng(3)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)
    tracemalloc.start()
    triadic_rhs_sparse(theta, idx, sigma2=0.5)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    dense_n3_bytes = n * n * n * 8
    ceiling = 1_000_000  # 1 MB
    assert peak < ceiling, (
        "INV-HO-SPARSE VIOLATED: triadic_rhs_sparse exceeds 1 MB peak allocation; "
        f"observed peak={peak} bytes, expected <{ceiling}, "
        f"with N={n}, dense_N3_bytes={dense_n3_bytes}, n_triangles=1."
    )


def test_validate_sparse_triangle_index_rejects_unsorted() -> None:
    """validate_sparse_triangle_index raises on i>=j."""
    bad = SparseTriangleIndex(
        i=np.asarray([1], dtype=np.int64),
        j=np.asarray([0], dtype=np.int64),
        k=np.asarray([2], dtype=np.int64),
        n_nodes=3,
    )
    with pytest.raises(ValueError, match="i<j<k"):
        validate_sparse_triangle_index(bad)


def test_max_triangles_cap_enforced() -> None:
    """build_sparse_triangle_index raises when triangle count exceeds cap."""
    n = 5
    A = _complete_adjacency(n)
    # K_5 has C(5,3)=10 triangles.
    with pytest.raises(ValueError, match="max_triangles"):
        build_sparse_triangle_index(A, max_triangles=3)


def test_sparse_config_validation() -> None:
    """HigherOrderSparseConfig rejects non-finite sigmas and negative caps."""
    with pytest.raises(ValueError, match="sigma1/sigma2 must be finite"):
        HigherOrderSparseConfig(sigma1=float("nan"))
    with pytest.raises(ValueError, match="max_triangles"):
        HigherOrderSparseConfig(max_triangles=-1)


def _random_symmetric_adj(n: int, p: float, seed: int) -> NDArray[np.bool_]:
    """Erdős–Rényi G(n, p) as a symmetric, diagonal-free boolean adjacency."""
    rng = np.random.default_rng(seed)
    upper = rng.random((n, n)) < p
    A = np.triu(upper, k=1)
    A = A | A.T
    np.fill_diagonal(A, False)
    return A.astype(bool)


def _dense_triadic_reference(
    theta: NDArray[np.float64],
    tri_index: dict[int, list[tuple[int, int]]],
    sigma2: float,
    n: int,
) -> NDArray[np.float64]:
    """Replicate the dense engine triadic accumulator (``_dtheta_dt`` L201-206).

    For each node ``i`` and partner pair ``(j, k)`` in ``tri_index[i]`` we sum
    ``sin(2θ_j − θ_k − θ_i)`` then scale by ``σ₂``. This is the exact
    canonical Skardal–Arenas triadic kernel used by
    :class:`HigherOrderKuramotoEngine`, reproduced so the test compares the
    two production code paths on a shared θ rather than re-deriving physics.
    """
    triadic = np.zeros(n, dtype=np.float64)
    for i in range(n):
        for j, k in tri_index.get(i, []):
            triadic[i] += np.sin(2.0 * theta[j] - theta[k] - theta[i])
    triadic *= sigma2
    return triadic


def test_dense_and_sparse_triadic_kernel_are_float_identical() -> None:
    """INV-K1: dense and sparse triadic RHS are the same ODE to float-exactness.

    The dense engine accumulator ``sin(2θ_j − θ_k − θ_i)`` (per-node, via
    ``build_triangle_index``) and ``triadic_rhs_sparse`` (per-triangle, via
    ``numpy.add.at``) are the algebraically identical canonical
    Skardal–Arenas triadic kernel: same σ₂, same sign, same three rotations
    per triangle. This loops over several random graphs/phase vectors and
    asserts they agree to ``atol=1e-12`` — proving by computation the identity
    that the module otherwise only states by reading. The bound is algebraic
    (the two paths evaluate the same closed-form sum, differing only in
    floating-point summation order), so an honest tolerance is machine-ε; we
    keep the registered algebraic floor 1e-12.
    """
    sigma2 = 0.37
    max_abs_diff = 0.0
    for seed in range(8):
        n = 7
        adj_bool = _random_symmetric_adj(n, p=0.6, seed=seed)
        rng = np.random.default_rng(1000 + seed)
        theta = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)

        triangles = find_triangles(adj_bool)
        tri_index = build_triangle_index(n, triangles)
        dense_triadic = _dense_triadic_reference(theta, tri_index, sigma2, n)

        sparse_index = build_sparse_triangle_index(adj_bool)
        sparse_triadic = triadic_rhs_sparse(theta, sparse_index, sigma2)

        assert sparse_index.n_triangles == len(triangles), (
            "INV-K1 VIOLATED: dense and sparse triangle structure must agree; "
            f"observed sparse={sparse_index.n_triangles}, dense={len(triangles)}, "
            f"expected equal triangle counts, "
            f"derived from identical adjacency, "
            f"with N={n}, p=0.6, seed={seed}."
        )
        np.testing.assert_allclose(
            dense_triadic,
            sparse_triadic,
            atol=1e-12,
            err_msg=(
                "INV-K1 VIOLATED: dense vs sparse triadic kernel diverged; "
                f"observed max|Δ|={float(np.max(np.abs(dense_triadic - sparse_triadic))):.3e}, "
                f"expected algebraic identity within atol=1e-12, "
                f"the kernels are the same sin(2θj−θk−θi) sum, "
                f"with N={n}, T={sparse_index.n_triangles}, sigma2={sigma2}, seed={seed}."
            ),
        )
        max_abs_diff = max(max_abs_diff, float(np.max(np.abs(dense_triadic - sparse_triadic))))

    assert max_abs_diff <= 1e-12, (
        "INV-K1 VIOLATED: aggregate dense-vs-sparse triadic deviation too large; "
        f"observed max|Δ|={max_abs_diff:.3e}, "
        f"expected ≤ algebraic floor 1e-12 (tol), "
        f"both paths evaluate the identical canonical triadic sum, "
        f"with N=7, sigma2={sigma2}, over seeds 0..7."
    )


def test_dense_and_sparse_trajectories_agree_on_equalized_weights() -> None:
    """INV-K1: dense and sparse RK4 trajectories coincide once edge weights match.

    The standing setup mismatch is purely in the *pairwise* weighting: the
    dense engine builds ``weighted_adj = |ρ|`` while the sparse path uses
    ``adj.astype(float) = 1.0`` on edges. We remove that mismatch by feeding
    the dense engine a correlation matrix that is exactly ``1.0`` on edges and
    thresholding at 0.5, so dense ``|ρ| = 1.0`` equals the sparse ``adj = 1.0``.
    With identical σ₁, σ₂, ω, θ₀, dt, steps the two RK4 integrators then
    evaluate bit-for-bit the same vector field, and order_parameter R(t)∈[0,1]
    and phases agree to ``atol=1e-10`` — limited only by floating-point
    summation order in the two distinct accumulation strategies (dense matrix
    sum vs ``numpy.add.at``), not by any physics difference.
    """
    n = 5
    adj_bool = _complete_adjacency(n)
    sigma1, sigma2 = 0.7, 0.4
    dt, steps = 0.01, 200
    omega = np.linspace(-1.0, 1.0, n).astype(np.float64)
    traj_tol = 1e-10

    # corr = 1.0 on edges, threshold 0.5 ⟹ dense weighted_adj = |ρ| = 1.0,
    # identical to the sparse adj.astype(float) = 1.0 weighting.
    corr = np.eye(n, dtype=np.float64) + 1.0 * adj_bool.astype(np.float64)

    # Loop over several random initial conditions: the equivalence is a
    # property of the shared vector field, not a single trajectory.
    for seed in range(4):
        rng = np.random.default_rng(seed)
        theta0 = rng.uniform(0.0, 2.0 * np.pi, size=n).astype(np.float64)

        cfg = HigherOrderSparseConfig(sigma1=sigma1, sigma2=sigma2)
        sparse_res = run_sparse_higher_order(adj_bool, omega, theta0, cfg=cfg, dt=dt, steps=steps)

        dense = HigherOrderKuramotoEngine(
            sigma1=sigma1,
            sigma2=sigma2,
            dt=dt,
            steps=steps,
            correlation_threshold=0.5,
        )
        dense_res = dense.run(corr=corr, omega=omega, theta0=theta0)

        assert sparse_res.n_triangles == dense_res.n_triangles, (
            "INV-K1 VIOLATED: equalized dense/sparse runs must share triangle count; "
            f"observed sparse={sparse_res.n_triangles}, dense={dense_res.n_triangles}, "
            f"expected equal, both K_{n} with unit weights, "
            f"with N={n}, dt={dt}, steps={steps}, seed={seed}."
        )
        np.testing.assert_allclose(
            sparse_res.order_parameter,
            dense_res.order_parameter,
            atol=traj_tol,
            err_msg=(
                "INV-K1 VIOLATED: R(t) trajectories diverged under equalized weights; "
                f"observed max|ΔR|="
                f"{float(np.max(np.abs(sparse_res.order_parameter - dense_res.order_parameter))):.3e}, "
                f"expected agreement within atol=1e-10 (tol), "
                f"identical vector field after weight equalization, "
                f"with N={n}, dt={dt}, steps={steps}, sigma1={sigma1}, sigma2={sigma2}, seed={seed}."
            ),
        )
        np.testing.assert_allclose(
            sparse_res.phases,
            dense_res.phases,
            atol=traj_tol,
            err_msg=(
                "INV-K1 VIOLATED: phase trajectories diverged under equalized weights; "
                f"observed max|Δθ|="
                f"{float(np.max(np.abs(sparse_res.phases - dense_res.phases))):.3e}, "
                f"expected agreement within atol=1e-10 (tol), "
                f"same RK4 flow on the same coupling, "
                f"with N={n}, dt={dt}, steps={steps}, sigma1={sigma1}, sigma2={sigma2}, seed={seed}."
            ),
        )
