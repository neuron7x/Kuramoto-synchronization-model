# SPDX-License-Identifier: MIT
from __future__ import annotations

import jax.numpy as jnp
import numpy as np

from core.kuramoto.kuramoto_ricci_engine import (
    kuramoto_ricci_trajectory,
    order_parameter,
)


def _scenario(seed: int, *, dt: float) -> float:
    rng = np.random.default_rng(seed)
    n = 16
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n), dtype=jnp.float32)
    omega = rng.normal(0.0, 0.12, size=n)
    omega -= float(np.mean(omega))
    adjacency = (
        0.02
        * (np.ones((n, n), dtype=np.float32) - np.eye(n, dtype=np.float32))
        / n
    )
    traj = kuramoto_ricci_trajectory(
        theta_0,
        dt=dt,
        n_steps=int(round(1.0 / dt)),
        omega=jnp.asarray(omega, dtype=jnp.float32),
        A=jnp.asarray(adjacency, dtype=jnp.float32),
    )
    return float(jnp.mean(order_parameter(traj[-10:])))


def test_uq_smoke_has_declared_initial_condition_source() -> None:
    values = np.asarray([_scenario(seed, dt=0.05) for seed in range(8)], dtype=float)
    assert values.shape == (8,)
    assert np.all(np.isfinite(values))
    assert float(np.std(values)) > 0.0
    assert 0.0 <= float(np.min(values)) <= float(np.max(values)) <= 1.0


def test_solver_tolerance_smoke_is_stable_under_dt_refinement() -> None:
    coarse = np.asarray([_scenario(seed, dt=0.05) for seed in range(4)], dtype=float)
    fine = np.asarray([_scenario(seed, dt=0.025) for seed in range(4)], dtype=float)
    drift = float(np.max(np.abs(coarse - fine)))
    assert drift < 0.08
