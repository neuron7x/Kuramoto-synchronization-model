# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T4 — Higher-order Kuramoto with triadic interaction.

Equation:
    dθ_i/dt = ω_i
              + σ₁ · Σ_j A_ij · sin(θ_j - θ_i)           [pairwise]
              + σ₂ · Σ_{j,k ∈ Δ(i)} sin(2θ_j - θ_k - θ_i) [triadic]

where Δ(i) = set of triangles containing node i.

The triadic term captures 3-body interactions:
    - When three assets form a triangle in the correlation network,
      their synchronization dynamics couple through higher-order effects
    - Standard pairwise Kuramoto misses cluster-level coherence
    - Triadic coupling can detect emergent clusters invisible to pairwise

Simplicial structure:
    Build 2-skeleton of clique complex from correlation matrix:
    1. Nodes = assets
    2. Edges (1-simplices) = |ρ_ij| > threshold
    3. Triangles (2-simplices) = cliques of size 3

No XGI dependency required: we build triangle list directly from
adjacency matrix using A³ diagonal trick.

Representation & information loss:
    The 2-skeleton is built from ``|ρ_ij| > threshold``, so correlation
    **sign is discarded**: an anti-correlated triple (ρ < 0) collapses onto
    the same simplex as a co-correlated one. The pairwise term is magnitude-
    weighted by ``|ρ|``; the triadic term is unit-weighted per triangle and
    carries no sign. This is therefore an *unsigned-coherence higher-order
    projection*, not a signed simplicial model, and every result declares it
    via ``HigherOrderKuramotoResult.signed`` / ``.information_loss``. The
    triadic term ``sin(2θ_j − θ_k − θ_i)`` is a genuine 3-phase coupling that
    does NOT reduce to a sum of pairwise ``sin(θ_a − θ_b)`` terms — the
    higher-order claim is about the coupling *form*, independent of the
    unsigned structure-building step.

References:
    Skardal & Arenas "Higher order interactions" Commun. Phys. (2020)
    Millán et al. "Explosive higher-order Kuramoto" PRL (2020)
    Bick et al. "What are higher-order networks?" SIAM Rev. (2023)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

#: Provenance constants for the unsigned-coherence 2-skeleton this engine
#: builds. ``|ρ| > threshold`` discards correlation sign, and the triadic
#: term is unit-weighted per triangle, so every result declares the same
#: representation and information loss.
_REPRESENTATION: str = "simplicial_2skeleton"
_INFORMATION_LOSS: tuple[str, ...] = ("correlation_sign", "triadic_edge_weight")


@dataclass(frozen=True, slots=True)
class HigherOrderKuramotoResult:
    """Result of higher-order Kuramoto simulation.

    The provenance fields make the structure honest and machine-auditable:
    the 2-skeleton is built by thresholding ``|ρ|`` so it is unsigned
    (``signed=False``) although higher-order (``higher_order=True``), and
    ``information_loss`` records what the ``|ρ| > threshold`` projection and
    the unit-weighted triadic term discard. They are constants for this
    estimator, not tunable outputs. The triadic coupling itself is a genuine
    non-pairwise-reducible 3-phase term — only the structure-building step is
    unsigned.
    """

    phases: NDArray[np.float64]  # (steps+1, N)
    order_parameter: NDArray[np.float64]  # (steps+1,)
    time: NDArray[np.float64]  # (steps+1,)
    n_triangles: int
    triadic_contribution: NDArray[np.float64]  # (steps+1,) magnitude of σ₂ term
    representation: str = _REPRESENTATION
    signed: bool = False
    higher_order: bool = True
    information_loss: tuple[str, ...] = _INFORMATION_LOSS


def find_triangles(adj: NDArray[np.bool_]) -> list[tuple[int, int, int]]:
    """Find all triangles in undirected graph.

    Uses A³ trace / 6 for counting, but returns explicit list.
    O(N²·Δ) where Δ = max degree.

    Parameters
    ----------
    adj : (N, N) boolean adjacency matrix.

    Returns
    -------
    List of (i, j, k) triangles with i < j < k.
    """
    n = adj.shape[0]
    triangles: list[tuple[int, int, int]] = []
    for i in range(n):
        neighbors_i = set(np.where(adj[i])[0])
        for j in neighbors_i:
            if j <= i:
                continue
            neighbors_j = set(np.where(adj[j])[0])
            common = neighbors_i & neighbors_j
            for k in common:
                if k > j:
                    triangles.append((i, j, k))
    return triangles


def build_triangle_index(
    n: int, triangles: list[tuple[int, int, int]]
) -> dict[int, list[tuple[int, int]]]:
    """Build per-node index of triangle partners.

    Returns dict mapping node i to list of (j, k) pairs where
    (i, j, k) forms a triangle.
    """
    index: dict[int, list[tuple[int, int]]] = {i: [] for i in range(n)}
    for i, j, k in triangles:
        index[i].append((j, k))
        index[j].append((i, k))
        index[k].append((i, j))
    return index


class HigherOrderKuramotoEngine:
    """Higher-order Kuramoto with pairwise + triadic coupling.

    Parameters
    ----------
    sigma1 : float
        Pairwise coupling strength (default 1.0).
    sigma2 : float
        Triadic coupling strength (default 0.5).
    dt : float
        Integration time step (default 0.01).
    steps : int
        Number of integration steps (default 1000).
    correlation_threshold : float
        Threshold for edge/triangle construction (default 0.3).
    """

    def __init__(
        self,
        sigma1: float = 1.0,
        sigma2: float = 0.5,
        dt: float = 0.01,
        steps: int = 1000,
        correlation_threshold: float = 0.3,
    ) -> None:
        if dt <= 0:
            raise ValueError(f"dt must be > 0, got {dt}")
        if steps < 1:
            raise ValueError(f"steps must be ≥ 1, got {steps}")
        self._sigma1 = sigma1
        self._sigma2 = sigma2
        self._dt = dt
        self._steps = steps
        self._corr_thresh = correlation_threshold

    def _build_structures(self, corr: NDArray[np.float64]) -> tuple[
        NDArray[np.float64],
        list[tuple[int, int, int]],
        dict[int, list[tuple[int, int]]],
    ]:
        """Build adjacency and triangle structures from correlation."""
        adj_bool = np.abs(corr) > self._corr_thresh
        np.fill_diagonal(adj_bool, False)

        # Weighted adjacency
        adj = np.abs(corr) * adj_bool.astype(float)
        np.fill_diagonal(adj, 0.0)

        triangles = find_triangles(adj_bool)
        tri_index = build_triangle_index(corr.shape[0], triangles)

        return adj, triangles, tri_index

    def _dtheta_dt(
        self,
        theta: NDArray[np.float64],
        omega: NDArray[np.float64],
        adj: NDArray[np.float64],
        tri_index: dict[int, list[tuple[int, int]]],
    ) -> tuple[NDArray[np.float64], float]:
        """Compute RHS of higher-order Kuramoto ODE.

        Returns (dθ/dt, triadic_magnitude).
        """
        n = theta.shape[0]

        # Pairwise coupling: σ₁ · Σ_j A_ij · sin(θ_j - θ_i)
        diff = theta[np.newaxis, :] - theta[:, np.newaxis]
        pairwise = self._sigma1 * (adj * np.sin(diff)).sum(axis=1)

        # Triadic coupling: σ₂ · Σ_{j,k ∈ Δ(i)} sin(2θ_j - θ_k - θ_i)
        triadic = np.zeros(n, dtype=np.float64)
        for i in range(n):
            for j, k in tri_index.get(i, []):
                triadic[i] += np.sin(2 * theta[j] - theta[k] - theta[i])
        triadic *= self._sigma2

        triadic_mag = float(np.sqrt(np.sum(triadic**2)))

        return omega + pairwise + triadic, triadic_mag

    def _rk4_step(
        self,
        theta: NDArray[np.float64],
        omega: NDArray[np.float64],
        adj: NDArray[np.float64],
        tri_index: dict[int, list[tuple[int, int]]],
    ) -> tuple[NDArray[np.float64], float]:
        """RK4 step with triadic coupling."""
        dt = self._dt

        k1, m1 = self._dtheta_dt(theta, omega, adj, tri_index)
        k2, m2 = self._dtheta_dt(theta + 0.5 * dt * k1, omega, adj, tri_index)
        k3, m3 = self._dtheta_dt(theta + 0.5 * dt * k2, omega, adj, tri_index)
        k4, m4 = self._dtheta_dt(theta + dt * k3, omega, adj, tri_index)

        theta_new = theta + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        return theta_new, (m1 + m2 + m3 + m4) / 4.0

    def run(
        self,
        corr: NDArray[np.float64],
        omega: NDArray[np.float64] | None = None,
        theta0: NDArray[np.float64] | None = None,
        seed: int = 42,
    ) -> HigherOrderKuramotoResult:
        """Run higher-order Kuramoto simulation.

        Parameters
        ----------
        corr : (N, N) correlation matrix.
        omega : (N,) natural frequencies (default: random).
        theta0 : (N,) initial phases (default: random).
        seed : int, RNG seed.

        Returns
        -------
        HigherOrderKuramotoResult.
        """
        corr_arr: NDArray[np.float64] = np.asarray(corr, dtype=np.float64)
        n = corr_arr.shape[0]

        rng = np.random.default_rng(seed)
        omega_arr: NDArray[np.float64] = (
            np.asarray(rng.standard_normal(n), dtype=np.float64)
            if omega is None
            else np.asarray(omega, dtype=np.float64)
        )
        theta0_arr: NDArray[np.float64] = (
            np.asarray(rng.uniform(0, 2 * np.pi, n), dtype=np.float64)
            if theta0 is None
            else np.asarray(theta0, dtype=np.float64)
        )

        adj, triangles, tri_index = self._build_structures(corr_arr)

        phases = np.empty((self._steps + 1, n), dtype=np.float64)
        R_arr = np.empty(self._steps + 1, dtype=np.float64)
        triadic_arr = np.empty(self._steps + 1, dtype=np.float64)
        time_arr = np.arange(self._steps + 1, dtype=np.float64) * self._dt

        theta = theta0_arr.copy()
        phases[0] = theta
        R_arr[0] = self._order_parameter(theta)
        triadic_arr[0] = 0.0

        for k in range(self._steps):
            theta, tri_mag = self._rk4_step(theta, omega_arr, adj, tri_index)
            phases[k + 1] = theta
            R_arr[k + 1] = self._order_parameter(theta)
            triadic_arr[k + 1] = tri_mag

        return HigherOrderKuramotoResult(
            phases=phases,
            order_parameter=R_arr,
            time=time_arr,
            n_triangles=len(triangles),
            triadic_contribution=triadic_arr,
        )

    @staticmethod
    def _order_parameter(theta: NDArray[np.float64]) -> float:
        """R = |mean(exp(iθ))|."""
        z = np.exp(1j * theta).mean()
        return float(np.clip(np.abs(z), 0.0, 1.0))  # INV-K1: R = |mean(exp(iθ))| ∈ [0,1]

    def run_from_prices(
        self,
        prices: NDArray[np.float64],
        window: int = 60,
        seed: int = 42,
    ) -> HigherOrderKuramotoResult:
        """Convenience: build correlation from prices, then run."""
        prices = np.asarray(prices, dtype=np.float64)
        returns = np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12)
        tail = returns[-window:] if returns.shape[0] > window else returns

        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(tail, rowvar=False)
        corr_arr: NDArray[np.float64] = np.asarray(np.nan_to_num(corr, nan=0.0), dtype=np.float64)

        return self.run(corr_arr, seed=seed)


__all__ = [
    "HigherOrderKuramotoEngine",
    "HigherOrderKuramotoResult",
    "find_triangles",
    "build_triangle_index",
    "SparseTriangleIndex",
    "HigherOrderSparseConfig",
    "build_sparse_triangle_index",
    "validate_sparse_triangle_index",
    "triadic_rhs_sparse",
    "run_sparse_higher_order",
]


# ── Sparse simplicial higher-order Kuramoto (opt-in, additive) ────────────


@dataclass(frozen=True, slots=True)
class SparseTriangleIndex:
    """Compressed triangle list for the 2-simplex skeleton.

    All three index arrays share length ``T`` (number of triangles).
    Each row ``(i[t], j[t], k[t])`` satisfies ``i < j < k`` and the index
    is sorted lexicographically with no duplicates.

    Attributes
    ----------
    i, j, k:
        ``int64`` arrays of triangle vertex indices.
    n_nodes:
        Total number of nodes in the underlying graph.
    """

    i: NDArray[np.int64]
    j: NDArray[np.int64]
    k: NDArray[np.int64]
    n_nodes: int

    def __post_init__(self) -> None:
        if not (self.i.shape == self.j.shape == self.k.shape):
            raise ValueError("SparseTriangleIndex i/j/k must share shape.")
        if self.i.ndim != 1:
            raise ValueError("SparseTriangleIndex arrays must be 1D.")
        if self.n_nodes <= 0:
            raise ValueError("n_nodes must be > 0.")

    @property
    def n_triangles(self) -> int:
        return int(self.i.size)


@dataclass(frozen=True, slots=True)
class HigherOrderSparseConfig:
    """Hyperparameters for the sparse triadic kernel.

    Attributes
    ----------
    sigma1:
        Pairwise coupling strength.
    sigma2:
        Triadic coupling strength.
    max_triangles:
        Hard upper bound on triangle count; exceeding this triggers
        :class:`ValueError`. ``None`` disables the cap.
    dense_debug:
        When True, the build path may allocate auxiliary ``O(N^2)``
        tensors for cross-validation against
        :class:`HigherOrderKuramotoEngine`. False forbids any allocation
        whose size would exceed ``c * n_triangles`` (see
        :func:`triadic_rhs_sparse`).
    """

    sigma1: float = 1.0
    sigma2: float = 0.5
    max_triangles: int | None = None
    dense_debug: bool = False

    def __post_init__(self) -> None:
        if not np.isfinite([self.sigma1, self.sigma2]).all():
            raise ValueError("sigma1/sigma2 must be finite.")
        if self.max_triangles is not None and self.max_triangles < 0:
            raise ValueError("max_triangles must be >= 0 or None.")


def validate_sparse_triangle_index(index: SparseTriangleIndex) -> None:
    """Verify ``i<j<k``, in-bounds, deduped, lex-sorted.

    Raises :class:`ValueError` on any violation.
    """
    if index.i.dtype != np.int64 or index.j.dtype != np.int64 or index.k.dtype != np.int64:
        raise ValueError("SparseTriangleIndex arrays must be int64.")
    if index.n_triangles == 0:
        return
    if (index.i < 0).any() or (index.k >= index.n_nodes).any():
        raise ValueError("SparseTriangleIndex contains out-of-range indices.")
    if not (index.i < index.j).all() or not (index.j < index.k).all():
        raise ValueError("SparseTriangleIndex rows must satisfy i<j<k.")
    rows = np.stack([index.i, index.j, index.k], axis=1)
    # Lexicographic sort check (rows must be strictly increasing).
    diffs = np.diff(rows, axis=0)
    if rows.shape[0] > 1:
        # First non-zero element of each diff row determines order.
        nonzero = np.where(diffs != 0)
        if nonzero[0].size > 0:
            first_idx = np.minimum.reduceat(
                nonzero[1],
                np.unique(nonzero[0], return_index=True)[1],
            )
            unique_rows, first_pos = np.unique(nonzero[0], return_index=True)
            for row_idx, col_idx in zip(unique_rows.tolist(), first_idx.tolist(), strict=True):
                if diffs[row_idx, col_idx] < 0:
                    raise ValueError("SparseTriangleIndex must be lexicographically sorted.")
        # Any diff row that is all zero indicates a duplicate triangle.
        zero_rows = (diffs == 0).all(axis=1)
        if zero_rows.any():
            raise ValueError("SparseTriangleIndex contains duplicate triangles.")


def build_sparse_triangle_index(
    adj: NDArray[np.bool_],
    *,
    max_triangles: int | None = None,
) -> SparseTriangleIndex:
    """Construct a :class:`SparseTriangleIndex` from a boolean adjacency.

    Iterates only over the upper triangle. Raises :class:`ValueError` if
    the discovered triangle count exceeds ``max_triangles``.
    """
    if adj.ndim != 2 or adj.shape[0] != adj.shape[1]:
        raise ValueError("adj must be a square matrix.")
    n = int(adj.shape[0])
    A = np.asarray(adj, dtype=bool, order="C")
    np.fill_diagonal(A, False)
    if not np.array_equal(A, A.T):
        raise ValueError("adj must be symmetric.")

    rows_i: list[int] = []
    rows_j: list[int] = []
    rows_k: list[int] = []
    for i in range(n):
        nb_i = np.flatnonzero(A[i])
        nb_i = nb_i[nb_i > i]
        for j in nb_i.tolist():
            common = np.flatnonzero(A[i] & A[j])
            common = common[common > j]
            for k in common.tolist():
                rows_i.append(i)
                rows_j.append(j)
                rows_k.append(k)
                if max_triangles is not None and len(rows_i) > max_triangles:
                    raise ValueError(f"triangle count exceeds max_triangles={max_triangles}.")

    idx = SparseTriangleIndex(
        i=np.asarray(rows_i, dtype=np.int64),
        j=np.asarray(rows_j, dtype=np.int64),
        k=np.asarray(rows_k, dtype=np.int64),
        n_nodes=n,
    )
    validate_sparse_triangle_index(idx)
    return idx


def triadic_rhs_sparse(
    theta: NDArray[np.float64],
    index: SparseTriangleIndex,
    sigma2: float,
) -> NDArray[np.float64]:
    """Sparse triadic RHS contribution for higher-order Kuramoto.

    For each triangle ``(i, j, k)`` we accumulate three deterministic
    terms via :func:`numpy.add.at`:

    .. math::

        \\Delta\\dot\\theta_i &+\\!= \\sin(2\\theta_j - \\theta_k - \\theta_i)\\\\
        \\Delta\\dot\\theta_j &+\\!= \\sin(2\\theta_i - \\theta_k - \\theta_j)\\\\
        \\Delta\\dot\\theta_k &+\\!= \\sin(2\\theta_i - \\theta_j - \\theta_k)

    The output is multiplied by ``sigma2``. No ``O(N^2)`` or ``O(N^3)``
    auxiliary buffer is allocated — total work is ``O(T)`` where ``T``
    is the triangle count.
    """
    validate_sparse_triangle_index(index)
    n = index.n_nodes
    if theta.shape != (n,):
        raise ValueError(f"theta shape {theta.shape} != ({n},).")

    out = np.zeros(n, dtype=np.float64)
    if index.n_triangles == 0 or sigma2 == 0.0:
        return out

    ti = theta[index.i]
    tj = theta[index.j]
    tk = theta[index.k]

    term_i = np.sin(2.0 * tj - tk - ti)
    term_j = np.sin(2.0 * ti - tk - tj)
    term_k = np.sin(2.0 * ti - tj - tk)

    np.add.at(out, index.i, term_i)
    np.add.at(out, index.j, term_j)
    np.add.at(out, index.k, term_k)

    out *= float(sigma2)
    return out


def _order_parameter_sparse(theta: NDArray[np.float64]) -> float:
    z = np.exp(1j * theta).mean()
    # INV-K1: R = |mean(exp(iθ))| ∈ [0,1].
    return float(np.clip(np.abs(z), 0.0, 1.0))


def run_sparse_higher_order(
    adj: NDArray[np.bool_],
    omega: NDArray[np.float64],
    theta0: NDArray[np.float64],
    *,
    cfg: HigherOrderSparseConfig,
    dt: float,
    steps: int,
) -> HigherOrderKuramotoResult:
    """Integrate the sparse higher-order Kuramoto ODE with RK4.

    Parameters
    ----------
    adj:
        ``(N, N)`` boolean adjacency matrix.
    omega, theta0:
        ``(N,)`` natural frequencies and initial phases.
    cfg:
        :class:`HigherOrderSparseConfig`.
    dt, steps:
        Integration step and total step count.

    Returns
    -------
    :class:`HigherOrderKuramotoResult`.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0.")
    if steps < 1:
        raise ValueError("steps must be >= 1.")

    n = int(adj.shape[0])
    if omega.shape != (n,) or theta0.shape != (n,):
        raise ValueError("omega/theta0 shape must match adj.")

    triangle_index = build_sparse_triangle_index(adj, max_triangles=cfg.max_triangles)
    weighted_adj = adj.astype(np.float64)
    np.fill_diagonal(weighted_adj, 0.0)

    def rhs(t_state: NDArray[np.float64]) -> tuple[NDArray[np.float64], float]:
        diff = t_state[np.newaxis, :] - t_state[:, np.newaxis]
        pairwise = cfg.sigma1 * (weighted_adj * np.sin(diff)).sum(axis=1)
        triadic = triadic_rhs_sparse(t_state, triangle_index, cfg.sigma2)
        magnitude = float(np.sqrt(np.sum(triadic**2)))
        return omega + pairwise + triadic, magnitude

    phases = np.empty((steps + 1, n), dtype=np.float64)
    R_arr = np.empty(steps + 1, dtype=np.float64)
    triadic_arr = np.empty(steps + 1, dtype=np.float64)
    time_arr = np.arange(steps + 1, dtype=np.float64) * dt

    theta = theta0.astype(np.float64, copy=True)
    phases[0] = theta
    R_arr[0] = _order_parameter_sparse(theta)
    triadic_arr[0] = 0.0

    for s in range(steps):
        k1, m1 = rhs(theta)
        k2, m2 = rhs(theta + 0.5 * dt * k1)
        k3, m3 = rhs(theta + 0.5 * dt * k2)
        k4, m4 = rhs(theta + dt * k3)
        theta = theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        phases[s + 1] = theta
        R_arr[s + 1] = _order_parameter_sparse(theta)
        triadic_arr[s + 1] = (m1 + m2 + m3 + m4) / 4.0

    return HigherOrderKuramotoResult(
        phases=phases,
        order_parameter=R_arr,
        time=time_arr,
        n_triangles=triangle_index.n_triangles,
        triadic_contribution=triadic_arr,
    )
