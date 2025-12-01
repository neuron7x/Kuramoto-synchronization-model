# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for core.validation.neuro_integrity module."""
from __future__ import annotations

import numpy as np
import pytest

from core.validation.neuro_integrity import (
    NeuroIntegrity,
    NeuroIntegrityConfig,
    NeuroIntegrityReport,
    PathwayState,
    compute_pathway_correlation,
    compute_phase_coherence,
)


class TestPathwayState:
    """Tests for PathwayState dataclass."""

    def test_basic_creation(self) -> None:
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.6,
            inhibition=0.4,
        )
        assert state.dopamine == 0.5
        assert state.serotonin == 0.4
        assert state.excitation == 0.6
        assert state.inhibition == 0.4

    def test_default_values(self) -> None:
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
        )
        assert state.norepinephrine == 0.5
        assert state.acetylcholine == 0.5
        assert state.gaba == 0.5
        assert state.glutamate == 0.5
        assert state.coherence == 0.5
        assert state.timestamp_ms is None

    def test_validation_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            PathwayState(
                dopamine=1.5,  # Out of [0, 1]
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_validation_negative(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            PathwayState(
                dopamine=-0.1,  # Negative
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_validation_nan(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            PathwayState(
                dopamine=float("nan"),
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_validation_inf(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            PathwayState(
                dopamine=float("inf"),
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_ei_balance_normal(self) -> None:
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.6,
            inhibition=0.3,
        )
        assert state.ei_balance == pytest.approx(2.0)

    def test_ei_balance_zero_inhibition(self) -> None:
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.6,
            inhibition=0.0,
        )
        assert state.ei_balance == float("inf")

    def test_ei_balance_zero_both(self) -> None:
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.0,
            inhibition=0.0,
        )
        assert state.ei_balance == 1.0

    def test_neuromodulator_balance_normal(self) -> None:
        state = PathwayState(
            dopamine=0.6,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
        )
        assert state.neuromodulator_balance == 0.6

    def test_neuromodulator_balance_zero_total(self) -> None:
        state = PathwayState(
            dopamine=0.0,
            serotonin=0.0,
            excitation=0.5,
            inhibition=0.5,
        )
        assert state.neuromodulator_balance == 0.5  # Neutral

    def test_as_mapping(self) -> None:
        state = PathwayState(
            dopamine=0.6,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
        )
        mapping = state.as_mapping()
        assert mapping["dopamine"] == 0.6
        assert mapping["serotonin"] == 0.4
        assert "ei_balance" in mapping
        assert "neuromodulator_balance" in mapping


class TestNeuroIntegrityConfig:
    """Tests for NeuroIntegrityConfig dataclass."""

    def test_default_values(self) -> None:
        config = NeuroIntegrityConfig()
        assert config.min_coherence == 0.1
        assert config.max_ei_imbalance == 5.0
        assert config.max_activation_rate == 2.0
        assert config.min_total_activation == 0.1
        assert config.max_total_activation == 7.0

    def test_custom_values(self) -> None:
        config = NeuroIntegrityConfig(min_coherence=0.2, max_ei_imbalance=3.0)
        assert config.min_coherence == 0.2
        assert config.max_ei_imbalance == 3.0


class TestNeuroIntegrityReport:
    """Tests for NeuroIntegrityReport dataclass."""

    def test_add_violation(self) -> None:
        report = NeuroIntegrityReport(
            is_valid=True,
            ei_balance=1.0,
            coherence=0.5,
            total_activation=4.0,
        )
        report.add_violation("Test violation")
        assert not report.is_valid
        assert len(report.violations) == 1

    def test_add_warning(self) -> None:
        report = NeuroIntegrityReport(
            is_valid=True,
            ei_balance=1.0,
            coherence=0.5,
            total_activation=4.0,
        )
        report.add_warning("Test warning")
        assert report.is_valid  # Warnings don't affect validity
        assert len(report.warnings) == 1


class TestNeuroIntegrity:
    """Tests for NeuroIntegrity validator class."""

    def test_default_initialization(self) -> None:
        validator = NeuroIntegrity()
        assert validator.config.min_coherence == 0.1

    def test_custom_config(self) -> None:
        config = NeuroIntegrityConfig(min_coherence=0.2)
        validator = NeuroIntegrity(config)
        assert validator.config.min_coherence == 0.2


class TestValidateState:
    """Tests for validate_state method."""

    def test_valid_state(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        report = validator.validate_state(state)
        assert report.is_valid
        assert len(report.violations) == 0

    def test_low_coherence_violation(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.05,  # Below min_coherence=0.1
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("Coherence" in v for v in report.violations)

    def test_low_coherence_warning(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.15,  # Above min but below 2*min
        )
        report = validator.validate_state(state)
        assert report.is_valid
        assert any("Low coherence" in w for w in report.warnings)

    def test_high_ei_imbalance(self) -> None:
        config = NeuroIntegrityConfig(max_ei_imbalance=3.0)
        validator = NeuroIntegrity(config)
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.8,
            inhibition=0.2,  # E/I = 4.0 > 3.0
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any(
            "E/I ratio" in v and "excitation dominant" in v for v in report.violations
        )

    def test_low_ei_imbalance(self) -> None:
        config = NeuroIntegrityConfig(max_ei_imbalance=3.0)
        validator = NeuroIntegrity(config)
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.2,
            inhibition=0.8,  # E/I = 0.25 < 1/3
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("inhibition dominant" in v for v in report.violations)

    def test_low_total_activation(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.0,
            serotonin=0.0,
            excitation=0.0,
            inhibition=0.0,
            norepinephrine=0.0,
            acetylcholine=0.0,
            gaba=0.0,
            glutamate=0.0,
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("neural silence" in v for v in report.violations)

    def test_high_total_activation(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=1.0,
            serotonin=1.0,
            excitation=1.0,
            inhibition=1.0,
            norepinephrine=1.0,
            acetylcholine=1.0,
            gaba=1.0,
            glutamate=1.0,  # Total = 8.0 > 7.0
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("runaway activation" in v for v in report.violations)

    def test_gaba_glutamate_imbalance_warning(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            gaba=0.9,
            glutamate=0.1,  # Ratio = 9.0, far from 1.0
        )
        report = validator.validate_state(state)
        assert any("GABA/Glutamate imbalance" in w for w in report.warnings)

    def test_metrics_populated(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        report = validator.validate_state(state)
        assert "dopamine" in report.metrics
        assert "total_activation" in report.metrics
        assert "gaba_glutamate_ratio" in report.metrics


class TestValidateTransition:
    """Tests for validate_transition method."""

    def test_valid_transition(self) -> None:
        validator = NeuroIntegrity()
        state_before = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        state_after = PathwayState(
            dopamine=0.6,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert report.is_valid

    def test_invalid_dt(self) -> None:
        validator = NeuroIntegrity()
        state_before = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        state_after = PathwayState(
            dopamine=0.6, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(state_before, state_after, dt=0)

    def test_rate_limit_violation(self) -> None:
        config = NeuroIntegrityConfig(max_activation_rate=0.5)
        validator = NeuroIntegrity(config)
        state_before = PathwayState(
            dopamine=0.0,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        state_after = PathwayState(
            dopamine=1.0,  # Change of 1.0 in 1s = rate of 1.0 > 0.5
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
        )
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert not report.is_valid
        assert any("change rate" in v for v in report.violations)

    def test_coherence_swing_warning(self) -> None:
        validator = NeuroIntegrity()
        state_before = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.2,
        )
        state_after = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.9,  # Large swing > 0.5
        )
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert any("Large coherence change" in w for w in report.warnings)

    def test_transition_metrics(self) -> None:
        validator = NeuroIntegrity()
        state_before = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        state_after = PathwayState(
            dopamine=0.6, serotonin=0.4, excitation=0.5, inhibition=0.5
        )
        report = validator.validate_transition(state_before, state_after, dt=0.5)
        assert report.metrics["dt"] == 0.5
        assert report.metrics["dopamine_delta"] == pytest.approx(0.1)
        assert report.metrics["serotonin_delta"] == pytest.approx(-0.1)

    def test_inherits_state_violations(self) -> None:
        validator = NeuroIntegrity()
        state_before = PathwayState(
            dopamine=0.5,
            serotonin=0.5,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.05,  # Below minimum
        )
        state_after = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        report = validator.validate_transition(state_before, state_after, dt=1.0)
        assert any("Initial:" in v for v in report.violations)


class TestValidateTrajectory:
    """Tests for validate_trajectory method."""

    def test_empty_trajectory(self) -> None:
        validator = NeuroIntegrity()
        report = validator.validate_trajectory([])
        assert report.is_valid

    def test_single_state_trajectory(self) -> None:
        validator = NeuroIntegrity()
        state = PathwayState(
            dopamine=0.5, serotonin=0.5, excitation=0.5, inhibition=0.5
        )
        report = validator.validate_trajectory([state])
        assert report.is_valid

    def test_valid_trajectory(self) -> None:
        validator = NeuroIntegrity()
        states = [
            PathwayState(
                dopamine=0.5 + i * 0.05,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
            )
            for i in range(5)
        ]
        report = validator.validate_trajectory(states)
        assert report.is_valid
        assert report.metrics["trajectory_length"] == 5

    def test_trajectory_with_timestamps(self) -> None:
        validator = NeuroIntegrity()
        states = [
            PathwayState(
                dopamine=0.5 + i * 0.05,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
            )
            for i in range(3)
        ]
        timestamps = [0.0, 1000.0, 2000.0]  # milliseconds
        report = validator.validate_trajectory(states, timestamps_ms=timestamps)
        assert report.is_valid

    def test_trajectory_with_state_timestamps(self) -> None:
        validator = NeuroIntegrity()
        states = [
            PathwayState(
                dopamine=0.5 + i * 0.05,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
                timestamp_ms=float(i * 1000),
            )
            for i in range(3)
        ]
        report = validator.validate_trajectory(states)
        assert report.is_valid

    def test_trajectory_skips_invalid_dt(self) -> None:
        validator = NeuroIntegrity()
        states = [
            PathwayState(
                dopamine=0.5,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
                timestamp_ms=1000.0,
            ),
            PathwayState(
                dopamine=0.5,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
                timestamp_ms=1000.0,  # Same timestamp, dt=0
            ),
        ]
        report = validator.validate_trajectory(states)
        # Should skip the invalid transition
        assert report.is_valid

    def test_trajectory_metrics(self) -> None:
        validator = NeuroIntegrity()
        states = [
            PathwayState(
                dopamine=0.5,
                serotonin=0.5,
                excitation=0.5,
                inhibition=0.5,
                coherence=0.3 + i * 0.1,
            )
            for i in range(5)
        ]
        report = validator.validate_trajectory(states)
        assert "mean_coherence" in report.metrics
        assert "std_coherence" in report.metrics
        assert "min_coherence" in report.metrics
        assert "max_coherence" in report.metrics


class TestComputePathwayCorrelation:
    """Tests for compute_pathway_correlation function."""

    def test_perfect_positive_correlation(self) -> None:
        dopamine = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        serotonin = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == pytest.approx(1.0)

    def test_perfect_negative_correlation(self) -> None:
        dopamine = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        serotonin = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == pytest.approx(-1.0)

    def test_no_correlation(self) -> None:
        # Constant arrays have no correlation
        dopamine = np.array([0.5, 0.5, 0.5, 0.5])
        serotonin = np.array([0.3, 0.3, 0.3, 0.3])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == 0.0

    def test_unequal_lengths_raises(self) -> None:
        dopamine = np.array([0.1, 0.2, 0.3])
        serotonin = np.array([0.1, 0.2])
        with pytest.raises(ValueError, match="equal length"):
            compute_pathway_correlation(dopamine, serotonin)

    def test_single_element(self) -> None:
        dopamine = np.array([0.5])
        serotonin = np.array([0.3])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == 0.0


class TestComputePhaseCoherence:
    """Tests for compute_phase_coherence function."""

    def test_perfect_sync(self) -> None:
        phases = np.array([0.0, 0.0, 0.0, 0.0])
        coherence = compute_phase_coherence(phases)
        assert coherence == pytest.approx(1.0)

    def test_uniform_distribution(self) -> None:
        # Phases uniformly distributed around the circle
        phases = np.array([0.0, np.pi / 2, np.pi, 3 * np.pi / 2])
        coherence = compute_phase_coherence(phases)
        assert coherence < 0.1  # Nearly zero

    def test_empty_array(self) -> None:
        phases = np.array([])
        coherence = compute_phase_coherence(phases)
        assert coherence == 0.0

    def test_handles_nan(self) -> None:
        phases = np.array([0.0, 0.0, np.nan, 0.0])
        coherence = compute_phase_coherence(phases)
        # Should filter out NaN and compute coherence of remaining
        assert coherence == pytest.approx(1.0)

    def test_all_nan(self) -> None:
        phases = np.array([np.nan, np.nan])
        coherence = compute_phase_coherence(phases)
        assert coherence == 0.0

    def test_partial_sync(self) -> None:
        # Mix of synchronized and offset phases
        phases = np.array([0.0, 0.0, np.pi / 4, np.pi / 4])
        coherence = compute_phase_coherence(phases)
        assert 0.5 < coherence < 1.0
