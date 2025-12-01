# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for core.validation.system_integrator module."""
from __future__ import annotations

import numpy as np
import pytest

from core.validation.neuro_integrity import (
    NeuroIntegrityConfig,
    PathwayState,
)
from core.validation.physics_validator import (
    EnergyBounds,
    ThermodynamicState,
)
from core.validation.system_integrator import (
    SystemHealthLevel,
    SystemIntegrator,
    SystemState,
    SystemValidationConfig,
    SystemValidationReport,
    compute_system_health_score,
)


class TestSystemHealthLevel:
    """Tests for SystemHealthLevel enum."""

    def test_values(self) -> None:
        assert SystemHealthLevel.CRITICAL.value == "critical"
        assert SystemHealthLevel.WARNING.value == "warning"
        assert SystemHealthLevel.HEALTHY.value == "healthy"
        assert SystemHealthLevel.OPTIMAL.value == "optimal"


class TestSystemState:
    """Tests for SystemState dataclass."""

    def test_default_creation(self) -> None:
        state = SystemState()
        assert state.thermodynamic is None
        assert state.pathway is None
        assert state.data is None
        assert state.data_name == "system_data"
        assert state.market_phase == "neutral"
        assert state.timestamp_ms is None

    def test_with_thermodynamic(self) -> None:
        thermo = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        state = SystemState(thermodynamic=thermo)
        assert state.thermodynamic is not None
        assert state.thermodynamic.free_energy == 1e-18

    def test_with_pathway(self) -> None:
        pathway = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        state = SystemState(pathway=pathway)
        assert state.pathway is not None
        assert state.pathway.dopamine == 0.5

    def test_with_data(self) -> None:
        data = np.array([1.0, 2.0, 3.0])
        state = SystemState(data=data, data_name="prices")
        assert state.data is not None
        assert state.data_name == "prices"

    def test_combined_state(self) -> None:
        thermo = ThermodynamicState(free_energy=1e-18, entropy=0.5)
        pathway = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        data = np.array([1.0, 2.0, 3.0])
        state = SystemState(
            thermodynamic=thermo,
            pathway=pathway,
            data=data,
            market_phase="bullish",
            timestamp_ms=1000.0,
        )
        assert state.thermodynamic is not None
        assert state.pathway is not None
        assert state.data is not None
        assert state.market_phase == "bullish"
        assert state.timestamp_ms == 1000.0


class TestSystemValidationConfig:
    """Tests for SystemValidationConfig dataclass."""

    def test_default_values(self) -> None:
        config = SystemValidationConfig()
        assert isinstance(config.energy_bounds, EnergyBounds)
        assert isinstance(config.neuro_config, NeuroIntegrityConfig)
        assert config.data_min_value is None
        assert config.data_max_value is None
        assert config.cross_domain_checks is True

    def test_health_thresholds(self) -> None:
        config = SystemValidationConfig()
        assert config.health_thresholds["critical"] == 0.3
        assert config.health_thresholds["warning"] == 0.6
        assert config.health_thresholds["healthy"] == 0.85

    def test_custom_config(self) -> None:
        custom_bounds = EnergyBounds(min_free_energy=-1e-14)
        custom_neuro = NeuroIntegrityConfig(min_coherence=0.2)
        config = SystemValidationConfig(
            energy_bounds=custom_bounds,
            neuro_config=custom_neuro,
            data_min_value=0.0,
            data_max_value=100.0,
            cross_domain_checks=False,
        )
        assert config.energy_bounds.min_free_energy == -1e-14
        assert config.neuro_config.min_coherence == 0.2
        assert config.data_min_value == 0.0
        assert config.data_max_value == 100.0
        assert config.cross_domain_checks is False


class TestSystemValidationReport:
    """Tests for SystemValidationReport dataclass."""

    def test_default_values(self) -> None:
        report = SystemValidationReport()
        assert report.is_valid
        assert report.health_level == SystemHealthLevel.HEALTHY
        assert report.health_score == 1.0
        assert report.physics_report is None
        assert report.neuro_report is None
        assert report.data_report is None
        assert report.cross_domain_issues == []

    def test_add_cross_domain_issue(self) -> None:
        report = SystemValidationReport()
        report.add_cross_domain_issue("Test issue")
        assert not report.is_valid
        assert len(report.cross_domain_issues) == 1
        assert report.cross_domain_issues[0] == "Test issue"

    def test_summary_basic(self) -> None:
        report = SystemValidationReport()
        summary = report.summary()
        assert "HEALTHY" in summary
        assert "Valid: True" in summary

    def test_summary_with_reports(self) -> None:
        report = SystemValidationReport()
        # Mock physics report
        from core.validation.physics_validator import PhysicsConstraintReport

        report.physics_report = PhysicsConstraintReport(
            is_valid=True, energy_delta=0.0, entropy_delta=0.0, energy_rate=0.0
        )
        summary = report.summary()
        assert "Physics: OK" in summary

    def test_summary_with_cross_domain_issues(self) -> None:
        report = SystemValidationReport()
        report.add_cross_domain_issue("Issue 1")
        report.add_cross_domain_issue("Issue 2")
        summary = report.summary()
        assert "Cross-domain issues: 2" in summary


class TestSystemIntegrator:
    """Tests for SystemIntegrator class."""

    def test_default_initialization(self) -> None:
        integrator = SystemIntegrator()
        assert integrator.config is not None
        assert integrator.physics_validator is not None
        assert integrator.neuro_validator is not None
        assert integrator.math_validator is not None

    def test_custom_config(self) -> None:
        config = SystemValidationConfig(cross_domain_checks=False)
        integrator = SystemIntegrator(config)
        assert integrator.config.cross_domain_checks is False


class TestValidate:
    """Tests for validate method."""

    def test_empty_state(self) -> None:
        integrator = SystemIntegrator()
        state = SystemState()
        report = integrator.validate(state)
        assert report.is_valid
        assert report.health_score == 1.0  # No domains to validate

    def test_physics_only(self) -> None:
        integrator = SystemIntegrator()
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.5)
        state = SystemState(thermodynamic=thermo)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.physics_report is not None
        assert "physics_score" in report.metrics

    def test_neuro_only(self) -> None:
        integrator = SystemIntegrator()
        pathway = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        state = SystemState(pathway=pathway)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.neuro_report is not None
        assert "neuro_score" in report.metrics

    def test_data_only(self) -> None:
        integrator = SystemIntegrator()
        data = np.array([1.0, 2.0, 3.0])
        state = SystemState(data=data)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.data_report is not None
        assert "data_score" in report.metrics

    def test_all_domains(self) -> None:
        integrator = SystemIntegrator()
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.5)
        pathway = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        data = np.array([1.0, 2.0, 3.0])
        state = SystemState(thermodynamic=thermo, pathway=pathway, data=data)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.physics_report is not None
        assert report.neuro_report is not None
        assert report.data_report is not None

    def test_physics_validation_failure(self) -> None:
        bounds = EnergyBounds(max_free_energy=1e-15)
        config = SystemValidationConfig(energy_bounds=bounds, cross_domain_checks=False)
        integrator = SystemIntegrator(config)
        thermo = ThermodynamicState(free_energy=1e-14, entropy=0.5)  # Exceeds max
        state = SystemState(thermodynamic=thermo)
        report = integrator.validate(state)
        assert not report.is_valid
        assert report.physics_report is not None
        assert not report.physics_report.is_valid

    def test_neuro_validation_failure(self) -> None:
        neuro_config = NeuroIntegrityConfig(min_coherence=0.5)
        config = SystemValidationConfig(
            neuro_config=neuro_config, cross_domain_checks=False
        )
        integrator = SystemIntegrator(config)
        pathway = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.1,  # Below minimum
        )
        state = SystemState(pathway=pathway)
        report = integrator.validate(state)
        assert not report.is_valid

    def test_data_validation_with_bounds(self) -> None:
        config = SystemValidationConfig(
            data_min_value=0.0, data_max_value=10.0, cross_domain_checks=False
        )
        integrator = SystemIntegrator(config)
        data = np.array([5.0, 15.0])  # 15 exceeds max
        state = SystemState(data=data)
        report = integrator.validate(state)
        assert not report.is_valid

    def test_warnings_reduce_score(self) -> None:
        integrator = SystemIntegrator()
        bounds = EnergyBounds(min_free_energy=-1e-15, max_free_energy=1e-15)
        config = SystemValidationConfig(energy_bounds=bounds, cross_domain_checks=False)
        integrator = SystemIntegrator(config)
        # Near boundary triggers warning
        thermo = ThermodynamicState(free_energy=0.95e-15, entropy=0.5)
        state = SystemState(thermodynamic=thermo)
        report = integrator.validate(state)
        # Score should be reduced due to warning
        assert report.metrics["physics_score"] < 1.0

    def test_health_level_critical(self) -> None:
        bounds = EnergyBounds(max_free_energy=1e-15)
        config = SystemValidationConfig(
            energy_bounds=bounds,
            health_thresholds={"critical": 0.6, "warning": 0.7, "healthy": 0.9},
            cross_domain_checks=False,
        )
        integrator = SystemIntegrator(config)
        thermo = ThermodynamicState(free_energy=1e-14, entropy=0.5)  # Fails
        state = SystemState(thermodynamic=thermo)
        report = integrator.validate(state)
        # Score is 0.0 (failed physics) which is < 0.6 (critical threshold)
        assert report.health_level == SystemHealthLevel.CRITICAL

    def test_health_level_optimal(self) -> None:
        integrator = SystemIntegrator()
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.5)
        pathway = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        data = np.array([1.0, 2.0, 3.0])
        state = SystemState(thermodynamic=thermo, pathway=pathway, data=data)
        report = integrator.validate(state)
        assert report.health_level == SystemHealthLevel.OPTIMAL

    def test_market_phase_metric(self) -> None:
        integrator = SystemIntegrator()
        state = SystemState(market_phase="bullish")
        report = integrator.validate(state)
        assert report.metrics["market_phase"] == 0.7

    def test_market_phase_unknown(self) -> None:
        integrator = SystemIntegrator()
        state = SystemState(market_phase="unknown_phase")
        report = integrator.validate(state)
        assert report.metrics["market_phase"] == 0.5  # Default

    def test_timestamp_metric(self) -> None:
        integrator = SystemIntegrator()
        state = SystemState(timestamp_ms=12345.0)
        report = integrator.validate(state)
        assert report.metrics["timestamp_ms"] == 12345.0


class TestValidateTransition:
    """Tests for validate_transition method."""

    def test_physics_transition(self) -> None:
        integrator = SystemIntegrator()
        thermo1 = ThermodynamicState(free_energy=0.0, entropy=0.5)
        thermo2 = ThermodynamicState(free_energy=1e-20, entropy=0.51)
        state1 = SystemState(thermodynamic=thermo1)
        state2 = SystemState(thermodynamic=thermo2)
        report = integrator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid
        assert report.physics_report is not None

    def test_neuro_transition(self) -> None:
        integrator = SystemIntegrator()
        pathway1 = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        pathway2 = PathwayState(
            dopamine=0.6, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        state1 = SystemState(pathway=pathway1)
        state2 = SystemState(pathway=pathway2)
        report = integrator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid
        assert report.neuro_report is not None

    def test_data_in_final_state(self) -> None:
        integrator = SystemIntegrator()
        data = np.array([1.0, 2.0, 3.0])
        state1 = SystemState()
        state2 = SystemState(data=data)
        report = integrator.validate_transition(state1, state2, dt=1.0)
        assert report.data_report is not None

    def test_transition_health_levels(self) -> None:
        integrator = SystemIntegrator()
        thermo1 = ThermodynamicState(free_energy=0.0, entropy=0.5)
        thermo2 = ThermodynamicState(free_energy=1e-20, entropy=0.51)
        state1 = SystemState(thermodynamic=thermo1)
        state2 = SystemState(thermodynamic=thermo2)
        report = integrator.validate_transition(state1, state2, dt=1.0)
        assert report.health_level in list(SystemHealthLevel)


class TestCrossDomainConsistency:
    """Tests for cross-domain consistency checks."""

    def test_entropy_variability_mismatch(self) -> None:
        config = SystemValidationConfig(
            cross_domain_checks=True,
            entropy_variability_threshold=0.05,
        )
        integrator = SystemIntegrator(config)
        # High entropy but low data variability
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.8)
        data = np.array([1.0, 1.0, 1.0, 1.0, 1.0])  # Very low CV
        state = SystemState(thermodynamic=thermo, data=data)
        report = integrator.validate(state)
        assert any(
            "Entropy-variability mismatch" in issue
            for issue in report.cross_domain_issues
        )

    def test_neural_energy_mismatch(self) -> None:
        config = SystemValidationConfig(
            cross_domain_checks=True,
            ei_balance_threshold=2.0,
            energy_floor=1e-19,
        )
        integrator = SystemIntegrator(config)
        # High E/I but very low energy
        thermo = ThermodynamicState(free_energy=1e-25, entropy=0.5)
        pathway = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.9,
            inhibition=0.3,  # E/I = 3.0 > threshold
        )
        state = SystemState(thermodynamic=thermo, pathway=pathway)
        report = integrator.validate(state)
        assert any(
            "Neural-energy mismatch" in issue for issue in report.cross_domain_issues
        )

    def test_coherence_quality_mismatch(self) -> None:
        config = SystemValidationConfig(
            cross_domain_checks=True,
            coherence_threshold=0.7,
            nan_ratio_threshold=0.05,
        )
        integrator = SystemIntegrator(config)
        # High coherence but poor data quality
        pathway = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.9,
        )
        data = np.array([1.0, np.nan, np.nan, np.nan, 5.0])  # 60% NaN
        state = SystemState(pathway=pathway, data=data)
        report = integrator.validate(state)
        assert any(
            "Coherence-quality mismatch" in issue
            for issue in report.cross_domain_issues
        )

    def test_no_cross_domain_when_disabled(self) -> None:
        config = SystemValidationConfig(cross_domain_checks=False)
        integrator = SystemIntegrator(config)
        # Same mismatch scenario but disabled
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.8)
        data = np.array([1.0, 1.0, 1.0])
        state = SystemState(thermodynamic=thermo, data=data)
        report = integrator.validate(state)
        assert len(report.cross_domain_issues) == 0

    def test_no_cross_domain_with_zero_mean_data(self) -> None:
        config = SystemValidationConfig(cross_domain_checks=True)
        integrator = SystemIntegrator(config)
        # Data with zero mean - CV is undefined
        thermo = ThermodynamicState(free_energy=0.0, entropy=0.8)
        data = np.array([-1.0, 0.0, 1.0])  # Mean of absolute values is not zero
        state = SystemState(thermodynamic=thermo, data=data)
        report = integrator.validate(state)
        # Should handle gracefully without division by zero
        assert report.is_valid or len(report.cross_domain_issues) > 0


class TestComputeSystemHealthScore:
    """Tests for compute_system_health_score function."""

    def test_all_valid_no_warnings(self) -> None:
        score = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
            physics_warnings=0,
            neuro_warnings=0,
            data_warnings=0,
        )
        assert score == 1.0

    def test_all_invalid(self) -> None:
        score = compute_system_health_score(
            physics_valid=False,
            neuro_valid=False,
            data_valid=False,
        )
        assert score == 0.0

    def test_warnings_reduce_score(self) -> None:
        score = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
            physics_warnings=2,
            neuro_warnings=0,
            data_warnings=0,
        )
        # physics_score = max(0.5, 1.0 - 0.2) = 0.8
        # Mean of [0.8, 1.0, 1.0] = 0.93...
        assert 0.9 <= score < 1.0

    def test_many_warnings_floor_at_half(self) -> None:
        score = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
            physics_warnings=10,  # Would be 0.0 without floor
            neuro_warnings=10,
            data_warnings=10,
        )
        # All scores floored at 0.5
        assert score == pytest.approx(0.5)

    def test_mixed_validity(self) -> None:
        score = compute_system_health_score(
            physics_valid=True,
            neuro_valid=False,  # Invalid
            data_valid=True,
        )
        # [1.0, 0.0, 1.0] -> mean = 0.67
        assert score == pytest.approx(2.0 / 3.0)
