# SPDX-License-Identifier: MIT
from __future__ import annotations

import jax.numpy as jnp
import numpy as np

from core.kuramoto.kuramoto_ricci_engine import kuramoto_ricci_trajectory


def _final_state(dt: float, total_time: float = 0.4) -> jnp.ndarray:
    n_steps = int(round(total_time / dt))
    theta_0 = jnp.asarray([0.2, -0.1, 0.4, -0.3], dtype=jnp.float32)
    omega = jnp.asarray([0.03, -0.01, 0.02, -0.04], dtype=jnp.float32)
    adjacency = 0.05 * (
        jnp.ones((4, 4), dtype=jnp.float32) - jnp.eye(4, dtype=jnp.float32)
    )
    return kuramoto_ricci_trajectory(
        theta_0,
        dt=dt,
        n_steps=n_steps,
        omega=omega,
        A=adjacency,
    )[-1]


def _linf(a: jnp.ndarray, b: jnp.ndarray) -> float:
    return float(jnp.max(jnp.abs(a - b)))


def test_midpoint_refinement_reduces_final_state_error() -> None:
    """dt -> dt/2 -> dt/4 must move toward a stable reference state."""
    coarse = _final_state(0.04)
    medium = _final_state(0.02)
    fine = _final_state(0.01)
    err_coarse = _linf(coarse, fine)
    err_medium = _linf(medium, fine)
    assert err_medium <= err_coarse
    assert err_coarse < 1e-3


def test_k_zero_integrates_constant_velocity_exactly_within_float32_noise() -> None:
    theta_0 = jnp.asarray([0.1, -0.2, 0.3], dtype=jnp.float32)
    omega = jnp.asarray([0.01, -0.02, 0.03], dtype=jnp.float32)
    adjacency = jnp.zeros((3, 3), dtype=jnp.float32)
    dt = 0.05
    n_steps = 20
    traj = kuramoto_ricci_trajectory(
        theta_0,
        dt=dt,
        n_steps=n_steps,
        omega=omega,
        A=adjacency,
    )
    expected = theta_0 + omega * dt * n_steps
    np.testing.assert_allclose(
        np.asarray(traj[-1]),
        np.asarray(expected),
        rtol=1e-6,
        atol=1e-6,
    )
