# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the last two methodology protocols shipped after the
orchestrator: M1.5 causal validation and M3.3 out-of-sample evaluation.

These tests use the synthetic ground-truth generator so the assertions
are anchored to known causal parents (M1.5) and known dynamics (M3.3).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.causal_validation import (
    CausalValidationConfig,
    CausalValidationReport,
    compare_to_coupling,
    lag_granger_causality,
)
from core.kuramoto.contracts import CouplingMatrix, PhaseMatrix
from core.kuramoto.coupling_estimator import CouplingEstimationConfig
from core.kuramoto.delay_estimator import DelayEstimationConfig
from core.kuramoto.network_engine import (
    NetworkEngineConfig,
    NetworkKuramotoEngine,
)
from core.kuramoto.oos_validation import (
    OOSConfig,
    circular_mae,
    diebold_mariano_test,
    evaluate_oos,
    simulate_forward,
    spa_test,
    temporal_split,
    walk_forward_evaluate,
)
from core.kuramoto.synthetic import SyntheticConfig, generate_sakaguchi_kuramoto

# ---------------------------------------------------------------------------
# M1.5 — causal validation
# ---------------------------------------------------------------------------


class TestLagGrangerCausality:
    def test_unidirectional_driver_detected(self) -> None:
        """A noisy driver → driven pair must be flagged as causal."""
        rng = np.random.default_rng(0)
        T, N = 2000, 3
        # Oscillator 0 drives 1 with lag 2; 2 is independent
        theta = np.zeros((T, N))
        theta[0] = rng.uniform(0, 2 * np.pi, size=N)
        for t in range(1, T):
            theta[t, 0] = theta[t - 1, 0] + 0.05 * 0.5
            # 1 follows 0 with lag 2
            drive = np.sin(theta[max(0, t - 2), 0] - theta[t - 1, 1])
            theta[t, 1] = theta[t - 1, 1] + 0.05 * (0.4 + 0.8 * drive)
            theta[t, 2] = theta[t - 1, 2] + 0.05 * 1.1
            theta[t] += 0.02 * rng.standard_normal(N) * np.sqrt(0.05)
        theta = np.mod(theta, 2 * np.pi)
        pm = PhaseMatrix(
            theta=theta,
            timestamps=np.arange(T, dtype=np.float64) * 0.05,
            asset_ids=("driver", "driven", "indep"),
            extraction_method="hilbert",
            frequency_band=(0.01, 1.0),
        )
        report = lag_granger_causality(pm, config=CausalValidationConfig(max_lag=4, alpha=0.01))
        assert isinstance(report, CausalValidationReport)
        # driven receives from driver
        assert bool(report.causal_graph[1, 0])
        # independent does NOT receive from driver
        assert not bool(report.causal_graph[2, 0])

    def test_diagonal_is_ignored(self) -> None:
        rng = np.random.default_rng(1)
        theta = np.mod(
            np.cumsum(0.05 + 0.02 * rng.standard_normal((500, 3)), axis=0),
            2 * np.pi,
        )
        pm = PhaseMatrix(
            theta=theta,
            timestamps=np.arange(500, dtype=np.float64),
            asset_ids=("a", "b", "c"),
            extraction_method="hilbert",
            frequency_band=(0.01, 1.0),
        )
        report = lag_granger_causality(pm)
        assert np.all(~np.asarray(np.diag(report.causal_graph)))
        assert np.all(np.isnan(np.diag(report.p_values)))

    def test_report_is_deeply_immutable(self) -> None:
        pm = generate_sakaguchi_kuramoto(
            SyntheticConfig(N=3, T=400, burn_in=40, seed=2)
        ).generated_phases
        report = lag_granger_causality(pm, config=CausalValidationConfig(max_lag=2))
        assert report.causal_graph.flags.writeable is False
        assert report.p_values.flags.writeable is False
        with pytest.raises(ValueError):
            report.p_values[0, 1] = 0.0

    def test_compare_to_coupling_metrics(self) -> None:
        N = 4
        K_true = np.zeros((N, N))
        K_true[0, 1] = 1.0
        K_true[2, 3] = -0.5
        coupling = CouplingMatrix(
            K=K_true,
            asset_ids=("a", "b", "c", "d"),
            sparsity=1 - 2 / 12,
            method="scad",
        )
        causal = np.zeros((N, N), dtype=bool)
        causal[0, 1] = True  # TP
        causal[1, 0] = True  # FP (in causal, not in coupling)
        causal[2, 3] = True  # TP
        report = CausalValidationReport(
            causal_graph=causal,
            p_values=np.zeros((N, N)),
            best_lag=np.zeros((N, N), dtype=np.int64),
            method="granger",
        )
        metrics = compare_to_coupling(report, coupling)
        # Intersection = 2 (both true edges detected); union = 3
        assert metrics["jaccard"] == pytest.approx(2 / 3)
        assert metrics["precision"] == pytest.approx(2 / 2)  # coupling ∩ causal / coupling
        assert metrics["recall"] == pytest.approx(2 / 3)  # coupling ∩ causal / causal

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError):
            CausalValidationConfig(max_lag=0)
        with pytest.raises(ValueError):
            CausalValidationConfig(alpha=0.0)
        with pytest.raises(ValueError):
            CausalValidationConfig(backend="xgboost")


# ---------------------------------------------------------------------------
# M3.3 — OOS validation primitives
# ---------------------------------------------------------------------------


class TestCircularMAE:
    def test_identical_inputs_give_zero(self) -> None:
        theta = np.linspace(0, 2 * np.pi, 100).reshape(-1, 1)
        assert circular_mae(theta, theta) == pytest.approx(0.0, abs=1e-12)

    def test_pi_offset_gives_pi(self) -> None:
        theta_a = np.zeros((50, 2))
        theta_b = np.full((50, 2), np.pi)
        assert circular_mae(theta_a, theta_b) == pytest.approx(np.pi, abs=1e-9)


class TestDieboldMariano:
    def test_model_strictly_better_yields_small_p(self) -> None:
        rng = np.random.default_rng(0)
        n = 500
        baseline_err = rng.standard_normal(n) * 0.5
        model_err = rng.standard_normal(n) * 0.1  # 5× smaller variance
        dm, p = diebold_mariano_test(model_err, baseline_err)
        assert dm > 0
        assert p < 0.01

    def test_identical_models_never_reject_null(self) -> None:
        """Identical error sequences → zero loss differential → no rejection.

        The variance of the differential is exactly zero, which the
        implementation treats as the degenerate-null case and
        returns ``p = 1`` (cannot reject equal accuracy). Any value
        above 0.5 is acceptable — the critical property is that we
        never spuriously claim superiority.
        """
        rng = np.random.default_rng(1)
        err = rng.standard_normal(400)
        _, p = diebold_mariano_test(err, err.copy())
        assert p >= 0.5

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            diebold_mariano_test(np.zeros(10), np.zeros(20))


class TestSPATest:
    def test_dominant_model_rejects_null(self) -> None:
        rng = np.random.default_rng(0)
        n = 400
        model_err = 0.05 * rng.standard_normal(n)
        baselines = {
            "noisy1": rng.standard_normal(n),
            "noisy2": rng.standard_normal(n) * 1.2,
            "noisy3": rng.standard_normal(n) * 0.8,
        }
        p = spa_test(model_err, baselines, n_bootstrap=200, block_length=10, random_state=0)
        assert p < 0.05

    def test_weak_model_fails_to_reject(self) -> None:
        rng = np.random.default_rng(2)
        n = 300
        # All models are the same scale — no one is the SPA winner
        model_err = rng.standard_normal(n)
        baselines = {
            "a": rng.standard_normal(n),
            "b": rng.standard_normal(n),
        }
        p = spa_test(model_err, baselines, n_bootstrap=200, block_length=10, random_state=0)
        assert p >= 0.05


# ---------------------------------------------------------------------------
# M3.3 — temporal split & forward simulation
# ---------------------------------------------------------------------------


class TestTemporalSplit:
    def test_slices_are_contiguous_and_disjoint(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=3, T=500, burn_in=50, seed=1))
        train, val, test = temporal_split(gt.generated_phases, train_frac=0.6, val_frac=0.2)
        T = gt.generated_phases.theta.shape[0]
        assert train.start == 0
        assert train.stop == val.start
        assert val.stop == test.start
        assert test.stop == T


class TestSimulateForward:
    def test_simulated_trajectory_has_expected_shape(self) -> None:
        gt = generate_sakaguchi_kuramoto(
            SyntheticConfig(
                N=4,
                T=600,
                dt=0.05,
                burn_in=50,
                seed=3,
                K_sparsity=0.5,
                K_scale=(0.4, 0.9),
                omega_center=0.7,
                omega_spread=0.3,
                tau_max=2,
                alpha_structure="zero",
                alpha_max=0.0,
                sigma_noise=0.02,
            )
        )
        engine = NetworkKuramotoEngine(
            NetworkEngineConfig(
                coupling=CouplingEstimationConfig(
                    penalty="mcp",
                    lambda_reg=0.1,
                    dt=0.05,
                    max_iter=500,
                    tol=1e-5,
                ),
                delay=DelayEstimationConfig(max_lag=2, dt=0.05),
            )
        )
        report = engine.identify(gt.generated_phases)
        theta_sim = simulate_forward(
            report.state,
            initial_phase=gt.generated_phases.theta[0],
            n_steps=50,
            dt=0.05,
        )
        assert theta_sim.shape == (50, 4)
        assert float(theta_sim.min()) >= 0.0
        assert float(theta_sim.max()) < 2 * np.pi


# ---------------------------------------------------------------------------
# M3.3 — end-to-end evaluation
# ---------------------------------------------------------------------------


class TestEvaluateOOS:
    @staticmethod
    @pytest.fixture(scope="class")
    def engine_and_phases() -> tuple[NetworkKuramotoEngine, PhaseMatrix]:
        gt = generate_sakaguchi_kuramoto(
            SyntheticConfig(
                N=4,
                T=1500,
                dt=0.05,
                burn_in=50,
                seed=11,
                K_sparsity=0.5,
                K_scale=(0.4, 0.9),
                omega_center=0.7,
                omega_spread=0.3,
                tau_max=1,
                alpha_structure="zero",
                alpha_max=0.0,
                sigma_noise=0.015,
            )
        )
        engine = NetworkKuramotoEngine(
            NetworkEngineConfig(
                coupling=CouplingEstimationConfig(
                    penalty="mcp",
                    lambda_reg=0.1,
                    dt=0.05,
                    max_iter=500,
                    tol=1e-5,
                ),
                delay=DelayEstimationConfig(max_lag=1, dt=0.05),
            )
        )
        return engine, gt.generated_phases

    def test_result_fields_are_populated(
        self, engine_and_phases: tuple[NetworkKuramotoEngine, PhaseMatrix]
    ) -> None:
        engine, phases = engine_and_phases
        result = evaluate_oos(
            phases,
            engine,
            config=OOSConfig(
                train_frac=0.6,
                val_frac=0.2,
                n_bootstrap=50,
                block_length=10,
            ),
        )
        assert 0.0 <= result.phase_mae_val < 2 * np.pi
        assert 0.0 <= result.phase_mae_test < 2 * np.pi
        assert "random_walk" in result.dm_p_values
        assert "historical_mean" in result.dm_p_values
        assert "ar1" in result.dm_p_values
        assert 0.0 <= result.spa_p_value <= 1.0
        assert isinstance(result.passed_level_D, bool)

    def test_walk_forward_returns_n_results(
        self, engine_and_phases: tuple[NetworkKuramotoEngine, PhaseMatrix]
    ) -> None:
        engine, phases = engine_and_phases
        results = walk_forward_evaluate(
            phases,
            engine,
            n_folds=2,
            config=OOSConfig(
                train_frac=0.6,
                val_frac=0.2,
                n_bootstrap=30,
                block_length=8,
            ),
        )
        assert len(results) == 2
        for r in results:
            assert 0.0 <= r.spa_p_value <= 1.0

    def test_split_provenance_is_serialized(
        self, engine_and_phases: tuple[NetworkKuramotoEngine, PhaseMatrix]
    ) -> None:
        """Task 19: every OOS result carries its split provenance."""
        engine, phases = engine_and_phases
        cfg = OOSConfig(train_frac=0.6, val_frac=0.2, n_bootstrap=30, block_length=10)
        result = evaluate_oos(phases, engine, config=cfg)
        prov = result.split_provenance
        assert prov.split_method == "temporal_embargo"
        assert prov.horizon == cfg.horizon
        assert prov.embargo == cfg.embargo
        assert prov.n_total == phases.theta.shape[0]
        assert prov.train_span[0] == 0
        assert prov.test_span[1] == prov.n_total
        # contiguous at embargo 0
        assert prov.train_span[1] == prov.val_span[0]
        d = prov.to_dict()
        assert d["split_method"] == "temporal_embargo" and d["train_span"] == [0, prov.train_span[1]]

    def test_split_provenance_reflects_embargo(
        self, engine_and_phases: tuple[NetworkKuramotoEngine, PhaseMatrix]
    ) -> None:
        """Stress: perturbing the embargo must move the recorded spans."""
        engine, phases = engine_and_phases
        base = evaluate_oos(
            phases, engine, config=OOSConfig(n_bootstrap=20, block_length=10)
        ).split_provenance
        emb = evaluate_oos(
            phases, engine, config=OOSConfig(embargo=10, n_bootstrap=20, block_length=10)
        ).split_provenance
        assert base.val_span[0] == base.train_span[1]  # embargo 0 → contiguous
        assert emb.val_span[0] == emb.train_span[1] + 10  # embargo 10 → gap
        assert emb.test_span[0] == emb.val_span[1] + 10

    def test_degenerate_split_fails_closed(
        self, engine_and_phases: tuple[NetworkKuramotoEngine, PhaseMatrix]
    ) -> None:
        """Stress: an embargo that empties a split fails closed, not IndexError."""
        engine, phases = engine_and_phases
        n = phases.theta.shape[0]
        with pytest.raises(ValueError, match="degenerate split"):
            evaluate_oos(
                phases, engine, config=OOSConfig(embargo=n, n_bootstrap=20, block_length=10)
            )


class TestOOSConfig:
    def test_train_plus_val_must_be_less_than_one(self) -> None:
        with pytest.raises(ValueError, match="train_frac \\+ val_frac"):
            OOSConfig(train_frac=0.7, val_frac=0.4)

    def test_rejects_zero_horizon(self) -> None:
        with pytest.raises(ValueError):
            OOSConfig(horizon=0)
