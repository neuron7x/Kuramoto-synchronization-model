"""Unit tests for neuroadaptive types and configuration."""

import pytest

from core.neuroadaptive import (
    ControlSignal,
    DecisionRequest,
    NeuroAdaptiveConfig,
    NeuroGateState,
    NeuroSignals,
)


class TestNeuroSignals:
    """Tests for NeuroSignals dataclass."""

    def test_neuro_signals_creation(self):
        """Test creating NeuroSignals with default values."""
        signals = NeuroSignals()
        assert signals.dopamine_rpe is None
        assert signals.serotonin_veto is None
        assert signals.threat_score is None
        assert signals.energy_efficiency is None
        assert signals.prior_confidence is None

    def test_neuro_signals_with_values(self):
        """Test creating NeuroSignals with specific values."""
        signals = NeuroSignals(
            dopamine_rpe=0.5,
            serotonin_veto=0.3,
            threat_score=0.2,
            energy_efficiency=0.8,
            prior_confidence=0.7,
        )
        assert signals.dopamine_rpe == 0.5
        assert signals.serotonin_veto == 0.3
        assert signals.threat_score == 0.2
        assert signals.energy_efficiency == 0.8
        assert signals.prior_confidence == 0.7

    def test_from_mapping(self):
        """Test creating NeuroSignals from a mapping."""
        data = {
            "dopamine_rpe": 0.5,
            "serotonin_veto": 0.3,
            "threat_score": 0.2,
        }
        signals = NeuroSignals.from_mapping(data)
        assert signals.dopamine_rpe == 0.5
        assert signals.serotonin_veto == 0.3
        assert signals.threat_score == 0.2
        assert signals.energy_efficiency is None
        assert signals.prior_confidence is None

    def test_as_dict(self):
        """Test converting NeuroSignals to dictionary."""
        signals = NeuroSignals(
            dopamine_rpe=0.5,
            serotonin_veto=0.3,
        )
        d = signals.as_dict()
        assert d["dopamine_rpe"] == 0.5
        assert d["serotonin_veto"] == 0.3
        assert d["threat_score"] is None
        assert d["energy_efficiency"] is None
        assert d["prior_confidence"] is None


class TestDecisionRequest:
    """Tests for DecisionRequest dataclass."""

    def test_decision_request_creation(self):
        """Test creating DecisionRequest with required fields."""
        signals = NeuroSignals(dopamine_rpe=0.5)
        req = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
        )
        assert req.raw_proposal == {"action": "buy"}
        assert req.neuro_signals == signals
        assert req.risk_tag == "medium"
        assert req.metadata is None

    def test_decision_request_with_risk_and_metadata(self):
        """Test DecisionRequest with custom risk and metadata."""
        signals = NeuroSignals()
        req = DecisionRequest(
            raw_proposal="test",
            neuro_signals=signals,
            risk_tag="high",
            metadata={"source": "strategy_a"},
        )
        assert req.risk_tag == "high"
        assert req.metadata == {"source": "strategy_a"}


class TestNeuroAdaptiveConfig:
    """Tests for NeuroAdaptiveConfig validation."""

    def test_default_config_validation(self):
        """Test that default config passes validation."""
        config = NeuroAdaptiveConfig()
        validated = config.validated()
        assert validated is config

    def test_weights_sum_validation(self):
        """Test that weights must sum to 1.0."""
        config = NeuroAdaptiveConfig(
            weights={
                "dopamine_rpe": 0.5,
                "serotonin_veto": 0.3,
            }
        )
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            config.validated()

    def test_ema_alpha_validation(self):
        """Test EMA alpha parameter validation."""
        config = NeuroAdaptiveConfig(ema_alpha=0.0)
        with pytest.raises(ValueError, match="ema_alpha must be in"):
            config.validated()

        config = NeuroAdaptiveConfig(ema_alpha=1.5)
        with pytest.raises(ValueError, match="ema_alpha must be in"):
            config.validated()

    def test_blend_ratio_validation(self):
        """Test blend ratio parameter validation."""
        config = NeuroAdaptiveConfig(blend_ratio=-0.1)
        with pytest.raises(ValueError, match="blend_ratio must be in"):
            config.validated()

        config = NeuroAdaptiveConfig(blend_ratio=1.5)
        with pytest.raises(ValueError, match="blend_ratio must be in"):
            config.validated()

    def test_invalid_range_validation(self):
        """Test range validation (low must be less than high)."""
        config = NeuroAdaptiveConfig(
            ranges={
                "dopamine_rpe": (1.0, -1.0),  # Invalid: low > high
            }
        )
        with pytest.raises(ValueError, match="invalid range"):
            config.validated()

    def test_missing_gate_threshold(self):
        """Test that all required gate thresholds must be present."""
        config = NeuroAdaptiveConfig(
            gate_thresholds={
                "hard_block": 0.2,
                "soft_block": 0.4,
                # Missing soft_allow and hard_allow
            }
        )
        with pytest.raises(ValueError, match="missing gate_thresholds"):
            config.validated()


class TestEnums:
    """Tests for enum types."""

    def test_neuro_gate_state_values(self):
        """Test NeuroGateState enum values."""
        assert NeuroGateState.REFLEX
        assert NeuroGateState.INHIBITED
        assert NeuroGateState.ARMED
        assert NeuroGateState.RELEASED
        assert NeuroGateState.OVERRIDDEN

    def test_control_signal_values(self):
        """Test ControlSignal enum values."""
        assert ControlSignal.INHIBIT
        assert ControlSignal.ARM
        assert ControlSignal.RELEASE
        assert ControlSignal.RESET
        assert ControlSignal.OVERRIDE_ALLOW
        assert ControlSignal.OVERRIDE_BLOCK
