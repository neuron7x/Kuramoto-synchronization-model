# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the Kuramoto extensions (Sakaguchi α, triadic, explosive)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.systemic_risk.kuramoto_extensions import (
    ExplosiveSyncReport,
    HigherOrderConfig,
    explosive_sync_sweep,
    kuramoto_order_parameter,
    sakaguchi_kuramoto_step,
    triadic_kuramoto_step,
)


class TestOrderParameter:
    def test_aligned_phases_yield_one(self) -> None:
        theta = np.zeros(100, dtype=np.float64)
        assert kuramoto_order_parameter(theta) == pytest.approx(1.0)

    def test_uniform_distribution_near_zero(self) -> None:
        rng = np.random.default_rng(seed=123)
        theta = rng.uniform(-math.pi, math.pi, 1000)
        # Finite sample noise: expect ~1/sqrt(N) ≈ 0.032
        assert kuramoto_order_parameter(theta) < 0.1

    def test_invalid_shape_rejects(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            kuramoto_order_parameter(np.zeros((3, 3), dtype=np.float64))


class TestSakaguchiStep:
    def test_zero_alpha_matches_standard_kuramoto(self) -> None:
        # With α=0 the step should reduce to standard Kuramoto.
        n = 5
        rng = np.random.default_rng(seed=42)
        theta = rng.uniform(-math.pi, math.pi, n)
        omega = np.zeros(n, dtype=np.float64)
        coupling = np.full((n, n), 0.5, dtype=np.float64)
        np.fill_diagonal(coupling, 0.0)
        alpha = np.zeros((n, n), dtype=np.float64)
        new = sakaguchi_kuramoto_step(theta, omega=omega, coupling=coupling, alpha=alpha, dt=0.01)
        assert new.shape == theta.shape
        assert np.all(np.isfinite(new))

    def test_nonzero_alpha_breaks_synchronization(self) -> None:
        # With heterogeneous ω the frustration parameter α reduces the
        # *effective* coupling: the SK steady-state order parameter on
        # an all-to-all graph is r ≈ √(1 - K_c/K) with
        # K_c = 2γ / cos(α) (Sakaguchi 1986, eq. 9). Hence α near π/2
        # blows up K_c and brings the system close to incoherence,
        # while α = 0 reaches near-perfect synchronization.
        n = 30
        rng = np.random.default_rng(seed=7)
        theta0 = rng.uniform(-math.pi, math.pi, n)
        omega = rng.normal(0.0, 1.0, n)  # heterogeneous frequencies
        coupling = np.full((n, n), 1.5 / (n - 1), dtype=np.float64)
        np.fill_diagonal(coupling, 0.0)
        alpha_zero = np.zeros((n, n), dtype=np.float64)
        # Use α just below π/2 so that cos(α) > 0 (system still defined)
        # but K_c scales by 1/cos(α) ~ 6.4×, pushing the regime
        # subcritical for our K = 1.5.
        alpha_strong = np.full((n, n), 1.42, dtype=np.float64)  # ≈ 81 deg

        theta_a = theta0.copy()
        theta_b = theta0.copy()
        # Long burn-in to reach steady state.
        r_a_history: list[float] = []
        r_b_history: list[float] = []
        for step in range(2000):
            theta_a = sakaguchi_kuramoto_step(
                theta_a, omega=omega, coupling=coupling, alpha=alpha_zero, dt=0.05
            )
            theta_b = sakaguchi_kuramoto_step(
                theta_b, omega=omega, coupling=coupling, alpha=alpha_strong, dt=0.05
            )
            if step >= 1500:
                r_a_history.append(kuramoto_order_parameter(theta_a))
                r_b_history.append(kuramoto_order_parameter(theta_b))
        r_zero = float(np.mean(r_a_history))
        r_strong = float(np.mean(r_b_history))
        # Time-averaged steady-state r should be substantially lower
        # under strong frustration.
        assert r_zero > r_strong + 0.10, (
            f"Expected α=0 to synchronize more than α≈π/2; "
            f"r_zero={r_zero:.3f}, r_strong={r_strong:.3f}"
        )

    def test_invalid_shapes_rejected(self) -> None:
        n = 5
        theta = np.zeros(n, dtype=np.float64)
        with pytest.raises(ValueError, match="omega"):
            sakaguchi_kuramoto_step(
                theta,
                omega=np.zeros(3, dtype=np.float64),
                coupling=np.zeros((n, n), dtype=np.float64),
                alpha=np.zeros((n, n), dtype=np.float64),
                dt=0.01,
            )

    def test_invalid_dt_rejected(self) -> None:
        n = 3
        theta = np.zeros(n, dtype=np.float64)
        with pytest.raises(ValueError, match="dt"):
            sakaguchi_kuramoto_step(
                theta,
                omega=np.zeros(n, dtype=np.float64),
                coupling=np.zeros((n, n), dtype=np.float64),
                alpha=np.zeros((n, n), dtype=np.float64),
                dt=-0.01,
            )


class TestTriadicStep:
    def test_pure_pairwise_matches_kuramoto_limit(self) -> None:
        # K_3 = 0 → reduces to mean-field Kuramoto; with identical
        # phases the drift is exactly omega.
        n = 10
        theta = np.zeros(n, dtype=np.float64)
        omega = np.full(n, 0.3, dtype=np.float64)
        cfg = HigherOrderConfig(k2=2.0, k3=0.0)
        new = triadic_kuramoto_step(theta, omega=omega, cfg=cfg, dt=0.1)
        assert np.allclose(new, theta + 0.1 * omega)

    def test_triadic_term_changes_dynamics(self) -> None:
        # K_3 ≠ 0 must produce a non-trivial drift.
        n = 10
        rng = np.random.default_rng(seed=2)
        theta = rng.uniform(-math.pi, math.pi, n)
        omega = np.zeros(n, dtype=np.float64)
        cfg_pair = HigherOrderConfig(k2=1.0, k3=0.0)
        cfg_triad = HigherOrderConfig(k2=1.0, k3=2.0)
        new_pair = triadic_kuramoto_step(theta, omega=omega, cfg=cfg_pair, dt=0.1)
        new_triad = triadic_kuramoto_step(theta, omega=omega, cfg=cfg_triad, dt=0.1)
        assert not np.allclose(new_pair, new_triad)

    def test_invalid_dt_rejected(self) -> None:
        n = 5
        theta = np.zeros(n, dtype=np.float64)
        with pytest.raises(ValueError, match="dt"):
            triadic_kuramoto_step(
                theta,
                omega=np.zeros(n, dtype=np.float64),
                cfg=HigherOrderConfig(k2=1.0, k3=0.0),
                dt=0.0,
            )


class TestExplosiveSync:
    def _build_sf_adjacency(self, n: int = 30, seed: int = 11) -> np.ndarray:
        """Synthetic Barabási-Albert-like adjacency: hub-rich graph."""
        rng = np.random.default_rng(seed=seed)
        # Stub: random sparse symmetric adjacency.
        adj = (rng.random((n, n)) < 0.20).astype(np.float64)
        adj = ((adj + adj.T) > 0).astype(np.float64)
        np.fill_diagonal(adj, 0.0)
        return adj

    def test_continuous_transition_low_hysteresis(self) -> None:
        """Standard Kuramoto on a regular graph is continuous;
        hysteresis width should be small."""
        rng = np.random.default_rng(seed=33)
        n = 20
        omega = rng.normal(0.0, 0.5, n)
        # Regular ring graph with nearest-neighbour coupling.
        adj = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            adj[i, (i + 1) % n] = 1.0
            adj[i, (i - 1) % n] = 1.0
        coupling_grid = np.linspace(0.1, 4.0, 8)
        report = explosive_sync_sweep(
            coupling_grid=coupling_grid,
            omega=omega,
            adjacency=adj,
            n_steps=400,
            burn_in=100,
            dt=0.05,
            seed=33,
            hysteresis_threshold=0.10,
        )
        assert isinstance(report, ExplosiveSyncReport)
        # Continuous transition: hysteresis should be modest.
        assert report.hysteresis_width < 0.30  # generous slack for small N

    def test_invalid_grid_rejected(self) -> None:
        # Non-monotonic coupling grid → rejected.
        omega = np.zeros(5, dtype=np.float64)
        adj = np.zeros((5, 5), dtype=np.float64)
        with pytest.raises(ValueError, match="strictly increasing"):
            explosive_sync_sweep(
                coupling_grid=np.array([1.0, 0.5, 2.0]),
                omega=omega,
                adjacency=adj,
                n_steps=100,
                burn_in=10,
                dt=0.1,
                hysteresis_threshold=0.10,
            )

    def test_diagonal_nonzero_rejected(self) -> None:
        omega = np.zeros(5, dtype=np.float64)
        adj = np.eye(5, dtype=np.float64)
        with pytest.raises(ValueError, match="diagonal"):
            explosive_sync_sweep(
                coupling_grid=np.array([0.1, 0.2, 0.3]),
                omega=omega,
                adjacency=adj,
                n_steps=100,
                burn_in=10,
                dt=0.1,
                hysteresis_threshold=0.10,
            )

    def test_burn_in_ge_n_steps_rejected(self) -> None:
        omega = np.zeros(3, dtype=np.float64)
        adj = np.zeros((3, 3), dtype=np.float64)
        with pytest.raises(ValueError, match="burn_in"):
            explosive_sync_sweep(
                coupling_grid=np.array([0.1, 0.2, 0.3]),
                omega=omega,
                adjacency=adj,
                n_steps=50,
                burn_in=50,
                dt=0.1,
                hysteresis_threshold=0.10,
            )
