# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Sparse connectivity support for large-scale Kuramoto networks.

For networks with millions of nodes (brain connectomes, social graphs),
dense N×N adjacency is infeasible (O(N²) memory).  This module computes
coupling in O(E) time using CSR sparse matrices.

Usage::

    from core.kuramoto.sparse import SparseKuramotoEngine
    import scipy.sparse as sp

    adj = sp.random(100_000, 100_000, density=0.001, format="csr")
    config = KuramotoConfig(
        N=100_000, K=2.0, adjacency=adj, adjacency_kind="normalized_topology"
    )
    result = SparseKuramotoEngine(config).run()
"""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray
from scipy import sparse

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter

__all__ = ["SparseKuramotoEngine"]

_logger = logging.getLogger(__name__)


def _sparse_dtheta_dt(
    theta: NDArray[np.float64],
    omega: NDArray[np.float64],
    adj_csr: sparse.csr_matrix,
) -> NDArray[np.float64]:
    """Kuramoto RHS with O(E) sparse coupling.

    For each oscillator i, computes:
        coupling_i = Σ_{j ∈ neighbors(i)} A_ij · sin(θ_j - θ_i)

    Using CSR row-slicing to iterate only over existing edges.
    """
    sin_theta = np.sin(theta)
    cos_theta = np.cos(theta)
    # Exploit sin(θ_j - θ_i) = sin(θ_j)cos(θ_i) - cos(θ_j)sin(θ_i)
    coupling = adj_csr.dot(sin_theta) * cos_theta - adj_csr.dot(cos_theta) * sin_theta
    result: NDArray[np.float64] = omega + coupling
    return result


def _sparse_rk4_step(
    theta: NDArray[np.float64],
    omega: NDArray[np.float64],
    adj_csr: sparse.csr_matrix,
    dt: float,
) -> NDArray[np.float64]:
    """RK4 step using sparse coupling — O(E) per evaluation."""
    k1 = _sparse_dtheta_dt(theta, omega, adj_csr)
    k2 = _sparse_dtheta_dt(theta + 0.5 * dt * k1, omega, adj_csr)
    k3 = _sparse_dtheta_dt(theta + 0.5 * dt * k2, omega, adj_csr)
    k4 = _sparse_dtheta_dt(theta + dt * k3, omega, adj_csr)
    return theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


class SparseKuramotoEngine:
    """Kuramoto integrator for large sparse networks.

    Accepts ``scipy.sparse`` adjacency matrices.  Dense adjacency in
    ``KuramotoConfig.adjacency`` is auto-converted to CSR.  For truly
    large graphs, pass a pre-built CSR matrix via ``sparse_adjacency``.
    """

    def __init__(
        self,
        config: KuramotoConfig,
        sparse_adjacency: sparse.spmatrix | None = None,
    ) -> None:
        self._cfg = config
        self._omega, self._theta0 = self._resolve_ic(config)
        self._adj_csr = self._resolve_sparse_adj(config, sparse_adjacency)

        nnz = self._adj_csr.nnz
        density = nnz / (config.N**2) if config.N > 0 else 0
        _logger.info(
            "SparseKuramotoEngine: N=%d, edges=%d, density=%.6f, memory=%.1f MB",
            config.N,
            nnz,
            density,
            (self._adj_csr.data.nbytes + self._adj_csr.indices.nbytes + self._adj_csr.indptr.nbytes)
            / 1e6,
        )

    def run(self) -> KuramotoResult:
        """Integrate using sparse O(E) coupling."""
        cfg = self._cfg
        N = cfg.N
        steps = cfg.steps
        dt = cfg.dt

        phases = np.empty((steps + 1, N), dtype=np.float64)
        R_arr = np.empty(steps + 1, dtype=np.float64)
        time_arr = np.arange(steps + 1, dtype=np.float64) * dt

        theta = self._theta0.copy()
        phases[0] = theta
        R_arr[0] = _order_parameter(theta)

        for k in range(steps):
            theta = _sparse_rk4_step(theta, self._omega, self._adj_csr, dt)
            phases[k + 1] = theta
            R_arr[k + 1] = _order_parameter(theta)

        return KuramotoResult(phases=phases, order_parameter=R_arr, time=time_arr, config=cfg)

    @staticmethod
    def _resolve_ic(cfg: KuramotoConfig) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        rng = np.random.default_rng(cfg.seed)
        omega = (
            cfg.omega.astype(np.float64, copy=False)
            if cfg.omega is not None
            else rng.standard_normal(cfg.N)
        )
        theta0 = (
            cfg.theta0.astype(np.float64, copy=False)
            if cfg.theta0 is not None
            else rng.uniform(0.0, 2.0 * np.pi, cfg.N)
        )
        return omega, theta0

    @staticmethod
    def _resolve_sparse_adj(
        cfg: KuramotoConfig,
        sparse_adj: sparse.spmatrix | None,
    ) -> sparse.csr_matrix:
        K = cfg.K
        N = cfg.N

        if sparse_adj is not None:
            adj = sparse.csr_matrix(sparse_adj, dtype=np.float64, copy=True)
            adj = adj.multiply(K)
            adj.setdiag(0.0)
            adj.eliminate_zeros()
            return adj

        if cfg.adjacency is not None:
            adj = sparse.csr_matrix(cfg.adjacency * K, dtype=np.float64)
            adj.setdiag(0.0)
            adj.eliminate_zeros()
            return adj

        # Global all-to-all as sparse (only useful for moderate N)
        adj = sparse.csr_matrix(np.full((N, N), K / N, dtype=np.float64))
        adj.setdiag(0.0)
        adj.eliminate_zeros()
        return adj
