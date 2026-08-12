# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Tests for the minimal Kuramoto integrator (C2.3 dependency).

The integrator is the shared simulation primitive consumed by the
CRN validator (C2.3) and the sweep runner (C2.4). These tests pin
its determinism, shape, and physical-sanity contracts.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_kuramoto import (
    DEFAULT_OMEGA_GAMMA,
    DEFAULT_STEPS_PER_QUARTER,
    IntegratorInvalid,
    simulate_kuramoto,
)
from research.systemic_risk.d002c_substrates import (
    T_HORIZON,
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
)


def _block_K(N: int = 50, lambda_: float = 0.0, seed: int = 42) -> np.ndarray:
    return BlockStructuredSubstrate().realize(N=N, lambda_=lambda_, seed=seed).K_baseline


# ---------------------------------------------------------------------------
# Shape + sanity
# ---------------------------------------------------------------------------


def test_simulate_returns_kuramoto_trajectory_correct_shape() -> None:
    K = _block_K(N=30)
    traj = simulate_kuramoto(K, seed=0, steps_per_quarter=5)
    assert traj.R.shape == (T_HORIZON * 5,)
    assert traj.theta is not None
    assert traj.theta.shape == (T_HORIZON * 5, 30)
    assert traj.steps_per_quarter == 5
    assert traj.horizon_quarters == T_HORIZON


def test_simulate_R_in_unit_interval() -> None:
    K = _block_K(N=50)
    traj = simulate_kuramoto(K, seed=7)
    assert traj.R.min() >= 0.0
    assert traj.R.max() <= 1.0


def test_simulate_R_and_theta_finite() -> None:
    K = _block_K(N=50)
    traj = simulate_kuramoto(K, seed=7)
    assert np.all(np.isfinite(traj.R))
    assert traj.theta is not None
    assert np.all(np.isfinite(traj.theta))


def test_simulate_theta_wrapped_to_pi_interval() -> None:
    K = _block_K(N=30)
    traj = simulate_kuramoto(K, seed=0)
    assert traj.theta is not None
    assert traj.theta.min() >= -np.pi - 1e-9
    assert traj.theta.max() <= np.pi + 1e-9


# ---------------------------------------------------------------------------
# Determinism — the load-bearing contract for CRN
# ---------------------------------------------------------------------------


def test_simulate_bit_exact_same_seed() -> None:
    K = _block_K(N=40)
    a = simulate_kuramoto(K, seed=42)
    b = simulate_kuramoto(K, seed=42)
    assert np.array_equal(a.R, b.R)
    assert a.theta is not None and b.theta is not None
    assert np.array_equal(a.theta, b.theta)


def test_simulate_different_seeds_yield_different_trajectories() -> None:
    K = _block_K(N=40)
    a = simulate_kuramoto(K, seed=1)
    b = simulate_kuramoto(K, seed=2)
    assert not np.array_equal(a.R, b.R)


def test_simulate_same_K_seed_differs_per_K() -> None:
    """Same seed but different K must yield different trajectories — the
    integrator must actually USE K (CRN paired-protocol depends on this:
    if integrator ignored K, K_precursor vs K_baseline would produce
    identical trajectories and the precursor would be invisible)."""
    K_base = _block_K(N=40, lambda_=0.0)
    K_pre = BlockStructuredSubstrate().realize(N=40, lambda_=1.0, seed=42).K_precursor
    a = simulate_kuramoto(K_base, seed=0)
    b = simulate_kuramoto(K_pre, seed=0)
    assert not np.array_equal(a.R, b.R)


def test_record_theta_false_returns_none() -> None:
    K = _block_K(N=30)
    traj = simulate_kuramoto(K, seed=0, record_theta=False)
    assert traj.theta is None
    assert traj.R.shape == (T_HORIZON * DEFAULT_STEPS_PER_QUARTER,)


# ---------------------------------------------------------------------------
# Contract: input validation
# ---------------------------------------------------------------------------


def test_simulate_rejects_2d_K() -> None:
    K = np.eye(10, dtype=np.float64)
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0)


def test_simulate_rejects_non_square_K() -> None:
    K = np.zeros((T_HORIZON, 10, 12), dtype=np.float64)
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0)


def test_simulate_rejects_non_finite_K() -> None:
    K = _block_K(N=10).copy()
    K[0, 0, 0] = np.nan
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0)


def test_simulate_rejects_non_positive_steps_per_quarter() -> None:
    K = _block_K(N=10)
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0, steps_per_quarter=0)


def test_simulate_rejects_non_positive_omega_gamma() -> None:
    K = _block_K(N=10)
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0, omega_gamma=0.0)
    with pytest.raises(IntegratorInvalid):
        simulate_kuramoto(K, seed=0, omega_gamma=float("nan"))


# ---------------------------------------------------------------------------
# Physical sanity
# ---------------------------------------------------------------------------


def test_simulate_ricci_substrate_runs_cleanly() -> None:
    """Every D-002C substrate must be integrable end-to-end."""
    K = RicciFlowSubstrate().realize(N=50, lambda_=0.0, seed=42).K_baseline
    traj = simulate_kuramoto(K, seed=0)
    assert np.all(np.isfinite(traj.R))


def test_default_constants_match_locked_values() -> None:
    """Sanity guard against accidental edits of the module-level defaults."""
    assert DEFAULT_STEPS_PER_QUARTER == 10
    assert DEFAULT_OMEGA_GAMMA == 0.5
