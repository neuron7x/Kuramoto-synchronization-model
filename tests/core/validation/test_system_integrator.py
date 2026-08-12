# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for system_integrator module."""

from __future__ import annotations

import numpy as np
import pytest

from core.validation.neuro_integrity import PathwayState
from core.validation.physics_validator import ThermodynamicState
from core.validation.system_integrator import (
    SystemHealthLevel,
    SystemIntegrator,
    SystemState,
    SystemValidationConfig,
    compute_system_health_score,
)


class TestSystemState:
    """Tests for SystemState dataclass."""

    def test_empty_state(self):
        """Test creating an empty state."""
        state = SystemState()
        assert state.thermodynamic is None
        assert state.pathway is None
        assert state.data is None

    def test_full_state(self):
        """Test creating a fully populated state."""
        state = SystemState(
            thermodynamic=ThermodynamicState(free_energy=1e-18, entropy=0.5),
            pathway=PathwayState(dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5),
            data=np.array([1.0, 2.0, 3.0]),
            market_phase="bullish",
        )
        assert state.thermodynamic is not None
        assert state.pathway is not None
        assert state.data is not None
        assert state.market_phase == "bullish"


class TestSystemIntegrator:
    """Tests for SystemIntegrator."""

    @pytest.fixture
    def integrator(self):
        """Create a default integrator."""
        return SystemIntegrator()

    @pytest.fixture
    def valid_thermodynamic(self):
        """Create a valid thermodynamic state."""
        return ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)

    @pytest.fixture
    def valid_pathway(self):
        """Create a valid pathway state."""
        return PathwayState(
            dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5, coherence=0.6
        )

    @pytest.fixture
    def valid_data(self):
        """Create valid data array."""
        return np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    def test_validate_empty_state(self, integrator):
        """Test validation of empty state."""
        state = SystemState()
        report = integrator.validate(state)
        assert report.is_valid
        assert report.health_score == 1.0
        assert report.health_level == SystemHealthLevel.OPTIMAL

    def test_validate_thermodynamic_only(self, integrator, valid_thermodynamic):
        """Test validation with only thermodynamic state."""
        state = SystemState(thermodynamic=valid_thermodynamic)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.physics_report is not None
        assert report.physics_report.is_valid
        assert report.health_level in [
            SystemHealthLevel.HEALTHY,
            SystemHealthLevel.OPTIMAL,
        ]

    def test_validate_pathway_only(self, integrator, valid_pathway):
        """Test validation with only pathway state."""
        state = SystemState(pathway=valid_pathway)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.neuro_report is not None
        assert report.neuro_report.is_valid

    def test_validate_data_only(self, integrator, valid_data):
        """Test validation with only data."""
        state = SystemState(data=valid_data)
        report = integrator.validate(state)
        assert report.is_valid
        assert report.data_report is not None
        assert report.data_report.is_valid

    def test_validate_full_state(self, integrator, valid_thermodynamic, valid_pathway, valid_data):
        """Test validation of fully populated state."""
        state = SystemState(
            thermodynamic=valid_thermodynamic,
            pathway=valid_pathway,
            data=valid_data,
        )
        report = integrator.validate(state)
        assert report.is_valid
        assert report.physics_report is not None
        assert report.neuro_report is not None
        assert report.data_report is not None
        assert report.health_score > 0.8

    def test_validate_invalid_physics(self, integrator, valid_pathway, valid_data):
        """Test validation with invalid physics state."""
        # Create invalid thermodynamic state (energy below bounds)
        invalid_thermo = ThermodynamicState(
            free_energy=-1e-14,  # Below default minimum
            entropy=0.5,
        )
        state = SystemState(
            thermodynamic=invalid_thermo,
            pathway=valid_pathway,
            data=valid_data,
        )
        report = integrator.validate(state)
        assert not report.is_valid
        assert not report.physics_report.is_valid

    def test_validate_invalid_neuro(self, integrator, valid_thermodynamic, valid_data):
        """Test validation with invalid neural state."""
        # Create invalid pathway state (low coherence)
        invalid_pathway = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.05,  # Below minimum
        )
        state = SystemState(
            thermodynamic=valid_thermodynamic,
            pathway=invalid_pathway,
            data=valid_data,
        )
        report = integrator.validate(state)
        assert not report.is_valid
        assert not report.neuro_report.is_valid

    def test_validate_invalid_data(self, integrator, valid_thermodynamic, valid_pathway):
        """Test validation with invalid data."""
        # Create data with NaN values
        invalid_data = np.array([1.0, float("nan"), 3.0])
        state = SystemState(
            thermodynamic=valid_thermodynamic,
            pathway=valid_pathway,
            data=invalid_data,
        )
        report = integrator.validate(state)
        assert not report.is_valid
        assert not report.data_report.is_valid

    def test_health_level_critical(self, integrator):
        """Test critical health level detection."""
        # All invalid states
        state = SystemState(
            thermodynamic=ThermodynamicState(free_energy=-1e-14, entropy=0.5),
            pathway=PathwayState(
                dopamine=0.5,
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
                coherence=0.05,
            ),
            data=np.array([float("nan")]),
        )
        report = integrator.validate(state)
        assert report.health_level == SystemHealthLevel.CRITICAL

    def test_validate_transition(self, integrator):
        """Test transition validation."""
        state1 = SystemState(
            thermodynamic=ThermodynamicState(free_energy=1e-18, entropy=0.5),
            pathway=PathwayState(dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5),
        )
        state2 = SystemState(
            thermodynamic=ThermodynamicState(free_energy=0.99e-18, entropy=0.51),
            pathway=PathwayState(dopamine=0.52, serotonin=0.42, excitation=0.51, inhibition=0.49),
        )
        report = integrator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid

    def test_cross_domain_entropy_check(self, integrator):
        """Test cross-domain entropy consistency check."""
        # High entropy but low variability data
        state = SystemState(
            thermodynamic=ThermodynamicState(free_energy=1e-18, entropy=0.9),
            data=np.array([1.0, 1.0, 1.0, 1.0, 1.0]),  # No variability
        )
        report = integrator.validate(state)
        # Should detect mismatch
        assert len(report.cross_domain_issues) > 0

    def test_summary_generation(self, integrator, valid_thermodynamic, valid_pathway, valid_data):
        """Test report summary generation."""
        state = SystemState(
            thermodynamic=valid_thermodynamic,
            pathway=valid_pathway,
            data=valid_data,
        )
        report = integrator.validate(state)
        summary = report.summary()
        assert "Health" in summary
        assert "Physics" in summary
        assert "Neuro" in summary
        assert "Data" in summary

    def test_custom_config(self):
        """Test integrator with custom configuration."""
        config = SystemValidationConfig(
            data_min_value=0.0,
            data_max_value=100.0,
        )
        integrator = SystemIntegrator(config)
        state = SystemState(data=np.array([50.0, 60.0, 70.0]))
        report = integrator.validate(state)
        assert report.is_valid


class TestComputeSystemHealthScore:
    """Tests for compute_system_health_score function."""

    def test_all_valid_no_warnings(self):
        """Test score with all valid and no warnings."""
        score = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
        )
        assert score == 1.0

    def test_one_invalid(self):
        """Test score with one invalid domain."""
        score = compute_system_health_score(
            physics_valid=False,
            neuro_valid=True,
            data_valid=True,
        )
        assert score == pytest.approx(2 / 3)

    def test_all_invalid(self):
        """Test score with all invalid."""
        score = compute_system_health_score(
            physics_valid=False,
            neuro_valid=False,
            data_valid=False,
        )
        assert score == 0.0

    def test_warnings_reduce_score(self):
        """Test that warnings reduce score."""
        score_no_warnings = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
        )
        score_with_warnings = compute_system_health_score(
            physics_valid=True,
            neuro_valid=True,
            data_valid=True,
            physics_warnings=2,
            neuro_warnings=1,
        )
        assert score_with_warnings < score_no_warnings
