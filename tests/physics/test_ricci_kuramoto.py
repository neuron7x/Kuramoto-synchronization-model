# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for ricci_energy_nonincrease and kuramoto_order_parameter_bounds."""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.ricci_kuramoto import (
    compute_order_parameter,
    hybrid_step,
    kuramoto_step,
    ricci_energy,
    ricci_flow_step,
    trajectory_hash,
)


def test_ricci_energy_nonincreases() -> None:
    """Positive witness: dispersion energy never increases under the contraction flow."""
    rng = np.random.default_rng(7)
    violations = 0
    for _ in range(20):
        curv = rng.normal(0.0, 2.0, size=16)
        energy_prev = ricci_energy(curv)
        for _ in range(50):
            curv = ricci_flow_step(curv, dt=0.3)
            energy = ricci_energy(curv)
            if energy > energy_prev * (1.0 + 1e-9):
                violations += 1
            energy_prev = energy
    assert violations == 0, (
        f"RICCI-ENERGY VIOLATED: {violations} steps increased dispersion energy "
        f"beyond tol=1e-9 under a contraction flow (dt=0.3). E(c)=sum (c-mean)^2 "
        f"must be a Lyapunov functional. seeds=20, steps=50"
    )


def test_energy_injection_flow_is_rejected() -> None:
    """Negative control: a non-contractive flow step (dt outside (0,1]) is rejected."""
    curv = np.array([1.0, -1.0, 0.5, 0.0])
    for bad_dt in (1.5, 0.0, -0.3):
        with pytest.raises(ValueError, match="dt must be in"):
            ricci_flow_step(curv, dt=bad_dt)


def test_order_parameter_within_unit_interval() -> None:
    """Positive witness: R(t) in [0,1] across a seeded mean-field sweep."""
    rng = np.random.default_rng(11)
    lo, hi = 1.0, 0.0
    for _ in range(50):
        phases = rng.uniform(-np.pi, np.pi, size=32)
        r = compute_order_parameter(phases)
        lo, hi = min(lo, r), max(hi, r)
    assert 0.0 <= lo <= hi <= 1.0, (
        f"KURAMOTO-R VIOLATED: observed R range [{lo:.6f}, {hi:.6f}] left [0,1]. "
        f"R=|mean(exp(i theta))| is a modulus of a convex combination of unit "
        f"vectors. realizations=50, N=32"
    )


def test_out_of_range_order_parameter_is_rejected() -> None:
    """Negative control: non-finite/empty phases fail closed (no garbage R)."""
    for bad in ([np.nan, 0.1], [], [np.inf]):
        with pytest.raises(ValueError):
            compute_order_parameter(bad)


def test_invalid_causal_mask_is_rejected() -> None:
    """A non-boolean or shape-mismatched causal mask fails closed."""
    state = {
        "phases": np.array([0.1, 0.2, 0.3]),
        "curvatures": np.array([0.0, 0.5, -0.5]),
        "coupling": 1.0,
    }
    with pytest.raises(ValueError, match="causal_mask must be boolean"):
        hybrid_step(state, 0.1, np.array([1, 0, 1]))
    with pytest.raises(ValueError, match="must match phases shape"):
        hybrid_step(state, 0.1, np.array([True, False]))


def test_future_state_injection_is_rejected() -> None:
    """An all-False (no admissible past) mask is rejected — no future injection."""
    state = {
        "phases": np.array([0.1, 0.2, 0.3]),
        "curvatures": np.array([0.0, 0.5, -0.5]),
        "coupling": 1.0,
    }
    with pytest.raises(ValueError, match="admits no oscillator"):
        hybrid_step(state, 0.1, np.array([False, False, False]))


def test_seeded_trajectory_hash_is_identical() -> None:
    """Fixed seed gives a bit-identical trajectory hash on replay."""
    def run() -> np.ndarray:
        rng = np.random.default_rng(42)
        phases = rng.uniform(-np.pi, np.pi, size=8)
        traj = [phases.copy()]
        for _ in range(25):
            phases = kuramoto_step(phases, 1.3, 0.05)
            traj.append(phases.copy())
        return np.array(traj)

    assert trajectory_hash(run()) == trajectory_hash(run())
