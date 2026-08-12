# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for physics_validator module."""

from __future__ import annotations

import pytest

from core.validation.physics_validator import (
    SYSTEM_TEMPERATURE_K,
    EnergyBounds,
    PhysicsValidator,
    ThermodynamicState,
    compute_energy_gradient,
)


class TestThermodynamicState:
    """Tests for ThermodynamicState dataclass."""

    def test_basic_construction(self):
        """Test basic state construction."""
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )
        assert state.free_energy == 1e-18
        assert state.entropy == 0.5
        assert state.temperature == 300.0

    def test_default_values(self):
        """Test default temperature and other values."""
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        assert state.temperature == SYSTEM_TEMPERATURE_K
        assert state.internal_energy == 0.0
        assert state.resource_usage == 0.0

    def test_gibbs_energy_calculation(self):
        """Test Gibbs free energy calculation."""
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
            internal_energy=200.0,
        )
        # G = U - TS = 200 - 300*0.5 = 50
        assert state.gibbs_energy == pytest.approx(50.0)

    def test_invalid_nan_raises(self):
        """Test that NaN values raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            ThermodynamicState(free_energy=float("nan"), entropy=0.5)

    def test_invalid_inf_raises(self):
        """Test that Inf values raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            ThermodynamicState(free_energy=float("inf"), entropy=0.5)

    def test_negative_temperature_raises(self):
        """Test that negative temperature raises ValueError."""
        with pytest.raises(ValueError, match="Temperature must be positive"):
            ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=-10.0)

    def test_invalid_resource_usage_raises(self):
        """Test that resource_usage outside [0,1] raises ValueError."""
        with pytest.raises(ValueError, match="resource_usage must be in"):
            ThermodynamicState(free_energy=1e-18, entropy=0.5, resource_usage=1.5)

    def test_as_mapping(self):
        """Test conversion to dictionary."""
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )
        mapping = state.as_mapping()
        assert "free_energy" in mapping
        assert "entropy" in mapping
        assert "gibbs_energy" in mapping


class TestEnergyBounds:
    """Tests for EnergyBounds configuration."""

    def test_default_bounds(self):
        """Test default bounds values."""
        bounds = EnergyBounds()
        assert bounds.min_free_energy < 0
        assert bounds.max_free_energy > 0
        assert bounds.max_energy_rate > 0

    def test_custom_bounds(self):
        """Test custom bounds configuration."""
        bounds = EnergyBounds(
            min_free_energy=-1e-14,
            max_free_energy=1e-14,
            max_energy_rate=1e-16,
        )
        assert bounds.min_free_energy == -1e-14
        assert bounds.max_free_energy == 1e-14


class TestPhysicsValidator:
    """Tests for PhysicsValidator."""

    @pytest.fixture
    def validator(self):
        """Create a default validator."""
        return PhysicsValidator()

    @pytest.fixture
    def valid_state(self):
        """Create a valid thermodynamic state."""
        return ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )

    def test_validate_valid_state(self, validator, valid_state):
        """Test validation of a valid state."""
        report = validator.validate_state(valid_state)
        assert report.is_valid
        assert len(report.violations) == 0

    def test_validate_state_below_energy_minimum(self, validator):
        """Test detection of energy below minimum."""
        state = ThermodynamicState(
            free_energy=-1e-14,  # Below default minimum
            entropy=0.5,
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("below minimum" in v for v in report.violations)

    def test_validate_state_above_energy_maximum(self, validator):
        """Test detection of energy above maximum."""
        state = ThermodynamicState(
            free_energy=1e-14,  # Above default maximum
            entropy=0.5,
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("above maximum" in v for v in report.violations)

    def test_validate_valid_transition(self, validator):
        """Test validation of a valid transition."""
        state1 = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        state2 = ThermodynamicState(free_energy=0.99e-18, entropy=0.51)
        report = validator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid
        assert report.entropy_delta > 0  # Entropy increased

    def test_validate_entropy_decrease_violation(self, validator):
        """Test detection of significant entropy decrease."""
        state1 = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        state2 = ThermodynamicState(free_energy=1e-18, entropy=0.3)  # Decrease
        report = validator.validate_transition(state1, state2, dt=1.0)
        assert not report.is_valid
        assert any("Second Law" in v for v in report.violations)

    def test_validate_small_entropy_decrease_allowed(self, validator):
        """Test that numerical noise in entropy is tolerated."""
        state1 = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        # Very small decrease within tolerance
        state2 = ThermodynamicState(free_energy=1e-18, entropy=0.5 - 1e-7)
        report = validator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid

    def test_validate_excessive_energy_rate(self):
        """Test detection of excessive energy change rate."""
        bounds = EnergyBounds(max_energy_rate=1e-20)
        validator = PhysicsValidator(bounds)
        state1 = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        state2 = ThermodynamicState(free_energy=0.9e-18, entropy=0.5)
        report = validator.validate_transition(state1, state2, dt=0.001)
        assert not report.is_valid
        assert any("rate" in v.lower() for v in report.violations)

    def test_validate_zero_dt_raises(self, validator, valid_state):
        """Test that zero time delta raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(valid_state, valid_state, dt=0.0)

    def test_validate_negative_dt_raises(self, validator, valid_state):
        """Test that negative time delta raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(valid_state, valid_state, dt=-1.0)

    def test_validate_trajectory(self, validator):
        """Test trajectory validation."""
        states = [
            ThermodynamicState(free_energy=1e-18, entropy=0.5),
            ThermodynamicState(free_energy=0.99e-18, entropy=0.51),
            ThermodynamicState(free_energy=0.98e-18, entropy=0.52),
        ]
        timestamps = [0.0, 1000.0, 2000.0]  # milliseconds
        report = validator.validate_trajectory(states, timestamps)
        assert report.is_valid

    def test_validate_trajectory_single_state(self, validator, valid_state):
        """Test trajectory with single state."""
        report = validator.validate_trajectory([valid_state])
        assert report.is_valid

    def test_validate_trajectory_empty(self, validator):
        """Test trajectory with no states."""
        report = validator.validate_trajectory([])
        assert report.is_valid


class TestComputeEnergyGradient:
    """Tests for compute_energy_gradient function."""

    def test_gradient_computation(self):
        """Test basic gradient computation."""
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )
        gradients = compute_energy_gradient(state)
        assert "entropy" in gradients
        assert "temperature" in gradients
        assert "internal_energy" in gradients

    def test_entropy_gradient_sign(self):
        """Test that entropy gradient has correct sign (dG/dS = -T)."""
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )
        gradients = compute_energy_gradient(state)
        # dG/dS = -T, so should be negative
        assert gradients["entropy"] < 0
        assert gradients["entropy"] == pytest.approx(-300.0)
