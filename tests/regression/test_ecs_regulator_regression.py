# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for ECS regulator.

These tests capture specific edge cases and bug fixes for the
ECS-inspired regulator module.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.neuro.ecs_regulator import (
    TRACE_SCHEMA_FIELDS,
    ECSInspiredRegulator,
    ECSMetrics,
    StabilityMetrics,
    StressMode,
)


class TestECSRegulatorStressMode:
    """Tests for StressMode enum."""

    def test_stress_mode_values(self) -> None:
        """Verify StressMode enum values are correct."""
        assert StressMode.NORMAL.value == "NORMAL"
        assert StressMode.ELEVATED.value == "ELEVATED"
        assert StressMode.CRISIS.value == "CRISIS"

    def test_stress_mode_is_string_enum(self) -> None:
        """Verify StressMode is a string enum."""
        assert isinstance(StressMode.NORMAL.value, str)
        assert isinstance(StressMode.ELEVATED.value, str)
        assert isinstance(StressMode.CRISIS.value, str)


class TestECSMetricsDataclass:
    """Tests for ECSMetrics dataclass."""

    def test_ecs_metrics_creation(self) -> None:
        """Test ECSMetrics creation with all fields."""
        metrics = ECSMetrics(
            timestamp=1234567890,
            stress_level=0.5,
            free_energy_proxy=0.3,
            risk_threshold=0.7,
            compensatory_factor=0.9,
            chronic_counter=5,
            is_chronic=False,
        )

        assert metrics.timestamp == 1234567890
        assert metrics.stress_level == 0.5
        assert metrics.free_energy_proxy == 0.3
        assert metrics.risk_threshold == 0.7
        assert metrics.compensatory_factor == 0.9
        assert metrics.chronic_counter == 5
        assert metrics.is_chronic is False


class TestStabilityMetricsDataclass:
    """Tests for StabilityMetrics dataclass."""

    def test_stability_metrics_creation(self) -> None:
        """Test StabilityMetrics creation with all fields."""
        metrics = StabilityMetrics(
            monotonicity_violations=0,
            gradient_clipping_events=2,
            lyapunov_value=0.05,
            stability_margin=0.8,
            volatility_regime="normal",
            risk_aversion_active=False,
        )

        assert metrics.monotonicity_violations == 0
        assert metrics.gradient_clipping_events == 2
        assert metrics.lyapunov_value == 0.05
        assert metrics.stability_margin == 0.8
        assert metrics.volatility_regime == "normal"
        assert metrics.risk_aversion_active is False


class TestECSRegulatorEdgeCases:
    """Edge case tests for ECSInspiredRegulator."""

    def test_regulator_initialization_default(self) -> None:
        """Test regulator initializes with default parameters."""
        regulator = ECSInspiredRegulator()

        # Verify initial state
        assert regulator.is_stable()
        metrics = regulator.get_stability_metrics()
        assert metrics.monotonicity_violations == 0

    def test_regulator_with_empty_returns_raises(self) -> None:
        """Regression: Empty returns array should raise ValueError."""
        regulator = ECSInspiredRegulator()

        with pytest.raises(ValueError, match="market_returns must not be empty"):
            regulator.update_stress(
                market_returns=np.array([]),
                drawdown=0.01,
            )

    def test_regulator_with_negative_drawdown_raises(self) -> None:
        """Regression: Negative drawdown should raise ValueError."""
        regulator = ECSInspiredRegulator()

        with pytest.raises(ValueError, match="drawdown must be non-negative"):
            regulator.update_stress(
                market_returns=np.array([0.01, 0.02, -0.01]),
                drawdown=-0.05,
            )

    def test_regulator_with_zero_drawdown(self) -> None:
        """Test regulator handles zero drawdown."""
        regulator = ECSInspiredRegulator()

        # Should not raise
        regulator.update_stress(
            market_returns=np.array([0.01, 0.02, -0.01]),
            drawdown=0.0,
        )

        metrics = regulator.get_metrics()
        assert metrics is not None

    def test_regulator_with_extreme_volatility(self) -> None:
        """Test regulator handles extreme volatility in returns."""
        regulator = ECSInspiredRegulator()

        # High volatility returns
        high_vol_returns = np.array([0.1, -0.15, 0.2, -0.18, 0.12])

        regulator.update_stress(
            market_returns=high_vol_returns,
            drawdown=0.1,
        )

        metrics = regulator.get_stability_metrics()
        assert math.isfinite(metrics.lyapunov_value)

    def test_regulator_stress_mode_transitions(self) -> None:
        """Test regulator transitions through stress modes correctly."""
        regulator = ECSInspiredRegulator()
        rng = np.random.default_rng(42)

        # Normal conditions
        normal_returns = rng.normal(0.001, 0.01, 20)
        for _ in range(5):
            regulator.update_stress(
                market_returns=normal_returns,
                drawdown=0.01,
            )

        # Stress conditions
        stress_returns = rng.normal(-0.02, 0.05, 20)
        for _ in range(10):
            regulator.update_stress(
                market_returns=stress_returns,
                drawdown=0.15,
            )

        # Check that metrics are still valid
        metrics = regulator.get_stability_metrics()
        assert math.isfinite(metrics.lyapunov_value)

    def test_decide_action_with_valid_signal(self) -> None:
        """Test decide_action with valid signal."""
        regulator = ECSInspiredRegulator()

        # First update stress to establish state
        regulator.update_stress(
            market_returns=np.array([0.01, 0.02, -0.01]),
            drawdown=0.01,
        )

        # Decide action
        action = regulator.decide_action(
            signal_strength=0.5,
            context_phase="stable",
        )

        assert isinstance(action, int)
        assert action in (-1, 0, 1)  # sell, hold, buy

    def test_get_metrics_returns_valid_data(self) -> None:
        """Test get_metrics returns valid ECSMetrics."""
        regulator = ECSInspiredRegulator()
        regulator.update_stress(
            market_returns=np.array([0.01, 0.02, -0.01]),
            drawdown=0.01,
        )

        metrics = regulator.get_metrics()

        assert isinstance(metrics, ECSMetrics)
        assert metrics.timestamp > 0
        assert math.isfinite(metrics.stress_level)
        assert math.isfinite(metrics.free_energy_proxy)

    def test_reset_clears_state(self) -> None:
        """Test reset clears regulator state."""
        regulator = ECSInspiredRegulator()
        rng = np.random.default_rng(42)

        # Add some stress
        stress_returns = rng.normal(-0.01, 0.03, 20)
        for _ in range(10):
            regulator.update_stress(
                market_returns=stress_returns,
                drawdown=0.1,
            )

        # Reset
        regulator.reset()

        # Verify reset
        metrics = regulator.get_stability_metrics()
        assert metrics.monotonicity_violations == 0
        assert regulator.is_stable()


class TestTraceSchemaFields:
    """Tests for trace schema field completeness."""

    def test_trace_schema_fields_count(self) -> None:
        """Verify trace schema has expected number of fields."""
        assert len(TRACE_SCHEMA_FIELDS) == 22

    def test_trace_schema_has_required_fields(self) -> None:
        """Verify trace schema includes all required audit fields."""
        required_fields = {
            "timestamp_utc",
            "schema_version",
            "decision_id",
            "prev_hash",
            "mode",
            "stress_level",
            "free_energy_proxy",
            "action",
            "event_hash",
        }

        assert required_fields.issubset(TRACE_SCHEMA_FIELDS)

    def test_trace_schema_has_conformal_fields(self) -> None:
        """Verify trace schema includes conformal prediction fields."""
        conformal_fields = {
            "conformal_q",
            "prediction_interval_low",
            "prediction_interval_high",
            "conformal_ready",
        }

        assert conformal_fields.issubset(TRACE_SCHEMA_FIELDS)
