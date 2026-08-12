# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for adaptive neuromodulator calibration system."""

from __future__ import annotations

import time

import numpy as np
import pytest

from core.utils.determinism import DEFAULT_SEED, seed_numpy
from geosync.core.neuro.adaptive_calibrator import (
    AdaptiveCalibrator,
    CalibrationMetrics,
)


@pytest.fixture
def initial_params():
    """Fixture providing initial neuromodulator parameters."""
    return {
        "dopamine": {
            "discount_gamma": 0.99,
            "learning_rate": 0.01,
            "burst_factor": 1.5,
            "base_temperature": 1.0,
            "invigoration_threshold": 0.6,
        },
        "serotonin": {
            "stress_threshold": 0.15,
            "release_threshold": 0.10,
            "desensitization_rate": 0.01,
            "floor_min": 0.2,
        },
        "gaba": {
            "k_inhibit": 0.4,
            "impulse_threshold": 0.5,
            "stdp_lr": 0.01,
            "max_inhibition": 0.85,
        },
        "na_ach": {
            "arousal_gain": 1.2,
            "attention_gain": 1.0,
            "risk_min": 0.5,
            "risk_max": 1.5,
        },
    }


@pytest.fixture
def sample_metrics():
    """Fixture providing sample calibration metrics."""
    return CalibrationMetrics(
        sharpe_ratio=1.5,
        max_drawdown=0.08,
        win_rate=0.65,
        avg_hold_time=25.0,
        dopamine_stability=0.3,
        serotonin_stress=0.25,
        gaba_inhibition_rate=0.35,
        na_ach_arousal=1.1,
        total_trades=100,
        timestamp=time.time(),
    )


class TestCalibrationMetrics:
    """Tests for CalibrationMetrics dataclass."""

    def test_composite_score_default_weights(self, sample_metrics):
        """Test composite score calculation with default weights."""
        score = sample_metrics.composite_score()

        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_composite_score_custom_weights(self, sample_metrics):
        """Test composite score with custom weights."""
        custom_weights = {
            "sharpe": 0.5,
            "drawdown": 0.2,
            "win_rate": 0.1,
            "stability": 0.1,
            "stress": 0.05,
            "arousal": 0.05,
        }

        score = sample_metrics.composite_score(custom_weights)

        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_composite_score_high_performance(self):
        """Test composite score with excellent metrics."""
        metrics = CalibrationMetrics(
            sharpe_ratio=3.0,
            max_drawdown=0.02,
            win_rate=0.80,
            avg_hold_time=20.0,
            dopamine_stability=0.1,
            serotonin_stress=0.1,
            gaba_inhibition_rate=0.3,
            na_ach_arousal=1.0,
            total_trades=200,
            timestamp=time.time(),
        )

        score = metrics.composite_score()

        # Should be high for excellent metrics
        assert score > 0.7

    def test_composite_score_poor_performance(self):
        """Test composite score with poor metrics."""
        metrics = CalibrationMetrics(
            sharpe_ratio=-0.5,
            max_drawdown=0.25,
            win_rate=0.35,
            avg_hold_time=50.0,
            dopamine_stability=0.6,
            serotonin_stress=0.7,
            gaba_inhibition_rate=0.8,
            na_ach_arousal=0.5,
            total_trades=50,
            timestamp=time.time(),
        )

        score = metrics.composite_score()

        # Should be low for poor metrics
        assert score < 0.5


class TestAdaptiveCalibrator:
    """Tests for AdaptiveCalibrator class."""

    def test_initialization(self, initial_params):
        """Test calibrator initialization."""
        calibrator = AdaptiveCalibrator(initial_params)

        assert calibrator.state.iteration == 0
        assert calibrator.state.best_score == -np.inf
        assert calibrator.state.temperature == 1.0
        assert len(calibrator.state.metrics_history) == 0

    def test_initialization_missing_neuromodulator(self):
        """Test initialization fails with missing neuromodulator."""
        incomplete_params = {
            "dopamine": {"learning_rate": 0.01},
            # Missing serotonin, gaba, na_ach
        }

        with pytest.raises(ValueError, match="Missing required"):
            AdaptiveCalibrator(incomplete_params)

    def test_step_updates_state(self, initial_params, sample_metrics):
        """Test that step() updates calibrator state."""
        calibrator = AdaptiveCalibrator(initial_params)

        new_params = calibrator.step(sample_metrics)

        assert calibrator.state.iteration == 1
        assert len(calibrator.state.metrics_history) == 1
        assert calibrator.state.temperature < 1.0  # Temperature should decay
        assert isinstance(new_params, dict)

    def test_step_improves_best_score(self, initial_params):
        """Test that better metrics update best score."""
        calibrator = AdaptiveCalibrator(initial_params)

        # First step with moderate metrics
        metrics1 = CalibrationMetrics(
            sharpe_ratio=1.0,
            max_drawdown=0.1,
            win_rate=0.5,
            avg_hold_time=30.0,
            dopamine_stability=0.3,
            serotonin_stress=0.3,
            gaba_inhibition_rate=0.4,
            na_ach_arousal=1.0,
            total_trades=50,
            timestamp=time.time(),
        )
        calibrator.step(metrics1)
        first_best = calibrator.state.best_score

        # Second step with better metrics
        metrics2 = CalibrationMetrics(
            sharpe_ratio=2.0,
            max_drawdown=0.05,
            win_rate=0.7,
            avg_hold_time=25.0,
            dopamine_stability=0.2,
            serotonin_stress=0.2,
            gaba_inhibition_rate=0.3,
            na_ach_arousal=1.1,
            total_trades=100,
            timestamp=time.time(),
        )
        calibrator.step(metrics2)

        assert calibrator.state.best_score > first_best

    def test_parameter_bounds(self, initial_params, sample_metrics):
        """Test that parameters stay within bounds."""
        calibrator = AdaptiveCalibrator(initial_params)

        # Run multiple steps
        for _ in range(10):
            new_params = calibrator.step(sample_metrics)

            # Check dopamine bounds
            assert 0.90 <= new_params["dopamine"]["discount_gamma"] <= 0.999
            assert 0.001 <= new_params["dopamine"]["learning_rate"] <= 0.05

            # Check serotonin bounds
            assert 0.1 <= new_params["serotonin"]["stress_threshold"] <= 0.3

            # Check GABA bounds
            assert 0.2 <= new_params["gaba"]["k_inhibit"] <= 0.8

            # Check NA/ACh bounds
            assert 0.8 <= new_params["na_ach"]["arousal_gain"] <= 2.0

    def test_temperature_decay(self, initial_params, sample_metrics):
        """Test that temperature decays over iterations."""
        calibrator = AdaptiveCalibrator(
            initial_params,
            temperature_initial=1.0,
            temperature_decay=0.95,
            min_temperature=0.01,
        )

        initial_temp = calibrator.state.temperature

        # Run several steps
        for _ in range(20):
            calibrator.step(sample_metrics)

        final_temp = calibrator.state.temperature

        assert final_temp < initial_temp
        assert final_temp >= 0.01  # Should not go below minimum

    def test_reset_exploration(self, initial_params, sample_metrics):
        """Test exploration reset after patience threshold."""
        calibrator = AdaptiveCalibrator(
            initial_params,
            patience=10,
        )

        # Run steps without improvement
        for _ in range(15):
            calibrator.step(sample_metrics)

        # Temperature should have been reset
        assert calibrator.state.temperature > calibrator.min_temperature * 2

    def test_get_best_params(self, initial_params, sample_metrics):
        """Test retrieving best parameters."""
        calibrator = AdaptiveCalibrator(initial_params)

        calibrator.step(sample_metrics)
        best = calibrator.get_best_params()

        assert isinstance(best, dict)
        assert "dopamine" in best
        assert "serotonin" in best
        assert "gaba" in best
        assert "na_ach" in best

    def test_calibration_report(self, initial_params, sample_metrics):
        """Test calibration report generation."""
        calibrator = AdaptiveCalibrator(initial_params)

        # Initial report should have no data
        report = calibrator.get_calibration_report()
        assert report["status"] == "no_data"

        # After steps, should have data
        for _ in range(5):
            calibrator.step(sample_metrics)

        report = calibrator.get_calibration_report()
        assert report["status"] == "active"
        assert "iteration" in report
        assert "best_score" in report
        assert "best_params" in report
        assert "recommendations" in report

    def test_recommendations_high_drawdown(self, initial_params):
        """Test recommendations for high drawdown."""
        calibrator = AdaptiveCalibrator(initial_params)

        high_dd_metrics = CalibrationMetrics(
            sharpe_ratio=1.0,
            max_drawdown=0.20,  # High drawdown
            win_rate=0.5,
            avg_hold_time=30.0,
            dopamine_stability=0.3,
            serotonin_stress=0.3,
            gaba_inhibition_rate=0.4,
            na_ach_arousal=1.0,
            total_trades=50,
            timestamp=time.time(),
        )

        calibrator.step(high_dd_metrics)
        report = calibrator.get_calibration_report()

        recommendations = report["recommendations"]
        assert any("drawdown" in rec.lower() for rec in recommendations)

    def test_export_and_restore_state(self, initial_params, sample_metrics):
        """Test state export and restoration."""
        calibrator1 = AdaptiveCalibrator(initial_params)

        # Run some steps
        for _ in range(5):
            calibrator1.step(sample_metrics)

        # Export state
        state_dict = calibrator1.export_state()

        # Restore to new calibrator
        calibrator2 = AdaptiveCalibrator.from_state(state_dict)

        # Check state matches
        assert calibrator2.state.iteration == calibrator1.state.iteration
        assert calibrator2.state.best_score == calibrator1.state.best_score
        assert calibrator2.state.temperature == calibrator1.state.temperature
        assert len(calibrator2.state.metrics_history) == len(calibrator1.state.metrics_history)

    def test_objective_trajectory_is_deterministic_with_seed(self, initial_params):
        """Ensure identical seeds yield identical objective trajectories."""

        def run_sequence(seed: int) -> list[float]:
            seed_numpy(seed)
            rng = np.random.default_rng(seed)
            calibrator = AdaptiveCalibrator(initial_params)
            objectives: list[float] = []

            for step in range(12):
                metrics = CalibrationMetrics(
                    sharpe_ratio=1.2 + rng.normal(0, 0.1),
                    max_drawdown=0.08 + abs(rng.normal(0, 0.01)),
                    win_rate=0.6 + rng.normal(0, 0.02),
                    avg_hold_time=25.0 + rng.normal(0, 1.0),
                    dopamine_stability=0.3 + abs(rng.normal(0, 0.05)),
                    serotonin_stress=0.25 + abs(rng.normal(0, 0.05)),
                    gaba_inhibition_rate=0.35 + abs(rng.normal(0, 0.03)),
                    na_ach_arousal=1.0 + rng.normal(0, 0.05),
                    total_trades=100 + step,
                    timestamp=float(step),
                )
                calibrator.step(metrics)
                objectives.append(calibrator.state.best_score)

            return objectives

        trajectory_a = run_sequence(DEFAULT_SEED)
        trajectory_b = run_sequence(DEFAULT_SEED)

        np.testing.assert_allclose(trajectory_a, trajectory_b, rtol=1e-7, atol=1e-9)


@pytest.mark.integration
class TestAdaptiveCalibratorIntegration:
    """Integration tests for adaptive calibrator."""

    def test_calibration_improves_over_time(self, initial_params):
        """Test that calibration improves performance over time."""
        calibrator = AdaptiveCalibrator(initial_params)

        # Simulate improving performance
        scores = []
        for i in range(20):
            # Gradually improve metrics
            metrics = CalibrationMetrics(
                sharpe_ratio=1.0 + i * 0.05,
                max_drawdown=0.10 - i * 0.002,
                win_rate=0.50 + i * 0.01,
                avg_hold_time=30.0,
                dopamine_stability=0.3,
                serotonin_stress=0.3,
                gaba_inhibition_rate=0.4,
                na_ach_arousal=1.0,
                total_trades=50 + i * 5,
                timestamp=time.time(),
            )

            calibrator.step(metrics)
            scores.append(calibrator.state.best_score)

        # Best score should improve
        assert scores[-1] > scores[0]

    def test_handles_noisy_metrics(self, initial_params):
        """Test calibrator handles noisy performance metrics."""
        calibrator = AdaptiveCalibrator(initial_params)

        # Add noise to metrics
        np.random.seed(42)
        for _ in range(30):
            metrics = CalibrationMetrics(
                sharpe_ratio=1.5 + np.random.randn() * 0.5,
                max_drawdown=0.08 + abs(np.random.randn() * 0.02),
                win_rate=0.60 + np.random.randn() * 0.1,
                avg_hold_time=25.0 + np.random.randn() * 5,
                dopamine_stability=0.3 + abs(np.random.randn() * 0.1),
                serotonin_stress=0.25 + abs(np.random.randn() * 0.1),
                gaba_inhibition_rate=0.35 + abs(np.random.randn() * 0.1),
                na_ach_arousal=1.0 + np.random.randn() * 0.2,
                total_trades=100,
                timestamp=time.time(),
            )

            # Should not crash
            new_params = calibrator.step(metrics)
            assert isinstance(new_params, dict)
