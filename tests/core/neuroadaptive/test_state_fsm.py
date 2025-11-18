"""Unit tests for neuroadaptive FSM state management."""

import pytest

from core.neuroadaptive import (
    ControlSignal,
    NeuroAdaptiveConfig,
    NeuroGateFsm,
    NeuroGateState,
)


class TestNeuroGateFsm:
    """Tests for NeuroGateFsm finite state machine."""

    @pytest.fixture
    def config(self):
        """Create default config for testing."""
        return NeuroAdaptiveConfig().validated()

    @pytest.fixture
    def fsm(self, config):
        """Create FSM instance for testing."""
        return NeuroGateFsm(config)

    def test_initial_state(self, fsm):
        """Test FSM starts in REFLEX state."""
        assert fsm.state == NeuroGateState.REFLEX

    def test_hard_reset(self, fsm):
        """Test hard reset returns to REFLEX state."""
        # Move to a different state
        fsm.step(neuro_confidence=0.1, risk_tag="medium")
        assert fsm.state != NeuroGateState.REFLEX

        # Reset should return to REFLEX
        fsm.hard_reset()
        assert fsm.state == NeuroGateState.REFLEX

    def test_hard_block_transition(self, fsm):
        """Test transition to INHIBITED on hard block."""
        # Confidence at or below hard_block (0.2) should inhibit
        transition = fsm.step(neuro_confidence=0.1, risk_tag="medium")
        assert transition.new_state == NeuroGateState.INHIBITED
        assert transition.control_signal == ControlSignal.INHIBIT
        assert fsm.state == NeuroGateState.INHIBITED

    def test_soft_block_transition(self, fsm):
        """Test transition to ARMED on soft block."""
        # Confidence between hard_block (0.2) and soft_block (0.4)
        transition = fsm.step(neuro_confidence=0.3, risk_tag="medium")
        assert transition.new_state == NeuroGateState.ARMED
        assert transition.control_signal == ControlSignal.ARM
        assert fsm.state == NeuroGateState.ARMED

    def test_hard_allow_transition(self, fsm):
        """Test transition to RELEASED on hard allow."""
        # Confidence at or above hard_allow (0.8) with non-critical risk
        transition = fsm.step(neuro_confidence=0.9, risk_tag="medium")
        assert transition.new_state == NeuroGateState.RELEASED
        assert transition.control_signal == ControlSignal.RELEASE
        assert fsm.state == NeuroGateState.RELEASED

    def test_hard_allow_critical_risk(self, fsm):
        """Test hard allow with critical risk still requires ARMED."""
        # Even high confidence with critical risk should ARM
        transition = fsm.step(neuro_confidence=0.9, risk_tag="critical")
        assert transition.new_state == NeuroGateState.ARMED
        assert transition.control_signal == ControlSignal.ARM
        assert "critical risk" in transition.reason.lower()

    def test_soft_allow_low_risk(self, fsm):
        """Test soft allow with low risk allows release."""
        # Confidence between soft_allow (0.6) and hard_allow (0.8)
        transition = fsm.step(neuro_confidence=0.7, risk_tag="low")
        assert transition.new_state == NeuroGateState.RELEASED
        assert transition.control_signal == ControlSignal.RELEASE

    def test_soft_allow_high_risk(self, fsm):
        """Test soft allow with high risk requires ARMED."""
        # Same confidence with high risk should ARM
        transition = fsm.step(neuro_confidence=0.7, risk_tag="high")
        assert transition.new_state == NeuroGateState.ARMED
        assert transition.control_signal == ControlSignal.ARM

    def test_inhibited_stays_inhibited(self, fsm):
        """Test INHIBITED state persists until override."""
        # First transition to INHIBITED
        fsm.step(neuro_confidence=0.1, risk_tag="medium")
        assert fsm.state == NeuroGateState.INHIBITED

        # Another step should stay inhibited
        transition = fsm.step(neuro_confidence=0.5, risk_tag="medium")
        assert transition.new_state == NeuroGateState.INHIBITED
        assert transition.control_signal is None
        assert "stay until override" in transition.reason.lower()

    def test_confidence_clamping(self, fsm):
        """Test that confidence values are clamped to [0, 1]."""
        # Test with confidence > 1.0
        transition = fsm.step(neuro_confidence=1.5, risk_tag="low")
        # Should be treated as 1.0, which is above hard_allow
        assert transition.new_state == NeuroGateState.RELEASED

        # Reset and test with confidence < 0.0
        fsm.hard_reset()
        transition = fsm.step(neuro_confidence=-0.5, risk_tag="low")
        # Should be treated as 0.0, which is below hard_block
        assert transition.new_state == NeuroGateState.INHIBITED

    def test_external_reset_signal(self, fsm):
        """Test applying external RESET signal."""
        # Move to a different state
        fsm.step(neuro_confidence=0.1, risk_tag="medium")
        assert fsm.state != NeuroGateState.REFLEX

        # Apply RESET
        transition = fsm.apply_external_signal(ControlSignal.RESET)
        assert transition.new_state == NeuroGateState.REFLEX
        assert transition.control_signal == ControlSignal.RESET
        assert fsm.state == NeuroGateState.REFLEX

    def test_external_override_allow(self, fsm):
        """Test applying OVERRIDE_ALLOW signal."""
        transition = fsm.apply_external_signal(ControlSignal.OVERRIDE_ALLOW)
        assert transition.new_state == NeuroGateState.OVERRIDDEN
        assert transition.control_signal == ControlSignal.OVERRIDE_ALLOW
        assert fsm.state == NeuroGateState.OVERRIDDEN

    def test_external_override_block(self, fsm):
        """Test applying OVERRIDE_BLOCK signal."""
        transition = fsm.apply_external_signal(ControlSignal.OVERRIDE_BLOCK)
        assert transition.new_state == NeuroGateState.OVERRIDDEN
        assert transition.control_signal == ControlSignal.OVERRIDE_BLOCK
        assert fsm.state == NeuroGateState.OVERRIDDEN

    def test_external_soft_signals(self, fsm):
        """Test applying soft control signals (INHIBIT, ARM, RELEASE)."""
        # Test INHIBIT
        transition = fsm.apply_external_signal(ControlSignal.INHIBIT)
        assert transition.new_state == NeuroGateState.INHIBITED
        assert transition.control_signal == ControlSignal.INHIBIT

        # Test ARM
        transition = fsm.apply_external_signal(ControlSignal.ARM)
        assert transition.new_state == NeuroGateState.ARMED
        assert transition.control_signal == ControlSignal.ARM

        # Test RELEASE
        transition = fsm.apply_external_signal(ControlSignal.RELEASE)
        assert transition.new_state == NeuroGateState.RELEASED
        assert transition.control_signal == ControlSignal.RELEASE
