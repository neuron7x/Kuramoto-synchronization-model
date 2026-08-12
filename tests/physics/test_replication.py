# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
from pathlib import Path

import jax.numpy as jnp
import numpy as np

from core.kuramoto.kuramoto_ricci_engine import (
    kuramoto_ricci_trajectory,
    order_parameter,
)


def _load_reference_solver():
    path = (
        Path(__file__).resolve().parents[2]
        / "reproducibility"
        / "reference_solvers"
        / "geosync_kuramoto_numpy.py"
    )
    spec = importlib.util.spec_from_file_location("geosync_kuramoto_numpy", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_numpy_reference_solver_matches_jax_midpoint_trajectory() -> None:
    ref = _load_reference_solver()
    theta_0 = np.asarray([0.2, -0.1, 0.4, -0.3], dtype=np.float64)
    omega = np.asarray([0.03, -0.01, 0.02, -0.04], dtype=np.float64)
    adjacency = 0.03 * (
        np.ones((4, 4), dtype=np.float64) - np.eye(4, dtype=np.float64)
    )

    numpy_traj = ref.kuramoto_numpy_trajectory(
        theta_0,
        dt=0.01,
        n_steps=50,
        omega=omega,
        adjacency=adjacency,
    )
    jax_traj = kuramoto_ricci_trajectory(
        jnp.asarray(theta_0),
        dt=0.01,
        n_steps=50,
        omega=jnp.asarray(omega),
        A=jnp.asarray(adjacency),
    )

    np.testing.assert_allclose(
        np.asarray(jax_traj),
        numpy_traj,
        rtol=1e-6,
        atol=1e-6,
    )


def test_numpy_reference_order_parameter_matches_jax_observable() -> None:
    ref = _load_reference_solver()
    theta = np.asarray(
        [
            [0.1, 0.2, -0.3, 0.4],
            [0.2, 0.1, -0.2, 0.5],
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(
        ref.order_parameter_numpy(theta),
        np.asarray(order_parameter(jnp.asarray(theta))),
    )
