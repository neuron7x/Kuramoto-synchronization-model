# SPDX-License-Identifier: MIT
from __future__ import annotations

import jax.numpy as jnp
import numpy as np

from core.kuramoto.kuramoto_ricci_engine import kuramoto_ricci_trajectory, order_parameter

NULL_MODEL_MATRIX = [
    {
        "id": "K_ZERO",
        "observable": "late_order_parameter",
        "expected_relation": "below_finite_size_bound",
        "test_name": "test_null_k_zero_independent_oscillators_do_not_lock",
    },
    {
        "id": "PHASE_SHUFFLE",
        "observable": "single_step_order_parameter",
        "expected_relation": "below_finite_size_bound",
        "test_name": "test_null_phase_shuffle_preserves_finite_size_low_R",
    },
    {
        "id": "WEAK_RANDOM_OMEGA",
        "observable": "late_order_parameter",
        "expected_relation": "below_sync_threshold",
        "test_name": "test_null_randomized_omega_with_weak_coupling_does_not_fake_strong_sync",
    },
    {
        "id": "MATCHED_ER_WEAK",
        "observable": "late_order_parameter",
        "expected_relation": "below_sync_threshold",
        "test_name": "test_matched_er_null_has_bounded_order_parameter_under_weak_coupling",
    },
]


def _omega(rng: np.random.Generator, n: int) -> jnp.ndarray:
    omega = rng.normal(0.0, 0.2, size=n)
    omega -= float(np.mean(omega))
    return jnp.asarray(omega)


def test_null_model_matrix_lists_all_executable_cases() -> None:
    ids = {entry["id"] for entry in NULL_MODEL_MATRIX}
    tests = {entry["test_name"] for entry in NULL_MODEL_MATRIX}
    assert ids == {"K_ZERO", "PHASE_SHUFFLE", "WEAK_RANDOM_OMEGA", "MATCHED_ER_WEAK"}
    assert tests == {
        "test_null_k_zero_independent_oscillators_do_not_lock",
        "test_null_phase_shuffle_preserves_finite_size_low_R",
        "test_null_randomized_omega_with_weak_coupling_does_not_fake_strong_sync",
        "test_matched_er_null_has_bounded_order_parameter_under_weak_coupling",
    }


def test_null_model_matrix_has_observable_and_relation() -> None:
    for entry in NULL_MODEL_MATRIX:
        assert entry["observable"] in {
            "late_order_parameter",
            "single_step_order_parameter",
        }
        assert entry["expected_relation"] in {
            "below_finite_size_bound",
            "below_sync_threshold",
        }


def test_null_k_zero_independent_oscillators_do_not_lock() -> None:
    n = 64
    rng = np.random.default_rng(201)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    omega = _omega(rng, n)
    A = jnp.zeros((n, n))
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=1000, omega=omega, A=A)
    R_late = float(jnp.mean(order_parameter(traj[500:])))
    finite_size_bound = 3.0 / np.sqrt(n)
    assert R_late < 2.0 * finite_size_bound


def test_null_phase_shuffle_preserves_finite_size_low_R() -> None:
    n = 128
    rng = np.random.default_rng(202)
    theta = rng.uniform(-np.pi, np.pi, size=n)
    shuffled = jnp.asarray(rng.permutation(theta))
    R = float(order_parameter(shuffled))
    assert R < 3.0 / np.sqrt(n)


def test_null_randomized_omega_with_weak_coupling_does_not_fake_strong_sync() -> None:
    n = 48
    rng = np.random.default_rng(203)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    omega = _omega(rng, n)
    A = jnp.ones((n, n)) - jnp.eye(n)
    weak_A = (0.001 / n) * A
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=800, omega=omega, A=weak_A)
    R_late = float(jnp.mean(order_parameter(traj[400:])))
    assert R_late < 0.5


def test_matched_er_null_has_bounded_order_parameter_under_weak_coupling() -> None:
    n = 64
    rng = np.random.default_rng(204)
    upper = rng.binomial(1, 0.25, size=(n, n)).astype(float)
    upper = np.triu(upper, k=1)
    A = jnp.asarray((upper + upper.T) / n)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    omega = _omega(rng, n)
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=800, omega=omega, A=0.01 * A)
    R_late = float(jnp.mean(order_parameter(traj[400:])))
    assert R_late < 0.5
