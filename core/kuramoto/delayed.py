# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Delayed Differential Equation (DDE) Kuramoto model.

In distributed systems (data centres, power grids, neural circuits),
signal propagation takes finite time τ.  The delayed Kuramoto model:

    dθ_i(t)/dt = ω_i + K · Σ_j A_ij · sin(θ_j(t - τ_ij) - θ_i(t))

This fundamentally changes synchronization dynamics: delays can
destabilize otherwise stable states, create chimera patterns, or
shift the critical coupling.

Implementation uses a ring buffer of past states with linear
interpolation for sub-step delay lookups.

Usage::

    from core.kuramoto.delayed import DelayedKuramotoEngine
    config = KuramotoConfig(N=50, K=3.0, dt=0.01, steps=5000)
    engine = DelayedKuramotoEngine(config, tau=0.5)  # uniform delay
    result = engine.run()
"""

from __future__ import annotations

import logging
from typing import Callable, Union

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter

__all__ = ["DelayedKuramotoEngine"]

_logger = logging.getLogger(__name__)


class DelayedKuramotoEngine:
    """Kuramoto integrator with time-delayed coupling.

    Parameters
    ----------
    config : KuramotoConfig
        Standard config.
    tau : float | NDArray
        Delay value(s).  Scalar for uniform delay; (N, N) array for
        heterogeneous per-edge delays.
    history_fn : callable | None
        Optional function ``f(t) -> NDArray[N]`` for pre-simulation
        history (t < 0).  Default: constant at theta0.
    """

    def __init__(
        self,
        config: KuramotoConfig,
        tau: Union[float, NDArray[np.float64]] = 0.1,
        history_fn: Callable[[float], NDArray[np.float64]] | None = None,
    ) -> None:
        self._cfg = config
        self._omega, self._theta0 = self._resolve_ic(config)
        self._adj = self._resolve_adj(config)

        # Process delay
        if np.isscalar(tau):
            tau_scalar = float(tau)  # type: ignore[arg-type]
            self._tau_matrix = np.full((config.N, config.N), tau_scalar, dtype=np.float64)
            self._max_tau = tau_scalar
        else:
            self._tau_matrix = np.asarray(tau, dtype=np.float64)
            self._max_tau = float(np.max(self._tau_matrix))

        self._history_fn = history_fn

        # Ring buffer sizing: need enough history to cover max delay
        self._buffer_len = max(int(np.ceil(self._max_tau / config.dt)) + 2, 3)

        _logger.info(
            "DelayedKuramotoEngine: N=%d, max_τ=%.4f, buffer=%d steps",
            config.N,
            self._max_tau,
            self._buffer_len,
        )

    def run(self) -> KuramotoResult:
        """Integrate DDE with ring-buffer history."""
        cfg = self._cfg
        N = cfg.N
        steps = cfg.steps
        dt = cfg.dt

        phases = np.empty((steps + 1, N), dtype=np.float64)
        R_arr = np.empty(steps + 1, dtype=np.float64)
        time_arr = np.arange(steps + 1, dtype=np.float64) * dt

        # Initialize ring buffer with history
        buffer = np.zeros((self._buffer_len, N), dtype=np.float64)
        if self._history_fn is not None:
            for idx in range(self._buffer_len):
                t_hist = -(self._buffer_len - 1 - idx) * dt
                buffer[idx] = self._history_fn(t_hist)
        else:
            # Constant history = theta0
            buffer[:] = self._theta0[np.newaxis, :]

        buf_ptr = self._buffer_len - 1  # points to "current" slot
        theta = self._theta0.copy()
        buffer[buf_ptr] = theta

        phases[0] = theta
        R_arr[0] = _order_parameter(theta)

        for k in range(steps):
            theta = self._dde_rk4_step(theta, k * dt, buffer, buf_ptr, dt)
            buf_ptr = (buf_ptr + 1) % self._buffer_len
            buffer[buf_ptr] = theta

            phases[k + 1] = theta
            R_arr[k + 1] = _order_parameter(theta)

        return KuramotoResult(phases=phases, order_parameter=R_arr, time=time_arr, config=cfg)

    def _lookup_delayed(
        self,
        buffer: NDArray[np.float64],
        buf_ptr: int,
        t_current: float,
        dt: float,
    ) -> NDArray[np.float64]:
        """Look up θ_j(t - τ_ij) for all (i, j) pairs using interpolation.

        Returns shape (N, N) where entry [i, j] = θ_j(t - τ_ij).
        """
        N = self._cfg.N
        tau = self._tau_matrix
        delayed_phases = np.empty((N, N), dtype=np.float64)

        for j in range(N):
            # For each target oscillator j, find delayed phase for all sources
            # All rows i need θ_j(t - τ_ij)
            delays = tau[:, j]  # delays from all i to j
            steps_back = delays / dt
            idx_floor = np.floor(steps_back).astype(int)
            frac = steps_back - idx_floor

            for i in range(N):
                sb = idx_floor[i]
                f = frac[i]
                # Linear interpolation between buffer slots
                idx0 = (buf_ptr - sb) % self._buffer_len
                idx1 = (buf_ptr - sb - 1) % self._buffer_len
                delayed_phases[i, j] = (1.0 - f) * buffer[idx0, j] + f * buffer[idx1, j]

        return delayed_phases

    def _dde_dtheta_dt(
        self,
        theta: NDArray[np.float64],
        t_current: float,
        buffer: NDArray[np.float64],
        buf_ptr: int,
        dt: float,
    ) -> NDArray[np.float64]:
        """DDE right-hand side with delayed coupling."""
        delayed = self._lookup_delayed(buffer, buf_ptr, t_current, dt)
        # delayed[i, j] = θ_j(t - τ_ij)
        # sin(θ_j(t-τ) - θ_i(t))
        sin_diff = np.sin(delayed - theta[:, np.newaxis])
        coupling = (self._adj * sin_diff).sum(axis=1)
        result: NDArray[np.float64] = self._omega + coupling
        return result

    def _dde_rk4_step(
        self,
        theta: NDArray[np.float64],
        t: float,
        buffer: NDArray[np.float64],
        buf_ptr: int,
        dt: float,
    ) -> NDArray[np.float64]:
        """RK4 step for DDE system."""
        k1 = self._dde_dtheta_dt(theta, t, buffer, buf_ptr, dt)
        k2 = self._dde_dtheta_dt(theta + 0.5 * dt * k1, t + 0.5 * dt, buffer, buf_ptr, dt)
        k3 = self._dde_dtheta_dt(theta + 0.5 * dt * k2, t + 0.5 * dt, buffer, buf_ptr, dt)
        k4 = self._dde_dtheta_dt(theta + dt * k3, t + dt, buffer, buf_ptr, dt)
        return theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

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
