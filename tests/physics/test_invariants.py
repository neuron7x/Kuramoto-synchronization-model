# SPDX-License-Identifier: MIT
from __future__ import annotations

import jax.numpy as jnp
import numpy as np
import pytest

from core.kuramoto.kuramoto_ricci_engine import (
    kuramoto_ricci_trajectory,
    order_parameter,
    phase_transition_boundary,
)


def test_order_parameter_batch_stays_in_unit_interval() -> None:
    rng = np.random.default_rng(123)
    theta = jnp.asarray(rng.uniform(-20.0 * np.pi, 20.0 * np.pi, size=(32, 64)))
    R = order_parameter(theta)
    assert bool(jnp.all(jnp.isfinite(R)))
    assert bool(jnp.all(R >= 0.0))
    assert bool(jnp.all(R <= 1.0))


def test_phase_transition_boundary_rejects_invalid_signed_adjacency() -> None:
    A = jnp.asarray([[0.0, -0.25], [-0.25, 0.0]])
    with pytest.raises(ValueError, match="non-negative"):
        phase_transition_boundary(K=1.0, lorentzian_half_width=0.5, A=A)


def test_trajectory_outputs_finite_theta() -> None:
    theta_0 = jnp.asarray([0.1, -0.2, 0.3, -0.4])
    omega = jnp.asarray([0.01, -0.02, 0.03, -0.01])
    A = jnp.ones((4, 4)) - jnp.eye(4)
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.01, n_steps=100, omega=omega, A=0.1 * A)
    assert traj.shape == (101, 4)
    assert bool(jnp.all(jnp.isfinite(traj)))


def test_zero_adjacency_has_infinite_critical_coupling() -> None:
    A = jnp.zeros((5, 5))
    report = phase_transition_boundary(K=1.0, lorentzian_half_width=0.4, A=A)
    assert report.K_c == float("inf")
    assert report.phi == -0.8
