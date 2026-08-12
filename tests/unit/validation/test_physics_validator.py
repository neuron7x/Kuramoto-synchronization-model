# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for core.validation.physics_validator module."""

from __future__ import annotations

import pytest

from core.validation.physics_validator import (
    ENERGY_SCALE,
    K_BOLTZMANN_EFFECTIVE,
    SYSTEM_TEMPERATURE_K,
    EnergyBounds,
    PhysicsConstraintReport,
    PhysicsValidator,
    ThermodynamicState,
    compute_energy_gradient,
)


class TestThermodynamicState:
    """Tests for ThermodynamicState dataclass."""

    def test_basic_creation(self) -> None:
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
        )
        assert state.free_energy == 1e-18
        assert state.entropy == 0.5
        assert state.temperature == 300.0

    def test_default_values(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        assert state.temperature == SYSTEM_TEMPERATURE_K
        assert state.internal_energy == 0.0
        assert state.resource_usage == 0.0
        assert state.timestamp_ms is None

    def test_validation_nan(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ThermodynamicState(
                free_energy=float("nan"),
                entropy=0.5,
            )

    def test_validation_inf(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ThermodynamicState(
                free_energy=float("inf"),
                entropy=0.5,
            )

    def test_validation_negative_temperature(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            ThermodynamicState(
                free_energy=1e-18,
                entropy=0.5,
                temperature=-100.0,
            )

    def test_validation_zero_temperature(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            ThermodynamicState(
                free_energy=1e-18,
                entropy=0.5,
                temperature=0.0,
            )

    def test_validation_resource_usage_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            ThermodynamicState(
                free_energy=1e-18,
                entropy=0.5,
                resource_usage=1.5,
            )

    def test_validation_resource_usage_negative(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            ThermodynamicState(
                free_energy=1e-18,
                entropy=0.5,
                resource_usage=-0.1,
            )

    def test_gibbs_energy(self) -> None:
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
            internal_energy=200.0,
        )
        # G = U - TS = 200 - 300*0.5 = 50
        assert state.gibbs_energy == pytest.approx(50.0)

    def test_as_mapping(self) -> None:
        state = ThermodynamicState(
            free_energy=1e-18,
            entropy=0.5,
            temperature=300.0,
            internal_energy=100.0,
            resource_usage=0.3,
        )
        mapping = state.as_mapping()
        assert mapping["free_energy"] == 1e-18
        assert mapping["entropy"] == 0.5
        assert mapping["temperature"] == 300.0
        assert mapping["internal_energy"] == 100.0
        assert mapping["resource_usage"] == 0.3
        assert "gibbs_energy" in mapping


class TestEnergyBounds:
    """Tests for EnergyBounds dataclass."""

    def test_default_values(self) -> None:
        bounds = EnergyBounds()
        assert bounds.min_free_energy == -1e-15
        assert bounds.max_free_energy == 1e-15
        assert bounds.max_energy_rate == 1e-17
        assert bounds.min_entropy == 0.0
        assert bounds.max_entropy == 10.0
        assert bounds.entropy_tolerance == 1e-6
        assert bounds.energy_conservation_tolerance == 0.1

    def test_custom_values(self) -> None:
        bounds = EnergyBounds(
            min_free_energy=-1e-14,
            max_free_energy=1e-14,
            max_energy_rate=1e-16,
        )
        assert bounds.min_free_energy == -1e-14
        assert bounds.max_free_energy == 1e-14
        assert bounds.max_energy_rate == 1e-16


class TestPhysicsConstraintReport:
    """Tests for PhysicsConstraintReport dataclass."""

    def test_add_violation(self) -> None:
        report = PhysicsConstraintReport(
            is_valid=True,
            energy_delta=0.0,
            entropy_delta=0.0,
            energy_rate=0.0,
        )
        report.add_violation("Test violation")
        assert not report.is_valid
        assert len(report.violations) == 1

    def test_add_warning(self) -> None:
        report = PhysicsConstraintReport(
            is_valid=True,
            energy_delta=0.0,
            entropy_delta=0.0,
            energy_rate=0.0,
        )
        report.add_warning("Test warning")
        assert report.is_valid
        assert len(report.warnings) == 1


class TestPhysicsValidator:
    """Tests for PhysicsValidator class."""

    def test_default_initialization(self) -> None:
        validator = PhysicsValidator()
        assert validator.bounds.min_free_energy == -1e-15

    def test_custom_bounds(self) -> None:
        bounds = EnergyBounds(min_free_energy=-1e-14)
        validator = PhysicsValidator(bounds)
        assert validator.bounds.min_free_energy == -1e-14


class TestValidateState:
    """Tests for validate_state method."""

    def test_valid_state(self) -> None:
        validator = PhysicsValidator()
        state = ThermodynamicState(free_energy=0.0, entropy=0.5)
        report = validator.validate_state(state)
        assert report.is_valid
        assert len(report.violations) == 0

    def test_energy_below_minimum(self) -> None:
        bounds = EnergyBounds(min_free_energy=-1e-15)
        validator = PhysicsValidator(bounds)
        state = ThermodynamicState(free_energy=-1e-14, entropy=0.5)
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("below minimum" in v for v in report.violations)

    def test_energy_above_maximum(self) -> None:
        bounds = EnergyBounds(max_free_energy=1e-15)
        validator = PhysicsValidator(bounds)
        state = ThermodynamicState(free_energy=1e-14, entropy=0.5)
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("above maximum" in v for v in report.violations)

    def test_entropy_below_minimum(self) -> None:
        bounds = EnergyBounds(min_entropy=0.1)
        validator = PhysicsValidator(bounds)
        state = ThermodynamicState(free_energy=0.0, entropy=0.05)
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("below minimum" in v for v in report.violations)

    def test_entropy_above_maximum(self) -> None:
        bounds = EnergyBounds(max_entropy=1.0)
        validator = PhysicsValidator(bounds)
        state = ThermodynamicState(free_energy=0.0, entropy=2.0)
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("above maximum" in v for v in report.violations)

    def test_energy_warning_lower_bound(self) -> None:
        bounds = EnergyBounds(min_free_energy=-1e-15, max_free_energy=1e-15)
        validator = PhysicsValidator(bounds)
        # Near lower bound
        state = ThermodynamicState(free_energy=-0.95e-15, entropy=0.5)
        report = validator.validate_state(state)
        assert any("approaching lower bound" in w for w in report.warnings)

    def test_energy_warning_upper_bound(self) -> None:
        bounds = EnergyBounds(min_free_energy=-1e-15, max_free_energy=1e-15)
        validator = PhysicsValidator(bounds)
        # Near upper bound
        state = ThermodynamicState(free_energy=0.95e-15, entropy=0.5)
        report = validator.validate_state(state)
        assert any("approaching upper bound" in w for w in report.warnings)

    def test_metrics_populated(self) -> None:
        validator = PhysicsValidator()
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        report = validator.validate_state(state)
        assert "free_energy" in report.metrics
        assert "entropy" in report.metrics
        assert "temperature" in report.metrics
        assert "gibbs_energy" in report.metrics


class TestValidateTransition:
    """Tests for validate_transition method."""

    def test_valid_transition(self) -> None:
        validator = PhysicsValidator()
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=1e-20, entropy=0.51)
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert report.is_valid

    def test_invalid_dt_zero(self) -> None:
        validator = PhysicsValidator()
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=1e-20, entropy=0.51)
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(state_before, state_after, dt=0.0)

    def test_invalid_dt_negative(self) -> None:
        validator = PhysicsValidator()
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=1e-20, entropy=0.51)
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(state_before, state_after, dt=-1.0)

    def test_second_law_violation(self) -> None:
        bounds = EnergyBounds(entropy_tolerance=1e-6)
        validator = PhysicsValidator(bounds)
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=0.0, entropy=0.4)  # Entropy decreased
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert not report.is_valid
        assert any("Second Law violation" in v for v in report.violations)

    def test_energy_rate_violation(self) -> None:
        bounds = EnergyBounds(max_energy_rate=1e-18)
        validator = PhysicsValidator(bounds)
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=1e-15, entropy=0.5)  # Large energy change
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert not report.is_valid
        assert any("Energy rate" in v and "exceeds" in v for v in report.violations)

    def test_energy_rate_warning(self) -> None:
        bounds = EnergyBounds(max_energy_rate=1e-17)
        validator = PhysicsValidator(bounds)
        state_before = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state_after = ThermodynamicState(free_energy=0.85e-17, entropy=0.5)  # 85% of limit
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert any("approaching limit" in w for w in report.warnings)

    def test_large_energy_change_warning(self) -> None:
        bounds = EnergyBounds(
            max_energy_rate=1e-10,  # High rate limit
            energy_conservation_tolerance=0.05,  # 5% tolerance
        )
        validator = PhysicsValidator(bounds)
        state_before = ThermodynamicState(free_energy=1e-15, entropy=0.5)
        state_after = ThermodynamicState(free_energy=1e-16, entropy=0.51)  # 90% energy change
        report = validator.validate_transition(state_before, state_after, dt=100.0)
        assert any("Large energy change" in w for w in report.warnings)

    def test_inherits_state_violations(self) -> None:
        bounds = EnergyBounds(max_free_energy=1e-15)
        validator = PhysicsValidator(bounds)
        state_before = ThermodynamicState(free_energy=1e-14, entropy=0.5)  # Invalid
        state_after = ThermodynamicState(free_energy=0.0, entropy=0.5)
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert any("Initial state:" in v for v in report.violations)

    def test_transition_metrics(self) -> None:
        validator = PhysicsValidator()
        state_before = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        state_after = ThermodynamicState(free_energy=2e-18, entropy=0.6)
        report = validator.validate_transition(state_before, state_after, dt=0.5)
        assert report.metrics["dt"] == 0.5
        assert report.metrics["energy_delta"] == pytest.approx(1e-18)
        assert report.metrics["entropy_delta"] == pytest.approx(0.1)
        assert "initial_free_energy" in report.metrics
        assert "final_free_energy" in report.metrics


class TestValidateTrajectory:
    """Tests for validate_trajectory method."""

    def test_single_state_trajectory(self) -> None:
        validator = PhysicsValidator()
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        report = validator.validate_trajectory([state])
        assert report.is_valid
        assert report.energy_delta == 0.0

    def test_empty_trajectory(self) -> None:
        validator = PhysicsValidator()
        report = validator.validate_trajectory([])
        assert report.is_valid

    def test_valid_trajectory(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(free_energy=i * 1e-20, entropy=0.5 + i * 0.01) for i in range(5)
        ]
        report = validator.validate_trajectory(states)
        assert report.is_valid
        assert report.metrics["trajectory_length"] == 5

    def test_trajectory_with_timestamps(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(free_energy=i * 1e-20, entropy=0.5 + i * 0.01) for i in range(3)
        ]
        timestamps = [0.0, 1000.0, 2000.0]
        report = validator.validate_trajectory(states, timestamps_ms=timestamps)
        assert report.is_valid

    def test_trajectory_with_state_timestamps(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(
                free_energy=i * 1e-20,
                entropy=0.5 + i * 0.01,
                timestamp_ms=float(i * 1000),
            )
            for i in range(3)
        ]
        report = validator.validate_trajectory(states)
        assert report.is_valid

    def test_trajectory_skips_invalid_dt(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(free_energy=1e-18, entropy=0.5, timestamp_ms=1000.0),
            ThermodynamicState(
                free_energy=1e-18, entropy=0.5, timestamp_ms=1000.0
            ),  # Same timestamp
        ]
        report = validator.validate_trajectory(states)
        assert report.is_valid

    def test_trajectory_total_energy_delta(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(free_energy=0.0, entropy=0.5),
            ThermodynamicState(free_energy=1e-18, entropy=0.51),
            ThermodynamicState(free_energy=5e-18, entropy=0.52),
        ]
        report = validator.validate_trajectory(states)
        assert report.energy_delta == pytest.approx(5e-18)
        assert report.entropy_delta == pytest.approx(0.02)

    def test_trajectory_max_rate(self) -> None:
        validator = PhysicsValidator()
        states = [
            ThermodynamicState(free_energy=0.0, entropy=0.5),
            ThermodynamicState(free_energy=1e-18, entropy=0.51),
            ThermodynamicState(free_energy=5e-18, entropy=0.52),
        ]
        report = validator.validate_trajectory(states)
        assert report.metrics["max_energy_rate"] > 0


class TestComputeEnergyGradient:
    """Tests for compute_energy_gradient function."""

    def test_gradient_entropy(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        gradients = compute_energy_gradient(state)
        # dG/dS = -T
        assert gradients["entropy"] == pytest.approx(-300.0)

    def test_gradient_temperature(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        gradients = compute_energy_gradient(state)
        # dG/dT = -S
        assert gradients["temperature"] == pytest.approx(-0.5)

    def test_gradient_internal_energy(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        gradients = compute_energy_gradient(state)
        # dG/dU = 1
        assert gradients["internal_energy"] == pytest.approx(1.0)

    def test_numerical_gradient_validation(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        gradients = compute_energy_gradient(state, perturbation=1e-6)
        # Numerical gradient should match analytical
        assert gradients["entropy_numerical"] == pytest.approx(gradients["entropy"], rel=1e-4)

    def test_zero_perturbation_skips_numerical(self) -> None:
        state = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        gradients = compute_energy_gradient(state, perturbation=0.0)
        assert "entropy_numerical" not in gradients


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_constants_exported(self) -> None:
        assert K_BOLTZMANN_EFFECTIVE is not None
        assert SYSTEM_TEMPERATURE_K is not None
        assert ENERGY_SCALE is not None

    def test_temperature_positive(self) -> None:
        assert SYSTEM_TEMPERATURE_K > 0

    def test_energy_scale_positive(self) -> None:
        assert ENERGY_SCALE > 0
