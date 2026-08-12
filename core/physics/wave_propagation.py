# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T6 — Graph Diffusion Engine (Fokker-Planck, NOT Maxwell literally).

Information propagation as diffusion on correlation network:

    ∂ρ/∂t = -L·ρ     (graph diffusion equation)

where:
    L = D - A          (graph Laplacian, D = degree matrix)
    D_ij = D_0·exp(κ_ij)  (curvature-dependent diffusion tensor)
    ρ(x,t) = probability density of price state

Solution:
    ρ(t) = exp(-L·t) · ρ(0)    via scipy.linalg.expm

This IS Maxwell-inspired (wave + diffusion) but physically grounded:
    - reduces to heat equation for κ=0
    - reduces to drift equation for D=0
    - coupling to Ricci: information spreads faster on positively curved
      edges (validated: Sandhu et al. 2016, "Graph curvature for
      differentiating cancer networks")

Implementation: graph Laplacian discretisation.
Matrix exponential via Padé approximation (scipy.linalg.expm).

AUDIT NOTE on complexity:
    Dense expm is O(n³). Tractable for n≤500 assets.
    For n>500 the action exp(-L·t)·ρ₀ is computed via a Lanczos Krylov-subspace
    method (``_expmv_lanczos``): since L is symmetric PSD, an m-step Lanczos
    factorisation V_mᵀ L V_m = T_m (tridiagonal, m≪n) gives
        exp(-L·t)·ρ₀ ≈ ‖ρ₀‖ · V_m · exp(-t·T_m) · e₁,
    reducing the exponential to a small m×m one. Cost O(m·n²) dense / O(m·nnz)
    sparse, versus O(n³). ``propagate(method="auto")`` dispatches dense≤500,
    Krylov above, and Lanczos matches dense expm to solver tolerance.
"""

from __future__ import annotations

import logging
from typing import cast

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

_LOGGER = logging.getLogger("geosync.physics.wave")

#: Dense-expm is used at or below this size; above it, Lanczos Krylov.
_DENSE_MAX_N = 500


def _expmv_lanczos(
    L: NDArray[np.float64],
    v: NDArray[np.float64],
    t: float,
    m_max: int = 60,
    tol: float = 1e-12,
) -> NDArray[np.float64]:
    """Action of the matrix exponential: return exp(-L·t)·v via Lanczos.

    Assumes L is symmetric (graph Laplacian). Uses full reorthogonalisation for
    numerical stability and stops early on an invariant subspace (β_{j+1}≈0).
    """
    n = v.shape[0]
    beta0 = float(np.linalg.norm(v))
    if beta0 == 0.0:
        return v.copy()

    m_max = min(m_max, n)
    V = np.zeros((n, m_max + 1), dtype=np.float64)
    alpha = np.zeros(m_max, dtype=np.float64)
    beta = np.zeros(m_max + 1, dtype=np.float64)
    V[:, 0] = v / beta0

    m_eff = m_max
    for j in range(m_max):
        w = L @ V[:, j]
        alpha[j] = float(V[:, j] @ w)
        w = w - alpha[j] * V[:, j]
        if j > 0:
            w = w - beta[j] * V[:, j - 1]
        # full reorthogonalisation against the built basis
        w = w - V[:, : j + 1] @ (V[:, : j + 1].T @ w)
        beta[j + 1] = float(np.linalg.norm(w))
        if beta[j + 1] < tol:
            m_eff = j + 1
            break
        V[:, j + 1] = w / beta[j + 1]

    tri = np.diag(alpha[:m_eff])
    if m_eff > 1:
        off = beta[1:m_eff]
        tri = tri + np.diag(off, 1) + np.diag(off, -1)
    exp_small = expm(-t * tri)
    # exp(-tL)·v ≈ beta0 · V_m · exp(-t·T_m) · e1  (e1 selects the first column)
    y = beta0 * (V[:, :m_eff] @ exp_small[:, 0])
    return cast(NDArray[np.float64], y)


class GraphDiffusionEngine:
    """Diffusion propagation on curvature-weighted graphs.

    Parameters
    ----------
    D_0 : float
        Base diffusion coefficient (default 1.0).
    """

    def __init__(self, D_0: float = 1.0) -> None:
        if D_0 <= 0:
            raise ValueError(f"D_0 must be > 0, got {D_0}")
        self._D_0 = D_0

    @property
    def D_0(self) -> float:
        return self._D_0

    def build_laplacian(
        self,
        adjacency: NDArray[np.float64],
        curvature: NDArray[np.float64] | None = None,
    ) -> NDArray[np.float64]:
        """Build graph Laplacian L = D - W.

        If curvature is provided, edge weights are scaled:
            W_ij = A_ij · D_0 · exp(κ_ij)

        Positive curvature → stronger coupling → faster diffusion.
        Negative curvature → weaker coupling → slower diffusion.

        Parameters
        ----------
        adjacency : (N, N) adjacency/weight matrix.
        curvature : (N, N) Ollivier-Ricci curvature matrix (optional).

        Returns
        -------
        (N, N) graph Laplacian. Eigenvalues are non-negative for
        undirected graphs (verified by construction).
        """
        A = np.asarray(adjacency, dtype=np.float64)
        n = A.shape[0]
        if A.shape != (n, n):
            raise ValueError(f"adjacency must be square, got {A.shape}")

        if curvature is not None:
            kappa = np.asarray(curvature, dtype=np.float64)
            if kappa.shape != (n, n):
                raise ValueError(f"curvature must match adjacency: {kappa.shape} vs {A.shape}")
            W = A * self._D_0 * np.exp(kappa)
        else:
            W = A * self._D_0

        # Ensure symmetry
        W = 0.5 * (W + W.T)
        np.fill_diagonal(W, 0.0)

        # Degree matrix
        D = np.diag(W.sum(axis=1))
        L = D - W
        return L

    @staticmethod
    def propagate(
        rho_0: NDArray[np.float64],
        L: NDArray[np.float64],
        t: float,
        method: str = "auto",
    ) -> NDArray[np.float64]:
        """Propagate density ρ(t) = exp(-L·t) · ρ(0).

        Parameters
        ----------
        rho_0 : (N,) initial probability density. Must sum to 1.
        L : (N, N) graph Laplacian.
        t : float, time to propagate.
        method : {"auto", "dense", "krylov"}. "auto" uses dense Padé expm for
            N≤500 and the Lanczos Krylov action above it (identical result to
            solver tolerance, but O(m·n²) instead of O(n³)).

        Returns
        -------
        (N,) propagated density. Sum is preserved (probability conservation).
        """
        rho_0 = np.asarray(rho_0, dtype=np.float64)
        L = np.asarray(L, dtype=np.float64)

        if t < 0:
            raise ValueError(f"t must be ≥ 0, got {t}")
        if t == 0:
            return rho_0.copy()
        if method not in ("auto", "dense", "krylov"):
            raise ValueError(f"method must be auto/dense/krylov, got {method!r}")

        use_krylov = method == "krylov" or (method == "auto" and L.shape[0] > _DENSE_MAX_N)
        if use_krylov:
            rho_t = _expmv_lanczos(L, rho_0, float(t))
        else:
            rho_t = expm(-L * t) @ rho_0
        # bounds: ρ(t) is a probability density (≥ 0); expm(-L·t) for a
        # graph Laplacian is non-negative, so negativity is round-off.
        # Surface a non-trivial excursion (non-Laplacian L). Behaviour
        # unchanged by the log.
        _neg = float(-rho_t[rho_t < 0.0].sum()) if np.any(rho_t < 0.0) else 0.0
        if _neg > 1e-9:
            _LOGGER.warning(
                "wave propagate: clamped %.3e negative density mass to 0 "
                "— heat kernel should be non-negative; check L is a valid "
                "graph Laplacian.",
                _neg,
            )
        rho_t = np.maximum(rho_t, 0.0)
        # Renormalise to preserve total probability
        total = rho_t.sum()
        if total > 0:
            rho_t = rho_t / total
        return cast(NDArray[np.float64], rho_t)

    @staticmethod
    def volatility_front(
        rho_t: NDArray[np.float64],
        threshold: float = 0.1,
        asset_names: list[str] | None = None,
    ) -> list[str | int]:
        """Identify assets at the diffusion wavefront.

        Assets with ρ_i(t) > threshold are at the front of
        information/volatility propagation.

        Parameters
        ----------
        rho_t : (N,) current density.
        threshold : float, density threshold.
        asset_names : optional list of asset identifiers.

        Returns
        -------
        List of asset identifiers (names or indices) above threshold.
        """
        rho = np.asarray(rho_t, dtype=np.float64)
        indices = np.where(rho > threshold)[0]
        if asset_names is not None:
            return [asset_names[i] for i in indices]
        return [int(i) for i in indices]

    def laplacian_eigenvalues(self, L: NDArray[np.float64]) -> NDArray[np.float64]:
        """Compute eigenvalues of graph Laplacian.

        For valid Laplacians:
        - All eigenvalues ≥ 0
        - Smallest eigenvalue = 0 (connected graph has multiplicity 1)
        - Second smallest = algebraic connectivity (Fiedler value)
        """
        eigenvalues = np.linalg.eigvalsh(L)
        return eigenvalues.astype(np.float64)


__all__ = ["GraphDiffusionEngine"]
