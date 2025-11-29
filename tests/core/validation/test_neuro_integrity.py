"""Tests for neuro_integrity module."""

from __future__ import annotations

import numpy as np
import pytest

from core.validation.neuro_integrity import (
    NeuroIntegrity,
    NeuroIntegrityConfig,
    PathwayState,
    compute_pathway_correlation,
    compute_phase_coherence,
)


class TestPathwayState:
    """Tests for PathwayState dataclass."""

    def test_basic_construction(self):
        """Test basic state construction."""
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

    def test_default_values(self):
        """Test default neurotransmitter values."""
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.6,
            inhibition=0.4,
        )
        assert state.norepinephrine == 0.5
        assert state.acetylcholine == 0.5
        assert state.gaba == 0.5
        assert state.glutamate == 0.5
        assert state.coherence == 0.5

    def test_ei_balance_calculation(self):
        """Test E/I balance calculation."""
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.6,
            inhibition=0.3,
        )
        assert state.ei_balance == pytest.approx(2.0)

    def test_ei_balance_zero_inhibition(self):
        """Test E/I balance with zero inhibition."""
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.6,
            inhibition=0.0,
        )
        assert state.ei_balance == float("inf")

    def test_neuromodulator_balance(self):
        """Test dopamine/serotonin balance calculation."""
        state = PathwayState(
            dopamine=0.6,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
        )
        # 0.6 / (0.6 + 0.4) = 0.6
        assert state.neuromodulator_balance == pytest.approx(0.6)

    def test_invalid_value_below_zero(self):
        """Test that values below 0 raise ValueError."""
        with pytest.raises(ValueError, match="must be in"):
            PathwayState(
                dopamine=-0.1,
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_invalid_value_above_one(self):
        """Test that values above 1 raise ValueError."""
        with pytest.raises(ValueError, match="must be in"):
            PathwayState(
                dopamine=1.5,
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_invalid_nan(self):
        """Test that NaN values raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            PathwayState(
                dopamine=float("nan"),
                serotonin=0.4,
                excitation=0.5,
                inhibition=0.5,
            )

    def test_as_mapping(self):
        """Test conversion to dictionary."""
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.6,
            inhibition=0.4,
        )
        mapping = state.as_mapping()
        assert "dopamine" in mapping
        assert "serotonin" in mapping
        assert "ei_balance" in mapping
        assert "neuromodulator_balance" in mapping


class TestNeuroIntegrityConfig:
    """Tests for NeuroIntegrityConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = NeuroIntegrityConfig()
        assert config.min_coherence > 0
        assert config.max_ei_imbalance > 1
        assert config.max_activation_rate > 0

    def test_custom_config(self):
        """Test custom configuration."""
        config = NeuroIntegrityConfig(
            min_coherence=0.2,
            max_ei_imbalance=3.0,
        )
        assert config.min_coherence == 0.2
        assert config.max_ei_imbalance == 3.0


class TestNeuroIntegrity:
    """Tests for NeuroIntegrity validator."""

    @pytest.fixture
    def validator(self):
        """Create a default validator."""
        return NeuroIntegrity()

    @pytest.fixture
    def valid_state(self):
        """Create a valid pathway state."""
        return PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.5,
        )

    def test_validate_valid_state(self, validator, valid_state):
        """Test validation of a valid state."""
        report = validator.validate_state(valid_state)
        assert report.is_valid
        assert len(report.violations) == 0

    def test_validate_low_coherence(self, validator):
        """Test detection of low coherence."""
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.5,
            inhibition=0.5,
            coherence=0.05,  # Below minimum
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("Coherence" in v for v in report.violations)

    def test_validate_high_ei_imbalance(self):
        """Test detection of high E/I imbalance."""
        config = NeuroIntegrityConfig(max_ei_imbalance=2.0)
        validator = NeuroIntegrity(config)
        state = PathwayState(
            dopamine=0.5,
            serotonin=0.4,
            excitation=0.9,
            inhibition=0.1,  # E/I = 9.0, exceeds 2.0
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("E/I ratio" in v for v in report.violations)

    def test_validate_low_total_activation(self):
        """Test detection of neural silence."""
        config = NeuroIntegrityConfig(min_total_activation=1.0)
        validator = NeuroIntegrity(config)
        state = PathwayState(
            dopamine=0.01,
            serotonin=0.01,
            excitation=0.01,
            inhibition=0.01,
            norepinephrine=0.01,
            acetylcholine=0.01,
            gaba=0.01,
            glutamate=0.01,
        )
        report = validator.validate_state(state)
        assert not report.is_valid
        assert any("neural silence" in v for v in report.violations)

    def test_validate_valid_transition(self, validator):
        """Test validation of a valid transition."""
        state1 = PathwayState(
            dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5
        )
        state2 = PathwayState(
            dopamine=0.55, serotonin=0.45, excitation=0.52, inhibition=0.48
        )
        report = validator.validate_transition(state1, state2, dt=1.0)
        assert report.is_valid

    def test_validate_excessive_rate(self):
        """Test detection of excessive activation rate."""
        config = NeuroIntegrityConfig(max_activation_rate=0.1)
        validator = NeuroIntegrity(config)
        state1 = PathwayState(
            dopamine=0.2, serotonin=0.4, excitation=0.5, inhibition=0.5
        )
        state2 = PathwayState(
            dopamine=0.8, serotonin=0.4, excitation=0.5, inhibition=0.5
        )  # dopamine changed by 0.6 in 1s
        report = validator.validate_transition(state1, state2, dt=1.0)
        assert not report.is_valid
        assert any("rate" in v.lower() for v in report.violations)

    def test_validate_zero_dt_raises(self, validator, valid_state):
        """Test that zero time delta raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            validator.validate_transition(valid_state, valid_state, dt=0.0)

    def test_validate_trajectory(self, validator):
        """Test trajectory validation."""
        states = [
            PathwayState(dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5),
            PathwayState(
                dopamine=0.52, serotonin=0.42, excitation=0.51, inhibition=0.49
            ),
            PathwayState(
                dopamine=0.54, serotonin=0.44, excitation=0.52, inhibition=0.48
            ),
        ]
        timestamps = [0.0, 1000.0, 2000.0]
        report = validator.validate_trajectory(states, timestamps)
        assert report.is_valid

    def test_validate_empty_trajectory(self, validator):
        """Test empty trajectory validation."""
        report = validator.validate_trajectory([])
        assert report.is_valid


class TestComputePathwayCorrelation:
    """Tests for compute_pathway_correlation function."""

    def test_perfect_positive_correlation(self):
        """Test perfect positive correlation."""
        dopamine = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        serotonin = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        """Test perfect negative correlation."""
        dopamine = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        serotonin = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == pytest.approx(-1.0)

    def test_uncorrelated(self):
        """Test uncorrelated series."""
        np.random.seed(42)
        dopamine = np.random.rand(100)
        serotonin = np.random.rand(100)
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert -0.3 < corr < 0.3  # Should be near zero

    def test_constant_series(self):
        """Test constant series returns zero correlation."""
        dopamine = np.array([0.5, 0.5, 0.5, 0.5])
        serotonin = np.array([0.3, 0.4, 0.5, 0.6])
        corr = compute_pathway_correlation(dopamine, serotonin)
        assert corr == 0.0

    def test_length_mismatch_raises(self):
        """Test that mismatched lengths raise ValueError."""
        with pytest.raises(ValueError, match="equal length"):
            compute_pathway_correlation(
                np.array([0.1, 0.2, 0.3]),
                np.array([0.1, 0.2]),
            )


class TestComputePhaseCoherence:
    """Tests for compute_phase_coherence function."""

    def test_perfect_synchrony(self):
        """Test perfect phase synchrony."""
        phases = np.array([0.0, 0.0, 0.0, 0.0])
        coherence = compute_phase_coherence(phases)
        assert coherence == pytest.approx(1.0)

    def test_perfect_desynchrony(self):
        """Test perfectly distributed phases."""
        phases = np.linspace(0, 2 * np.pi, 5)[:-1]  # 4 evenly spaced phases
        coherence = compute_phase_coherence(phases)
        assert coherence < 0.1  # Should be near zero

    def test_partial_synchrony(self):
        """Test partial phase synchrony."""
        phases = np.array([0.0, 0.1, 0.0, 0.1])
        coherence = compute_phase_coherence(phases)
        assert 0.9 < coherence < 1.0

    def test_empty_array(self):
        """Test empty array returns zero."""
        coherence = compute_phase_coherence(np.array([]))
        assert coherence == 0.0

    def test_handles_nan(self):
        """Test that NaN values are filtered."""
        phases = np.array([0.0, 0.0, float("nan"), 0.0])
        coherence = compute_phase_coherence(phases)
        assert coherence == pytest.approx(1.0)
