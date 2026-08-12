# SPDX-License-Identifier: MIT
from __future__ import annotations

import jax.numpy as jnp

from core.kuramoto.kuramoto_ricci_engine import (
    kuramoto_ricci_trajectory,
    order_parameter,
    phase_transition_boundary,
)


def test_geosync_output_contract_shapes_units_ranges() -> None:
    theta_0 = jnp.asarray([0.1, 0.2, -0.1, -0.2])
    omega = jnp.asarray([0.01, -0.01, 0.02, -0.02])
    A = 0.1 * (jnp.ones((4, 4)) - jnp.eye(4))
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.01, n_steps=50, omega=omega, A=A)
    R = order_parameter(traj)
    report = phase_transition_boundary(K=0.1, lorentzian_half_width=0.5, A=A)

    assert traj.shape == (51, 4)
    assert R.shape == (51,)
    assert bool(jnp.all(jnp.isfinite(traj)))
    assert bool(jnp.all((R >= 0.0) & (R <= 1.0)))
    assert report.lambda_max_A >= 0.0
    assert report.K_c > 0.0 or report.K_c == float("inf")


def test_adjacency_input_contract() -> None:
    A = jnp.asarray(
        [
            [0.0, 0.2, 0.3],
            [0.2, 0.0, 0.1],
            [0.3, 0.1, 0.0],
        ]
    )
    assert A.shape == (3, 3)
    assert bool(jnp.all(A >= 0.0))
    assert bool(jnp.allclose(A, A.T))
    assert bool(jnp.all(jnp.diag(A) == 0.0))
