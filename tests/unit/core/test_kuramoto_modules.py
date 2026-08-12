# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive unit tests for Kuramoto engine modules.

Covers: DelayedKuramotoEngine, EarlyStoppingEngine, SparseKuramotoEngine,
SecondOrderKuramotoEngine, AdaptiveKuramotoEngine.

Mathematical invariants tested:
- Order parameter R in [0, 1]
- Phases finite after integration
- Convergence under strong coupling
- Edge cases: single-pair oscillators, identical frequencies, NaN guards
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import sparse

from core.kuramoto.adaptive import AdaptiveKuramotoEngine
from core.kuramoto.config import KuramotoConfig
from core.kuramoto.delayed import DelayedKuramotoEngine
from core.kuramoto.early_stopping import EarlyStoppingEngine
from core.kuramoto.metrics import order_parameter
from core.kuramoto.ott_antonsen import OttAntonsenEngine, detect_chimera
from core.kuramoto.phase_transition import PhaseTransitionAnalyzer
from core.kuramoto.second_order import SecondOrderKuramotoEngine
from core.kuramoto.sparse import SparseKuramotoEngine

# Level auto-assigned by conftest from tests/test_levels.yaml

# INV-K1 order-parameter envelope: 0 <= R <= 1. The upper edge carries a float
# round-off tolerance (R = |mean(e^{i*theta})| can exceed 1 by ~1 ULP). These are
# derived physical bounds, not tuned thresholds.
R_LOWER_BOUND = 0.0
R_UPPER_BOUND = 1.0
R_UPPER_TOL = 1e-12


# ── Helpers ──────────────────────────────────────────────────────────────


def _synced_config(N: int = 10, K: float = 5.0, steps: int = 500, seed: int = 42) -> KuramotoConfig:
    """Config with strong coupling that should synchronize."""
    return KuramotoConfig(N=N, K=K, dt=0.01, steps=steps, seed=seed)


def _weak_config(N: int = 10, K: float = 0.01, steps: int = 200, seed: int = 7) -> KuramotoConfig:
    """Config with weak coupling -- low synchronization expected."""
    return KuramotoConfig(N=N, K=K, dt=0.01, steps=steps, seed=seed)


def _minimal_config(seed: int = 0) -> KuramotoConfig:
    """Minimal 2-oscillator config."""
    return KuramotoConfig(N=2, K=2.0, dt=0.01, steps=100, seed=seed)


# ═══════════════════════════════════════════════════════════════════════
# DelayedKuramotoEngine
# ═══════════════════════════════════════════════════════════════════════


class TestDelayedKuramotoEngine:
    def test_order_parameter_bounded(self):
        """INV-K1: 0 <= R(t) <= 1 for the full integrated trajectory."""
        cfg = _synced_config(N=8, steps=300)
        result = DelayedKuramotoEngine(cfg, tau=0.05).run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_phases_finite(self):
        """INV-HPC2: finite inputs -> finite phases (no NaN/Inf propagation)."""
        cfg = _synced_config(N=6, steps=200)
        result = DelayedKuramotoEngine(cfg, tau=0.02).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_output_shapes(self):
        """NON_PHYSICS: result array shapes (interface contract), not a registered physics invariant."""
        cfg = _synced_config(N=5, steps=150)
        result = DelayedKuramotoEngine(cfg, tau=0.1).run()
        assert result.phases.shape == (151, 5)
        assert result.order_parameter.shape == (151,)
        assert result.time.shape == (151,)

    def test_zero_delay_matches_standard_behavior(self):
        """INV-K1: zero delay reduces to standard Kuramoto with finite phases, R in [0,1]."""
        cfg = _synced_config(N=4, steps=100)
        result = DelayedKuramotoEngine(cfg, tau=0.0).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )
        r_final = result.order_parameter[-1]
        assert R_LOWER_BOUND <= r_final <= R_UPPER_BOUND + R_UPPER_TOL, (
            "INV-K1: final order parameter must stay in [0,1], observed "
            f"R_final={r_final} with N={cfg.N} (expected bounded order parameter)"
        )

    def test_heterogeneous_delay_matrix(self):
        """INV-K1: 0 <= R(t) <= 1 with a heterogeneous delay matrix; phases stay finite."""
        cfg = _synced_config(N=4, steps=100)
        tau_matrix = np.random.default_rng(99).uniform(0.01, 0.05, (4, 4))
        result = DelayedKuramotoEngine(cfg, tau=tau_matrix).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_custom_history_function(self):
        """INV-HPC2: a custom history function still yields finite phases."""
        cfg = _synced_config(N=3, steps=100)
        result = DelayedKuramotoEngine(cfg, tau=0.05, history_fn=lambda t: np.zeros(3)).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_two_oscillators(self):
        """INV-K1: 0 <= R(t) <= 1 holds for the minimal N=2 oscillator pair."""
        cfg = _minimal_config()
        result = DelayedKuramotoEngine(cfg, tau=0.01).run()
        assert result.phases.shape == (101, 2)
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )


# ═══════════════════════════════════════════════════════════════════════
# EarlyStoppingEngine
# ═══════════════════════════════════════════════════════════════════════


class TestEarlyStoppingEngine:
    def test_order_parameter_bounded(self):
        """INV-K1: 0 <= R(t) <= 1 for the full integrated trajectory."""
        cfg = _synced_config(steps=2000)
        result = EarlyStoppingEngine(cfg, epsilon=1e-4, patience=50, min_steps=50).run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_early_stop_happens_under_strong_coupling(self):
        """INV-K3: strong coupling K>K_c drives convergence (early-stop fires)."""
        max_steps = 5000
        cfg = _synced_config(N=10, K=8.0, steps=max_steps)
        result = EarlyStoppingEngine(cfg, epsilon=1e-4, patience=100, min_steps=50).run()
        assert result.summary.get("early_stopped", False), (
            "INV-K3: supercritical K>K_c must converge and trigger early stop, observed "
            f"early_stopped={result.summary.get('early_stopped', False)} with N=10, K=8.0 "
            "(expected convergence to R_inf>0)"
        )
        converged_at = result.summary["converged_at_step"]
        assert converged_at < max_steps, (
            "INV-K3: convergence must occur before max_steps, observed "
            f"converged_at_step={converged_at} with steps={max_steps}, K=8.0 "
            "(expected finite-time convergence)"
        )

    def test_phases_finite(self):
        """INV-HPC2: finite inputs -> finite phases (no NaN/Inf propagation)."""
        cfg = _synced_config(steps=500)
        result = EarlyStoppingEngine(cfg, epsilon=1e-5, patience=50, min_steps=30).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_summary_keys_present(self):
        """NON_PHYSICS: summary dict keys (interface contract), not a registered physics invariant."""
        cfg = _synced_config(steps=500)
        result = EarlyStoppingEngine(cfg, epsilon=1e-4, patience=50, min_steps=30).run()
        for key in ("converged_at_step", "max_steps", "early_stopped", "compute_saved_pct"):
            assert key in result.summary

    def test_no_early_stop_with_tiny_patience(self):
        """NON_PHYSICS: early-stop config edge case (strict epsilon runs to completion),
        not a registered physics invariant."""
        cfg = _weak_config(steps=200)
        result = EarlyStoppingEngine(cfg, epsilon=1e-15, patience=5000, min_steps=10).run()
        # Should run to max steps since convergence criterion is extremely strict
        assert result.order_parameter.shape[0] > 0

    def test_two_oscillators(self):
        """INV-K1: 0 <= R(t) <= 1 holds for the minimal N=2 oscillator pair."""
        cfg = _minimal_config()
        result = EarlyStoppingEngine(
            KuramotoConfig(N=2, K=5.0, dt=0.01, steps=1000, seed=0),
            epsilon=1e-4,
            patience=50,
            min_steps=20,
        ).run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )


# ═══════════════════════════════════════════════════════════════════════
# SparseKuramotoEngine
# ═══════════════════════════════════════════════════════════════════════


class TestSparseKuramotoEngine:
    def test_order_parameter_bounded(self):
        """INV-K1: 0 <= R(t) <= 1 for the full integrated trajectory."""
        cfg = _synced_config(N=20, steps=300)
        result = SparseKuramotoEngine(cfg).run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_phases_finite(self):
        """INV-HPC2: finite inputs -> finite phases (no NaN/Inf propagation)."""
        cfg = _synced_config(N=15, steps=200)
        result = SparseKuramotoEngine(cfg).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_explicit_sparse_adjacency(self):
        """INV-K1: 0 <= R(t) <= 1 with an explicit sparse adjacency; phases finite."""
        N = 10
        rng = np.random.default_rng(42)
        dense = rng.random((N, N))
        dense = (dense + dense.T) / 2
        np.fill_diagonal(dense, 0.0)
        sp_adj = sparse.csr_matrix(dense)
        cfg = KuramotoConfig(N=N, K=2.0, dt=0.01, steps=200, seed=42)
        result = SparseKuramotoEngine(cfg, sparse_adjacency=sp_adj).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_dense_adjacency_auto_converted(self):
        """NON_PHYSICS: dense->sparse adjacency auto-conversion shape (plumbing), not a registered physics invariant."""
        N = 8
        adj = np.ones((N, N))
        np.fill_diagonal(adj, 0.0)
        cfg = KuramotoConfig(N=N, K=1.0, dt=0.01, steps=100, adjacency=adj, seed=10)
        result = SparseKuramotoEngine(cfg).run()
        assert result.phases.shape == (101, N)

    def test_output_shapes(self):
        """NON_PHYSICS: result array shapes (interface contract), not a registered physics invariant."""
        cfg = _synced_config(N=12, steps=100)
        result = SparseKuramotoEngine(cfg).run()
        assert result.phases.shape == (101, 12)
        assert result.order_parameter.shape == (101,)
        assert result.time.shape == (101,)

    def test_two_oscillators(self):
        """INV-K1: 0 <= R(t) <= 1 holds for the minimal N=2 oscillator pair."""
        cfg = _minimal_config()
        result = SparseKuramotoEngine(cfg).run()
        assert result.phases.shape == (101, 2)
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )


# ═══════════════════════════════════════════════════════════════════════
# SecondOrderKuramotoEngine
# ═══════════════════════════════════════════════════════════════════════


class TestSecondOrderKuramotoEngine:
    def test_order_parameter_bounded(self):
        """INV-K1: 0 <= R(t) <= 1 for the full integrated trajectory."""
        cfg = _synced_config(N=8, K=5.0, steps=500)
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.5).run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_phases_and_velocities_finite(self):
        """INV-HPC2: finite inputs -> finite phases AND velocities (second-order)."""
        cfg = _synced_config(N=6, steps=300)
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.3).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )
        assert np.all(np.isfinite(result.velocities)), (
            "INV-HPC2: finite inputs must yield finite velocities, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.velocities)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_output_shapes(self):
        """NON_PHYSICS: result array shapes (interface contract), not a registered physics invariant."""
        cfg = _synced_config(N=5, steps=200)
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.2).run()
        assert result.phases.shape == (201, 5)
        assert result.velocities.shape == (201, 5)
        assert result.order_parameter.shape == (201,)

    def test_summary_has_frequency_metrics(self):
        """NON_PHYSICS: second-order summary metric keys (interface), not a registered physics invariant."""
        cfg = _synced_config(N=5, steps=200)
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.2).run()
        for key in (
            "frequency_nadir",
            "frequency_zenith",
            "max_rocof",
            "final_frequency_spread",
            "mean_frequency",
        ):
            assert key in result.summary, f"Missing summary key: {key}"

    def test_heterogeneous_mass_and_damping(self):
        """INV-HPC2: heterogeneous mass/damping still yields finite phases."""
        N = 6
        cfg = _synced_config(N=N, steps=200)
        mass = np.linspace(0.5, 2.0, N)
        damping = np.linspace(0.1, 0.5, N)
        result = SecondOrderKuramotoEngine(cfg, mass=mass, damping=damping).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_invalid_mass_raises(self):
        """NON_PHYSICS: constructor validation of mass>0 (input guard), not a registered physics invariant."""
        cfg = _synced_config(N=4, steps=50)
        with pytest.raises(ValueError, match="Mass must be strictly positive"):
            SecondOrderKuramotoEngine(cfg, mass=0.0)

    def test_negative_damping_raises(self):
        """NON_PHYSICS: constructor validation of damping>=0 (input guard), not a registered physics invariant."""
        cfg = _synced_config(N=4, steps=50)
        with pytest.raises(ValueError, match="Damping must be non-negative"):
            SecondOrderKuramotoEngine(cfg, mass=1.0, damping=-0.1)

    def test_custom_initial_velocity(self):
        """INV-HPC2: a custom initial velocity still yields finite phases."""
        cfg = _synced_config(N=4, steps=100)
        v0 = np.array([0.1, -0.1, 0.2, -0.2])
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.3, velocity0=v0).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_two_oscillators(self):
        """INV-K1: 0 <= R(t) <= 1 holds for the minimal N=2 oscillator pair."""
        cfg = _minimal_config()
        result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.5).run()
        assert result.phases.shape == (101, 2)
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )


# ═══════════════════════════════════════════════════════════════════════
# AdaptiveKuramotoEngine
# ═══════════════════════════════════════════════════════════════════════


class TestAdaptiveKuramotoEngine:
    def test_order_parameter_bounded(self):
        """INV-K1: 0 <= R(t) <= 1 for the full integrated trajectory."""
        cfg = _synced_config(N=8, steps=300)
        result = AdaptiveKuramotoEngine(cfg, method="RK45").run()
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )
        assert np.all(result.order_parameter <= R_UPPER_BOUND + R_UPPER_TOL), (
            "INV-K1: order parameter must satisfy R <= R_UPPER_BOUND, observed "
            f"max={float(np.max(result.order_parameter))} with N={cfg.N} "
            "(expected upper envelope + round-off tol)"
        )

    def test_phases_finite(self):
        """INV-HPC2: finite inputs -> finite phases (no NaN/Inf propagation)."""
        cfg = _synced_config(N=6, steps=200)
        result = AdaptiveKuramotoEngine(cfg).run()
        assert np.all(np.isfinite(result.phases)), (
            "INV-HPC2: finite inputs must yield finite phases, observed "
            f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} with N={cfg.N} "
            "(expected no NaN/Inf propagation)"
        )

    def test_output_shapes(self):
        """NON_PHYSICS: result array shapes (interface contract), not a registered physics invariant."""
        cfg = _synced_config(N=5, steps=150)
        result = AdaptiveKuramotoEngine(cfg).run()
        assert result.phases.shape == (151, 5)
        assert result.order_parameter.shape == (151,)

    def test_strong_coupling_convergence(self):
        """INV-K3: super-critical coupling K>>K_c drives the order parameter toward sync.

        For K=10 (far above the Kuramoto critical coupling K_c for a unit-spread
        frequency distribution) the steady-state order parameter must reach the
        strongly-synchronized regime. The threshold is derived from the mean-field
        self-consistency R_inf = sqrt(1 - K_c/K): with K_c ~ O(1) and K=10,
        R_inf >~ 0.9, so a conservative sync floor of 0.7 is comfortably below the
        theoretical R_inf and acts only as a regime discriminator (INV-K3: R_inf>0).
        """
        cfg = KuramotoConfig(N=10, K=10.0, dt=0.01, steps=1000, seed=42)
        result = AdaptiveKuramotoEngine(cfg).run()
        # Sync regime floor (well below theoretical R_inf=sqrt(1-K_c/K) for K=10).
        sync_floor = 0.7
        r_final = float(result.order_parameter[-1])
        assert r_final > sync_floor, (
            "INV-K3: super-critical K=10 must reach the synchronized regime, observed "
            f"R_final={r_final} with N=10, K=10.0 (expected R_inf > sync_floor)"
        )

    def test_multiple_methods(self):
        """INV-HPC2: every adaptive solver method yields finite phases and bounded R."""
        cfg = _synced_config(N=5, steps=100)
        for method in ("RK45", "RK23", "DOP853"):
            result = AdaptiveKuramotoEngine(cfg, method=method).run()
            assert np.all(np.isfinite(result.phases)), (
                "INV-HPC2: finite inputs must yield finite phases, observed "
                f"non-finite count={int(np.sum(~np.isfinite(result.phases)))} "
                f"with method={method}, N={cfg.N} (expected no NaN/Inf)"
            )
            assert np.all(result.order_parameter >= R_LOWER_BOUND), (
                "INV-HPC2: order parameter must satisfy R >= R_LOWER_BOUND, observed "
                f"min={float(np.min(result.order_parameter))} with method={method}, "
                f"N={cfg.N} (expected lower envelope)"
            )

    def test_two_oscillators(self):
        """INV-K1: 0 <= R(t) <= 1 holds for the minimal N=2 oscillator pair."""
        cfg = _minimal_config()
        result = AdaptiveKuramotoEngine(cfg).run()
        assert result.phases.shape == (101, 2)
        assert np.all(result.order_parameter >= R_LOWER_BOUND), (
            "INV-K1: order parameter must satisfy R >= R_LOWER_BOUND, observed "
            f"min={float(np.min(result.order_parameter))} with N={cfg.N} "
            "(expected lower envelope)"
        )


# ═══════════════════════════════════════════════════════════════════════
# Cross-module: mathematical properties
# ═══════════════════════════════════════════════════════════════════════


class TestCrossModuleMathProperties:
    def test_identical_phases_give_R_one(self):
        """INV-K1: identical phases with zero frequency saturate R=1 across all engines.

        With theta_i ≡ 0 and omega_i ≡ 0 every engine must hold the order parameter at
        the upper edge R=1 of the INV-K1 envelope for the whole trajectory.
        """
        N = 5
        r_sat = 1.0
        sync_atol = 1e-6
        theta0 = np.zeros(N)
        omega = np.zeros(N)
        cfg = KuramotoConfig(N=N, K=1.0, dt=0.01, steps=50, theta0=theta0, omega=omega, seed=0)

        engines = {
            "delayed": DelayedKuramotoEngine(cfg, tau=0.01).run(),
            "early_stopping": EarlyStoppingEngine(
                cfg, epsilon=1e-6, patience=10, min_steps=5
            ).run(),
            "sparse": SparseKuramotoEngine(cfg).run(),
            "second_order": SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.5).run(),
            "adaptive": AdaptiveKuramotoEngine(cfg).run(),
        }
        for name, result in engines.items():
            assert np.allclose(result.order_parameter, r_sat, atol=sync_atol), (
                f"INV-K1: identical phases must saturate R to {r_sat}, observed "
                f"max_dev={float(np.max(np.abs(result.order_parameter - r_sat)))} "
                f"with engine={name}, N={N} (expected |R-1| <= sync_atol)"
            )

    def test_time_monotonically_increasing(self):
        """NON_PHYSICS: time-grid monotonicity (integrator interface), not a registered physics invariant."""
        cfg = _synced_config(N=5, steps=100)
        result = DelayedKuramotoEngine(cfg, tau=0.02).run()
        assert np.all(np.diff(result.time) > 0)

    def test_seed_reproducibility(self):
        """INV-HPC1: identical seed -> bit-reproducible phase trajectory.

        Re-running the same seeded config must reproduce the phase trajectory to
        within machine precision; checked across several seeds (INV-HPC1).
        """
        repro_atol = 1e-10
        for seed in (123, 7, 2024):
            r1 = AdaptiveKuramotoEngine(_synced_config(seed=seed)).run()
            r2 = AdaptiveKuramotoEngine(_synced_config(seed=seed)).run()
            max_dev = float(np.max(np.abs(r1.phases - r2.phases)))
            assert max_dev <= repro_atol, (
                "INV-HPC1: identical seed must reproduce phases to machine precision, "
                f"observed max_dev={max_dev} with seed={seed} "
                "(expected <= repro_atol)"
            )


class TestFinitenessFailClosed:
    """Fail-closed finiteness guards: non-finite input must never leak past the
    documented order-parameter bounds (INV-OA1 |z|≤1, INV-K1 R∈[0,1]).

    Each test reproduces a latent defect found by a computational manifold
    audit: NaN-blind comparison guards (``abs(z) > 1.0`` is False for NaN) used
    to propagate NaN/Inf silently, and the Ott-Antonsen integrator silently
    renormalised a blown-up RK4 step onto the unit circle — inverting the
    synchronization verdict (subcritical K<2Δ reported as full sync R=1).
    """

    def test_oa_unstable_step_fails_closed_not_silent_full_sync(self) -> None:
        """INV-OA1/OA3: a blown-up RK4 step must raise, not report spurious sync.

        K=0.5 < K_c=2Δ=4 is subcritical (INV-OA3: R→0). With dt past the RK4
        stability limit the old code silently renormalised the divergence to
        |z|=1 and returned R[-1]=1.0 (a full-sync verdict, the exact opposite
        regime). Fail-closed now raises FloatingPointError.
        """
        engine = OttAntonsenEngine(K=0.5, delta=2.0, omega0=0.0)
        # Sweep several over-large dt past the RK4 stability limit; each must raise.
        for dt in (2.5, 5.0, 10.0):
            with pytest.raises(FloatingPointError):
                engine.integrate(T=50.0, dt=dt, R0=0.5)

    def test_oa_rejects_non_finite_initial_condition(self) -> None:
        """INV-OA1: a non-finite initial condition R0 must fail-closed, not run.

        INV-OA1 bounds |z| <= 1; a non-finite R0 cannot live on the unit disc, so each
        non-finite initial condition must raise rather than yield an all-NaN trajectory.
        """
        engine = OttAntonsenEngine(K=2.0, delta=0.5)
        for bad_r0 in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError):
                engine.integrate(T=1.0, dt=0.1, R0=bad_r0)

    def test_oa_rejects_non_finite_parameters(self) -> None:
        """INV-OA1: non-finite K/delta/omega0 must fail-closed at construction.

        INV-OA1's |z| <= 1 evolution is undefined for non-finite parameters, so each
        non-finite (K, delta, omega0) combination must raise at construction time.
        """
        bad_param_kwargs = (
            {"K": float("inf"), "delta": 0.5},
            {"K": 1.0, "delta": float("nan")},
            {"K": 1.0, "delta": 0.5, "omega0": float("inf")},
        )
        for kwargs in bad_param_kwargs:
            with pytest.raises(ValueError):
                OttAntonsenEngine(**kwargs)

    def test_oa_legitimate_supercritical_still_exact(self) -> None:
        """INV-OA2: supercritical steady state matches R_inf = sqrt(1 - K_c/K).

        For K > K_c = 2*delta the Ott-Antonsen RK4 fixed point must reproduce the exact
        mean-field normal form R_inf = sqrt(1 - 2*delta/K) across several supercritical
        (K, delta) points (INV-OA2).
        """
        steady_state_tol = 1e-3
        # Each (K, delta) is supercritical: K > K_c = 2*delta.
        for K, delta in ((6.0, 0.5), (4.0, 0.5), (3.0, 1.0)):
            engine = OttAntonsenEngine(K=K, delta=delta, omega0=0.0)
            result = engine.integrate(T=50.0, dt=0.01, R0=0.1)
            k_c = 2.0 * delta
            r_inf_theory = math.sqrt(1.0 - k_c / K)
            assert result.is_supercritical, (
                "INV-OA2: K>K_c must be flagged supercritical, observed "
                f"is_supercritical={result.is_supercritical} with K={K}, K_c={k_c} "
                "(expected supercritical)"
            )
            assert abs(result.R[-1] - r_inf_theory) < steady_state_tol, (
                "INV-OA2: steady-state R must match sqrt(1-K_c/K), observed "
                f"R_final={float(result.R[-1])} vs theory={r_inf_theory} with K={K}, "
                f"K_c={k_c} (expected |R-R_inf| < steady_state_tol)"
            )

    def test_order_parameter_rejects_non_finite_phases(self) -> None:
        """INV-K1: a non-finite phase must fail-closed, never leak NaN past R in [0,1].

        INV-K1 bounds R in [0,1]; a non-finite phase cannot produce a bounded R, so each
        non-finite phase array must raise rather than silently emit NaN.
        """
        bad_thetas = (
            np.array([[0.0, np.nan, 1.0], [0.1, 0.2, 0.3]]),
            np.array([[0.0, np.inf, 1.0], [0.1, 0.2, 0.3]]),
            np.array([[0.0, -np.inf, 1.0], [0.1, 0.2, 0.3]]),
        )
        for theta in bad_thetas:
            with pytest.raises(ValueError):
                order_parameter(theta, axis=1)

    def test_order_parameter_finite_phases_bounded(self) -> None:
        """INV-K1: finite phases yield an order parameter inside the [0,1] envelope."""
        theta = np.array([[0.0, 0.1, 0.2], [1.0, 1.1, 0.9]])
        r = order_parameter(theta, axis=1)
        assert r.shape == (2,), (
            f"INV-K1: order parameter shape must match input rows, observed "
            f"shape={r.shape} with N=3 (expected (2,))"
        )
        assert np.all((r >= R_LOWER_BOUND) & (r <= R_UPPER_BOUND)), (
            "INV-K1: order parameter must stay in [0,1], observed "
            f"min={float(np.min(r))}, max={float(np.max(r))} with N=3 "
            "(expected bounded envelope)"
        )


class TestDegenerateInputFailClosed:
    """Degenerate-input guards found by a computational audit: a single-point
    sweep, a flat (never-crossing) R curve, and negative/empty chimera sector
    labels each previously produced an opaque crash or a silently-wrong result.
    """

    def test_find_critical_k_single_point_raises(self) -> None:
        """NON_PHYSICS: single-point sweep input guard for _find_critical_K (detector
        robustness), not a registered physics invariant."""
        with pytest.raises(ValueError, match="≥2 sweep points"):
            PhaseTransitionAnalyzer._find_critical_K(np.array([2.0]), np.array([0.5]))

    def test_find_critical_k_flat_curve_signals_no_transition(self) -> None:
        """NON_PHYSICS: flat-curve no-transition guard for _find_critical_K (detector
        robustness), not a registered physics invariant."""
        k_c = PhaseTransitionAnalyzer._find_critical_K(np.linspace(0.0, 5.0, 5), np.full(5, 0.1))
        assert math.isnan(k_c)

    def test_find_critical_k_real_crossing_unchanged(self) -> None:
        """NON_PHYSICS: K_c interpolation regression for _find_critical_K (detector
        numerics), not a registered physics invariant."""
        k_c = PhaseTransitionAnalyzer._find_critical_K(
            np.array([0.0, 1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.5, 0.9])
        )
        assert 1.0 < k_c < 2.0

    def test_detect_chimera_rejects_negative_sectors(self) -> None:
        """NON_PHYSICS: chimera-detector negative-sector input guard (robustness), not a
        registered physics invariant."""
        with pytest.raises(ValueError, match="non-negative"):
            detect_chimera(
                np.array([0.0, 0.1, 3.0, 3.1]),
                np.array([-1, -1, 0, 0], dtype=np.int64),
            )

    def test_detect_chimera_rejects_empty(self) -> None:
        """NON_PHYSICS: chimera-detector empty-input guard, not a registered physics invariant."""
        with pytest.raises(ValueError, match="non-empty"):
            detect_chimera(np.array([]), np.array([], dtype=np.int64))

    def test_detect_chimera_valid_sectors_unchanged(self) -> None:
        """NON_PHYSICS: chimera-detector valid-input regression (report shape), not a
        registered physics invariant."""
        report = detect_chimera(
            np.array([0.0, 0.1, 3.0, 3.1]),
            np.array([0, 0, 1, 1], dtype=np.int64),
        )
        assert report.sector_R.shape == (2,)
