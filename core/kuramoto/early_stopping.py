# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Early stopping strategy for Kuramoto simulations.

Detects steady-state convergence via exponential moving average of R(t).
When the order parameter stabilizes (|ΔR̄| < ε for N consecutive steps),
the simulation terminates early — saving up to 70% of compute in cloud.

Follows the Resource Governance invariant: no wasted cycles.

Usage::

    from core.kuramoto.early_stopping import EarlyStoppingEngine
    config = KuramotoConfig(N=100, K=3.0, steps=50000)
    result = EarlyStoppingEngine(config, epsilon=1e-5, patience=200).run()
    print(f"Converged at step {result.summary['converged_at_step']}")
"""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter, _rk4_step

__all__ = ["EarlyStoppingEngine"]

_logger = logging.getLogger(__name__)


class EarlyStoppingEngine:
    """Kuramoto integrator with convergence-based early termination.

    Parameters
    ----------
    config : KuramotoConfig
        Standard config.  ``steps`` is treated as **maximum** steps.
    epsilon : float
        Convergence threshold: stop when |EMA(R) change| < epsilon.
    patience : int
        Number of consecutive steps the criterion must hold.
    ema_alpha : float
        Exponential moving average decay.  Smaller = smoother.
        Default 0.01 (≈100-step effective window).
    min_steps : int
        Minimum steps before early stopping can trigger (warmup).
    """

    def __init__(
        self,
        config: KuramotoConfig,
        epsilon: float = 1e-5,
        patience: int = 200,
        ema_alpha: float = 0.01,
        min_steps: int = 100,
    ) -> None:
        self._cfg = config
        self._epsilon = epsilon
        self._patience = patience
        self._alpha = ema_alpha
        self._min_steps = min_steps

        rng = np.random.default_rng(config.seed)
        self._omega = (
            config.omega.astype(np.float64, copy=False)
            if config.omega is not None
            else rng.standard_normal(config.N)
        )
        self._theta0 = (
            config.theta0.astype(np.float64, copy=False)
            if config.theta0 is not None
            else rng.uniform(0.0, 2.0 * np.pi, config.N)
        )
        self._adj = self._resolve_adj(config)

    def run(self) -> KuramotoResult:
        """Integrate with early stopping on R(t) convergence."""
        cfg = self._cfg
        max_steps = cfg.steps
        dt = cfg.dt

        # Pre-allocate for max, truncate later
        phases_list = []
        R_list = []

        theta = self._theta0.copy()
        R0 = _order_parameter(theta)
        phases_list.append(theta.copy())
        R_list.append(R0)

        ema_R = R0
        prev_ema = R0
        stable_count = 0
        converged_step = max_steps  # default: ran to completion

        for k in range(max_steps):
            theta = _rk4_step(theta, self._omega, self._adj, dt)
            R = _order_parameter(theta)

            phases_list.append(theta.copy())
            R_list.append(R)

            # Update EMA
            ema_R = self._alpha * R + (1.0 - self._alpha) * ema_R
            delta = abs(ema_R - prev_ema)
            prev_ema = ema_R

            if k >= self._min_steps:
                if delta < self._epsilon:
                    stable_count += 1
                    if stable_count >= self._patience:
                        converged_step = k + 1
                        _logger.info(
                            "Early stopping at step %d/%d: ΔR̄=%.2e < ε=%.2e "
                            "(patience=%d met), saved %.1f%% compute",
                            converged_step,
                            max_steps,
                            delta,
                            self._epsilon,
                            self._patience,
                            100.0 * (1.0 - converged_step / max_steps),
                        )
                        break
                else:
                    stable_count = 0

        actual_steps = len(R_list) - 1
        phases = np.array(phases_list, dtype=np.float64)
        R_arr = np.array(R_list, dtype=np.float64)
        time_arr = np.arange(actual_steps + 1, dtype=np.float64) * dt

        # Create config with actual steps for validation
        actual_cfg = cfg.model_copy(update={"steps": actual_steps})

        result = KuramotoResult(
            phases=phases,
            order_parameter=R_arr,
            time=time_arr,
            config=actual_cfg,
        )
        result.summary["converged_at_step"] = converged_step
        result.summary["max_steps"] = max_steps
        result.summary["early_stopped"] = converged_step < max_steps
        result.summary["compute_saved_pct"] = (
            100.0 * (1.0 - converged_step / max_steps) if converged_step < max_steps else 0.0
        )

        return result

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
