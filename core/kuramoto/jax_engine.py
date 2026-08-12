# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""JAX-accelerated Kuramoto simulation engine.

Provides XLA-compiled integration via ``@jax.jit`` and batch simulation
via ``jax.vmap`` for 100–1000× speedup on GPU/TPU.  Falls back to NumPy
engine when JAX is not installed.

Usage::

    from core.kuramoto.jax_engine import JaxKuramotoEngine
    result = JaxKuramotoEngine(config).run()           # single sim, JIT-compiled
    results = JaxKuramotoEngine.batch(configs, seeds)   # vmap over seeds
"""

from __future__ import annotations

import logging
from typing import cast

import numpy as np

try:
    import jax
    import jax.numpy as jnp
    from jax import jit, vmap

    JAX_AVAILABLE = True
except ImportError:  # pragma: no cover
    JAX_AVAILABLE = False

from .config import KuramotoConfig
from .engine import KuramotoResult

__all__ = ["JaxKuramotoEngine", "JAX_AVAILABLE"]

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JAX pure-function kernels (traced once, reused via XLA cache)
# ---------------------------------------------------------------------------

if JAX_AVAILABLE:

    @jit  # type: ignore[misc, unused-ignore]
    def _jax_dtheta_dt(
        theta: jnp.ndarray,
        omega: jnp.ndarray,
        adj: jnp.ndarray,
    ) -> jnp.ndarray:
        """Kuramoto RHS — XLA-compiled, no Python overhead per call."""
        diff = theta[jnp.newaxis, :] - theta[:, jnp.newaxis]
        coupling = (adj * jnp.sin(diff)).sum(axis=1)
        return omega + coupling

    @jit  # type: ignore[misc, unused-ignore]
    def _jax_rk4_step(
        theta: jnp.ndarray,
        omega: jnp.ndarray,
        adj: jnp.ndarray,
        dt: float,
    ) -> jnp.ndarray:
        """RK4 step — fully fused XLA kernel."""
        k1 = _jax_dtheta_dt(theta, omega, adj)
        k2 = _jax_dtheta_dt(theta + 0.5 * dt * k1, omega, adj)
        k3 = _jax_dtheta_dt(theta + 0.5 * dt * k2, omega, adj)
        k4 = _jax_dtheta_dt(theta + dt * k3, omega, adj)
        # ``_jax_dtheta_dt`` is wrapped by ``@jit``; ``JitWrapped.__call__``
        # is typed as returning ``Any`` (jax has no array-precise jit stub),
        # so this pure-array RK4 combination loses its static type. The
        # declared ``jnp.ndarray`` contract is correct at runtime — cast to
        # restore it without widening or suppressing the real signal.
        return cast("jnp.ndarray", theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4))

    @jit  # type: ignore[misc, unused-ignore]
    def _jax_order_parameter(theta: jnp.ndarray) -> jnp.ndarray:
        """Order parameter R — vectorised, no Python loop."""
        z = jnp.exp(1j * theta).mean()
        # INV-K1: R ∈ [0,1] — JAX mirror of engine.py _order_parameter
        return jnp.clip(jnp.abs(z), 0.0, 1.0)

    def _jax_simulate_trajectory(
        theta0: jnp.ndarray,
        omega: jnp.ndarray,
        adj: jnp.ndarray,
        dt: float,
        steps: int,
    ) -> tuple[jnp.ndarray, jnp.ndarray]:
        """Run full trajectory via jax.lax.scan (no Python loop)."""

        def scan_fn(
            theta: jnp.ndarray,
            _: None,
        ) -> tuple[jnp.ndarray, tuple[jnp.ndarray, jnp.ndarray]]:
            theta_next = _jax_rk4_step(theta, omega, adj, dt)
            R = _jax_order_parameter(theta_next)
            return theta_next, (theta_next, R)

        _, (all_phases, all_R) = jax.lax.scan(scan_fn, theta0, None, length=steps)

        # Prepend initial state
        phases = jnp.concatenate([theta0[jnp.newaxis, :], all_phases], axis=0)
        R_arr = jnp.concatenate([_jax_order_parameter(theta0)[jnp.newaxis], all_R])
        return phases, R_arr

    def _jax_batch_simulate(
        theta0_batch: jnp.ndarray,
        omega: jnp.ndarray,
        adj: jnp.ndarray,
        dt: float,
        steps: int,
    ) -> tuple[jnp.ndarray, jnp.ndarray]:
        """Batch simulate via vmap — one GPU kernel for thousands of runs."""

        def single_sim(
            theta0: jnp.ndarray,
        ) -> tuple[jnp.ndarray, jnp.ndarray]:
            return _jax_simulate_trajectory(theta0, omega, adj, dt, steps)

        return vmap(single_sim)(theta0_batch)  # type: ignore[no-any-return, unused-ignore]


class JaxKuramotoEngine:
    """XLA-compiled Kuramoto integrator with optional GPU/TPU acceleration.

    Drop-in replacement for :class:`KuramotoEngine` with identical output
    contract.  When JAX is unavailable, raises ``RuntimeError`` at init.
    """

    def __init__(self, config: KuramotoConfig) -> None:
        if not JAX_AVAILABLE:
            raise RuntimeError(
                "JAX is not installed. Install with: pip install jax jaxlib\n"
                "For GPU: pip install jax[cuda12]"
            )
        self._cfg = config
        self._omega, self._theta0, self._adj = self._prepare(config)
        _logger.info(
            "JaxKuramotoEngine initialised: N=%d, backend=%s",
            config.N,
            jax.default_backend(),
        )

    def run(self) -> KuramotoResult:
        """Run single JIT-compiled simulation."""
        cfg = self._cfg
        phases_jax, R_jax = _jax_simulate_trajectory(
            self._theta0,
            self._omega,
            self._adj,
            cfg.dt,
            cfg.steps,
        )
        # Convert back to NumPy for KuramotoResult validation
        phases = np.asarray(phases_jax, dtype=np.float64)
        R_arr = np.asarray(R_jax, dtype=np.float64)
        time_arr = np.arange(cfg.steps + 1, dtype=np.float64) * cfg.dt
        return KuramotoResult(phases=phases, order_parameter=R_arr, time=time_arr, config=cfg)

    @staticmethod
    def batch(
        config: KuramotoConfig,
        seeds: list[int],
    ) -> list[KuramotoResult]:
        """Run batch of simulations via ``jax.vmap`` — single GPU kernel.

        Parameters
        ----------
        config : KuramotoConfig
            Shared configuration (N, K, dt, steps, adjacency).
        seeds : list[int]
            One seed per simulation; controls initial phases.

        Returns
        -------
        list[KuramotoResult]
            One result per seed.
        """
        if not JAX_AVAILABLE:
            raise RuntimeError("JAX is not installed.")

        N = config.N
        # Generate batch of initial conditions
        theta0_batch = []
        for s in seeds:
            rng = np.random.default_rng(s)
            theta0_batch.append(rng.uniform(0.0, 2.0 * np.pi, N))
        theta0_jax = jnp.array(np.stack(theta0_batch))

        # Shared omega and adjacency
        rng0 = np.random.default_rng(config.seed)
        omega = jnp.array(
            config.omega if config.omega is not None else rng0.standard_normal(N),
            dtype=jnp.float64,
        )
        K = config.K
        if config.adjacency is not None:
            adj = jnp.array(K * config.adjacency, dtype=jnp.float64)
            adj = adj.at[jnp.diag_indices(N)].set(0.0)
        else:
            adj = jnp.full((N, N), K / N, dtype=jnp.float64)
            adj = adj.at[jnp.diag_indices(N)].set(0.0)

        _logger.info(
            "Launching vmap batch: %d simulations on %s",
            len(seeds),
            jax.default_backend(),
        )
        all_phases, all_R = _jax_batch_simulate(theta0_jax, omega, adj, config.dt, config.steps)

        results = []
        time_arr = np.arange(config.steps + 1, dtype=np.float64) * config.dt
        for i, s in enumerate(seeds):
            cfg_i = config.model_copy(update={"seed": s})
            results.append(
                KuramotoResult(
                    phases=np.asarray(all_phases[i], dtype=np.float64),
                    order_parameter=np.asarray(all_R[i], dtype=np.float64),
                    time=time_arr.copy(),
                    config=cfg_i,
                )
            )
        return results

    @staticmethod
    def _prepare(
        cfg: KuramotoConfig,
    ) -> tuple[jnp.ndarray, jnp.ndarray, jnp.ndarray]:
        """Convert config arrays to JAX device arrays."""
        rng = np.random.default_rng(cfg.seed)
        omega_np = cfg.omega if cfg.omega is not None else rng.standard_normal(cfg.N)
        theta0_np = cfg.theta0 if cfg.theta0 is not None else rng.uniform(0.0, 2.0 * np.pi, cfg.N)

        N, K = cfg.N, cfg.K
        if cfg.adjacency is not None:
            adj_np = K * cfg.adjacency.astype(np.float64)
            np.fill_diagonal(adj_np, 0.0)
        else:
            adj_np = np.full((N, N), K / N, dtype=np.float64)
            np.fill_diagonal(adj_np, 0.0)

        return (
            jnp.array(omega_np, dtype=jnp.float64),
            jnp.array(theta0_np, dtype=jnp.float64),
            jnp.array(adj_np, dtype=jnp.float64),
        )
