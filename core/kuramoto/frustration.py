# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Phase frustration α_{ij} estimation (protocol M2.2).

Given already-identified ``K`` and ``τ``, we solve the per-edge
one-dimensional optimisation

.. math::

    \\alpha^*_{ij} = \\arg\\min_{\\alpha \\in [-\\pi,\\pi]}
        \\sum_t \\Bigl[\\dot\\theta_i(t) - \\omega_i -
            K_{ij}\\,\\sin\\bigl(\\theta_j(t-\\tau_{ij}) - \\theta_i(t) - \\alpha\\bigr)\\Bigr]^2

This is the profile likelihood of the Sakaguchi parameter at fixed
coupling and delay, derived from the drift equation itself. It has two
attractive properties over the crude ``mean(Δφ)`` heuristic listed in
the methodology:

* It is consistent with the Sakaguchi–Kuramoto drift equation — the
  recovered ``α`` is exactly the one that minimises the residual of
  the same model the coupling estimator fits.
* It is a **1-D bounded optimisation per edge**, closed-form gradient
  available, so the solver runs in milliseconds even for dense
  ``N = 50`` networks.

For each edge we subtract the contribution of all *other* edges from
the target before fitting, which makes the per-edge problem exact
(assuming ``K`` and ``τ`` are themselves exact). When ``K`` is noisy
the residual from the other edges becomes a random offset that is
averaged out by the optimisation over many timesteps.

The solver uses ``scipy.optimize.minimize_scalar`` with the bounded
Brent method; no MCMC, no heavy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar

from .contracts import CouplingMatrix, DelayMatrix, FrustrationMatrix, PhaseMatrix

__all__ = [
    "FrustrationEstimationConfig",
    "FrustrationEstimator",
    "estimate_frustration",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrustrationEstimationConfig:
    """Hyperparameters for profile-likelihood frustration estimation.

    Attributes
    ----------
    dt : float
        Sampling interval used to differentiate the unwrapped phase.
    subtract_other_edges : bool
        If ``True`` (default) the contribution of every other active
        edge is subtracted from the target before fitting ``α_{ij}``.
        The alternatives (``False``) treat each edge in isolation and
        are only useful as a sanity check or when ``K`` has very few
        non-zero entries.
    eps : float
        Small constant added to ``xtol`` to silence Brent-method warnings
        on degenerate constant residuals.
    """

    dt: float = 1.0
    subtract_other_edges: bool = True
    eps: float = 1e-6

    def __post_init__(self) -> None:
        if self.dt <= 0:
            raise ValueError("dt must be > 0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frequency_deviation(theta: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``θ̇`` matrix and the per-oscillator natural frequency."""
    unwrapped = np.unwrap(theta, axis=0)
    theta_dot = np.asarray(np.gradient(unwrapped, dt, axis=0), dtype=np.float64)
    omega = np.asarray(np.median(theta_dot, axis=0), dtype=np.float64)
    return theta_dot, omega


def _delayed_diff(theta: np.ndarray, i: int, j: int, tau: int) -> np.ndarray:
    """Return the aligned ``θ_j(t − τ) − θ_i(t)`` for the common window."""
    T = theta.shape[0]
    if tau >= T:
        return np.zeros(0)
    return np.asarray(theta[: T - tau, j] - theta[tau:, i], dtype=np.float64)


# ---------------------------------------------------------------------------
# Core estimator
# ---------------------------------------------------------------------------


def _estimate_alpha_edge(
    i: int,
    j: int,
    theta: np.ndarray,
    theta_dot: np.ndarray,
    omega: np.ndarray,
    K: np.ndarray,
    tau: np.ndarray,
    alpha_current: np.ndarray,
    eps: float,
    subtract_other_edges: bool,
) -> float:
    """Profile-likelihood fit for a single edge ``(i, j)``.

    The per-row window is anchored at ``t = max_lag_i``, where
    ``max_lag_i`` is the largest delay among the active in-edges of
    oscillator ``i``. With the window anchored this way, every
    ``sin(θ_j(t − τ_{ij}) − θ_i(t))`` feature is well-defined without
    padding, and every per-edge contribution has the same length.
    """
    T, N = theta.shape
    k_ij = float(K[i, j])
    if abs(k_ij) < 1e-12:
        return 0.0

    # Find the maximum lag across all active edges in row i so we can
    # anchor the shared window at a single starting point.
    active_k = [kk for kk in range(N) if kk != i and abs(K[i, kk]) > 1e-12]
    max_lag_i = int(max((int(tau[i, kk]) for kk in active_k), default=0))
    T_eff = T - max_lag_i
    if T_eff < 10:
        return 0.0

    target = theta_dot[max_lag_i : max_lag_i + T_eff, i] - omega[i]

    if subtract_other_edges:
        for kk in active_k:
            if kk == j:
                continue
            t_ik = int(tau[i, kk])
            start = max_lag_i - t_ik
            theta_k_lag = theta[start : start + T_eff, kk]
            theta_i_win = theta[max_lag_i : max_lag_i + T_eff, i]
            contribution = K[i, kk] * np.sin(theta_k_lag - theta_i_win - alpha_current[i, kk])
            target = target - contribution

    t_ij = int(tau[i, j])
    start_j = max_lag_i - t_ij
    theta_j_lag = theta[start_j : start_j + T_eff, j]
    theta_i_win = theta[max_lag_i : max_lag_i + T_eff, i]
    phase_diff_ij = theta_j_lag - theta_i_win

    def loss(alpha: float) -> float:
        pred = k_ij * np.sin(phase_diff_ij - alpha)
        residual = target - pred
        return float(np.dot(residual, residual))

    result = minimize_scalar(
        loss,
        bounds=(-np.pi, np.pi),
        method="bounded",
        options={"xatol": eps},
    )
    return float(result.x)


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


class FrustrationEstimator:
    """Profile-likelihood estimator for the Sakaguchi ``α`` matrix.

    Example
    -------
    >>> est = FrustrationEstimator(FrustrationEstimationConfig(dt=0.05))
    >>> alpha = est.estimate(phase_matrix, coupling, delays)
    """

    def __init__(self, config: FrustrationEstimationConfig | None = None) -> None:
        self.config = config or FrustrationEstimationConfig()

    def estimate(
        self,
        phases: PhaseMatrix,
        coupling: CouplingMatrix,
        delays: DelayMatrix,
    ) -> FrustrationMatrix:
        if phases.asset_ids != coupling.asset_ids:
            raise ValueError("phases and coupling asset_ids must match")
        if phases.asset_ids != delays.asset_ids:
            raise ValueError("phases and delays asset_ids must match")
        cfg = self.config
        theta = np.asarray(phases.theta, dtype=np.float64)
        K = np.asarray(coupling.K, dtype=np.float64)
        tau = np.asarray(delays.tau, dtype=np.int64)

        theta_dot, omega = _frequency_deviation(theta, cfg.dt)
        N = phases.N
        alpha = np.zeros((N, N), dtype=np.float64)

        # Two passes: the second uses the alpha estimates from the first
        # to refine the residual subtraction. Two iterations are enough
        # — in practice the estimator converges to within machine
        # precision by the second pass for reasonable K / τ.
        for _ in range(2):
            alpha_prev = alpha.copy()
            for i in range(N):
                for j in range(N):
                    if i == j or abs(K[i, j]) < 1e-12:
                        continue
                    alpha[i, j] = _estimate_alpha_edge(
                        i,
                        j,
                        theta,
                        theta_dot,
                        omega,
                        K,
                        tau,
                        alpha_prev,
                        cfg.eps,
                        cfg.subtract_other_edges,
                    )
            if np.max(np.abs(alpha - alpha_prev)) < 1e-6:
                break

        alpha[K == 0] = 0.0
        return FrustrationMatrix(
            alpha=alpha,
            asset_ids=phases.asset_ids,
            method="profile_likelihood",
        )


def estimate_frustration(
    phases: PhaseMatrix,
    coupling: CouplingMatrix,
    delays: DelayMatrix,
    config: FrustrationEstimationConfig | None = None,
) -> FrustrationMatrix:
    """Functional shortcut around :class:`FrustrationEstimator`."""
    return FrustrationEstimator(config).estimate(phases, coupling, delays)
