# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adaptive ODE solvers for stiff Kuramoto systems.

Fixed-step RK4 fails when coupling K or frequency spread ω is large
(stiff regime).  This module provides:

- **Dormand-Prince RK45** with embedded error estimation and automatic dt
- **scipy.integrate.solve_ivp** wrapper for LSODA/RK45/Radau backends

Usage::

    from core.kuramoto.adaptive import AdaptiveKuramotoEngine
    config = KuramotoConfig(N=100, K=50.0, steps=5000)
    result = AdaptiveKuramotoEngine(config, method="RK45").run()
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter

__all__ = ["AdaptiveKuramotoEngine"]

_logger = logging.getLogger(__name__)

SolverMethod = Literal["RK45", "RK23", "DOP853", "Radau", "BDF", "LSODA"]


class AdaptiveKuramotoEngine:
    """Kuramoto integrator with adaptive step-size control.

    Uses ``scipy.integrate.solve_ivp`` under the hood, which provides
    Dormand-Prince (RK45), LSODA (auto stiff/non-stiff), Radau (implicit),
    and other production-grade solvers.

    Parameters
    ----------
    config : KuramotoConfig
        Standard config.  ``dt`` is used as initial step hint; ``steps``
        determines the number of uniformly-spaced output points.
    method : str
        One of ``"RK45"`` (default), ``"LSODA"``, ``"Radau"``, ``"DOP853"``,
        ``"RK23"``, ``"BDF"``.
    rtol : float
        Relative tolerance (default: 1e-8).
    atol : float
        Absolute tolerance (default: 1e-10).
    """

    def __init__(
        self,
        config: KuramotoConfig,
        method: SolverMethod = "RK45",
        rtol: float = 1e-8,
        atol: float = 1e-10,
    ) -> None:
        self._cfg = config
        self._method = method
        self._rtol = rtol
        self._atol = atol
        self._omega, self._theta0 = self._resolve_ic(config)
        self._adj = self._resolve_adj(config)

    def run(self) -> KuramotoResult:
        """Integrate with adaptive stepping, interpolate to uniform grid."""
        cfg = self._cfg
        N = cfg.N
        t_end = cfg.dt * cfg.steps
        t_eval = np.linspace(0.0, t_end, cfg.steps + 1)

        omega = self._omega
        adj = self._adj

        def rhs(t: float, theta: NDArray[np.float64]) -> NDArray[np.float64]:
            diff = theta[np.newaxis, :] - theta[:, np.newaxis]
            coupling = (adj * np.sin(diff)).sum(axis=1)
            result: NDArray[np.float64] = omega + coupling
            return result

        _logger.info(
            "AdaptiveKuramotoEngine: N=%d, K=%.4f, method=%s, rtol=%.0e, atol=%.0e, T=%.4f",
            N,
            cfg.K,
            self._method,
            self._rtol,
            self._atol,
            t_end,
        )

        sol = solve_ivp(
            rhs,
            t_span=(0.0, t_end),
            y0=self._theta0,
            method=self._method,
            t_eval=t_eval,
            rtol=self._rtol,
            atol=self._atol,
            first_step=cfg.dt,
            max_step=t_end / 10,
        )

        if not sol.success:
            raise RuntimeError(f"ODE solver failed: {sol.message}")

        phases = sol.y.T  # (steps+1, N)
        R_arr = np.array([_order_parameter(phases[k]) for k in range(cfg.steps + 1)])
        time_arr = sol.t

        _logger.info(
            "Solver finished: %d internal steps, %d function evaluations",
            sol.t_events is not None and len(sol.t_events) or 0,
            sol.nfev,
        )

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
    def _resolve_adj(cfg: KuramotoConfig) -> NDArray[np.float64]:
        N, K = cfg.N, cfg.K
        if cfg.adjacency is not None:
            adj = K * cfg.adjacency.astype(np.float64, copy=True)
            np.fill_diagonal(adj, 0.0)
            return adj
        adj = np.full((N, N), K / N, dtype=np.float64)
        np.fill_diagonal(adj, 0.0)
        return adj
