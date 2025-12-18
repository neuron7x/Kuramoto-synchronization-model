# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive tests for FailSafe Controller.

These tests cover:
- All fail-safe levels and transitions
- Auto-recovery mechanism
- Stress reporting and escalation
- Action management
- Edge cases and negative tests
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.risk_monitoring.fail_safe import (
    FailSafeAction,
    FailSafeConfig,
    FailSafeController,
    FailSafeLevel,
    FailSafeState,
)


class TestFailSafeLevelComparison:
    """Tests for FailSafeLevel enum comparison operators."""

    def test_level_ordering(self) -> None:
        """Test that levels are ordered by severity."""
        assert FailSafeLevel.NORMAL < FailSafeLevel.CAUTION
        assert FailSafeLevel.CAUTION < FailSafeLevel.RESTRICTED
        assert FailSafeLevel.RESTRICTED < FailSafeLevel.HALT
        assert FailSafeLevel.HALT < FailSafeLevel.EMERGENCY

    def test_level_le_operator(self) -> None:
        """Test less-than-or-equal operator."""
        assert FailSafeLevel.NORMAL <= FailSafeLevel.NORMAL
        assert FailSafeLevel.NORMAL <= FailSafeLevel.CAUTION
        assert not FailSafeLevel.CAUTION <= FailSafeLevel.NORMAL

    def test_level_gt_operator(self) -> None:
        """Test greater-than operator."""
        assert FailSafeLevel.EMERGENCY > FailSafeLevel.HALT
        assert FailSafeLevel.HALT > FailSafeLevel.RESTRICTED
        assert not FailSafeLevel.NORMAL > FailSafeLevel.CAUTION

    def test_level_ge_operator(self) -> None:
        """Test greater-than-or-equal operator."""
        assert FailSafeLevel.HALT >= FailSafeLevel.HALT
        assert FailSafeLevel.EMERGENCY >= FailSafeLevel.NORMAL
        assert not FailSafeLevel.NORMAL >= FailSafeLevel.CAUTION

    def test_comparison_with_non_level_returns_not_implemented(self) -> None:
        """Test that comparison with non-FailSafeLevel returns NotImplemented."""
        level = FailSafeLevel.NORMAL

        # These should not raise but return NotImplemented
        assert level.__lt__("string") is NotImplemented
        assert level.__le__(123) is NotImplemented
        assert level.__gt__(None) is NotImplemented
        assert level.__ge__([]) is NotImplemented


class TestFailSafeConfig:
    """Tests for FailSafeConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = FailSafeConfig()

        assert config.caution_position_multiplier == 0.7
        assert config.restricted_position_multiplier == 0.3
        assert config.auto_recover_delay_minutes == 30
        assert config.escalation_threshold_seconds == 60
        assert config.enable_emergency_liquidation is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = FailSafeConfig(
            caution_position_multiplier=0.5,
            restricted_position_multiplier=0.1,
            auto_recover_delay_minutes=60,
            escalation_threshold_seconds=120,
            enable_emergency_liquidation=False,
        )

        assert config.caution_position_multiplier == 0.5
        assert config.restricted_position_multiplier == 0.1
        assert config.auto_recover_delay_minutes == 60
        assert config.enable_emergency_liquidation is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        config = FailSafeConfig()
        d = config.to_dict()

        assert "caution_position_multiplier" in d
        assert "restricted_position_multiplier" in d
        assert "auto_recover_delay_minutes" in d
        assert d["require_manual_recovery_levels"] == ["halt", "emergency"]


class TestFailSafeState:
    """Tests for FailSafeState dataclass."""

    def test_default_state(self) -> None:
        """Test default state values."""
        state = FailSafeState()

        assert state.level == FailSafeLevel.NORMAL
        assert state.active is False
        assert state.reason == ""
        assert state.position_multiplier == 1.0
        assert state.allow_new_orders is True
        assert state.force_paper_trading is False
        assert state.pending_actions == ()

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        state = FailSafeState(
            level=FailSafeLevel.CAUTION,
            active=True,
            reason="Test reason",
            activated_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            source="test",
            position_multiplier=0.7,
            pending_actions=(FailSafeAction.REDUCE_POSITIONS,),
        )

        d = state.to_dict()

        assert d["level"] == "caution"
        assert d["active"] is True
        assert d["reason"] == "Test reason"
        assert d["position_multiplier"] == 0.7
        assert "reduce_positions" in d["pending_actions"]


class TestFailSafeControllerBasic:
    """Basic tests for FailSafeController."""

    def test_initialization(self) -> None:
        """Test controller initialization."""
        controller = FailSafeController()
        state = controller.get_state()

        assert state.level == FailSafeLevel.NORMAL
        assert state.active is False
        assert controller.is_trading_allowed() is True
        assert controller.is_new_orders_allowed() is True
        assert controller.get_position_multiplier() == 1.0

    def test_initialization_with_config(self) -> None:
        """Test initialization with custom config."""
        config = FailSafeConfig(caution_position_multiplier=0.5)
        controller = FailSafeController(config=config)

        assert controller.config.caution_position_multiplier == 0.5

    def test_initialization_with_callback(self) -> None:
        """Test initialization with state change callback."""
        callback_states: list[FailSafeState] = []

        def on_change(state: FailSafeState) -> None:
            callback_states.append(state)

        controller = FailSafeController(on_state_change=on_change)
        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        assert len(callback_states) == 1
        assert callback_states[0].level == FailSafeLevel.CAUTION

    def test_callback_exception_handled(self) -> None:
        """Test that callback exceptions are handled gracefully."""
        def bad_callback(state: FailSafeState) -> None:
            raise ValueError("Callback error")

        controller = FailSafeController(on_state_change=bad_callback)

        # Should not raise
        state = controller.escalate_to(FailSafeLevel.CAUTION, "Test")
        assert state.level == FailSafeLevel.CAUTION


class TestFailSafeControllerEscalation:
    """Tests for escalation behavior."""

    def test_escalate_to_caution(self) -> None:
        """Test escalation to CAUTION level."""
        controller = FailSafeController()
        state = controller.escalate_to(FailSafeLevel.CAUTION, "High volatility")

        assert state.level == FailSafeLevel.CAUTION
        assert state.active is True
        assert state.position_multiplier < 1.0
        assert state.allow_new_orders is True
        assert state.force_paper_trading is True
        assert FailSafeAction.REDUCE_POSITIONS in state.pending_actions

    def test_escalate_to_restricted(self) -> None:
        """Test escalation to RESTRICTED level."""
        controller = FailSafeController()
        state = controller.escalate_to(FailSafeLevel.RESTRICTED, "Market stress")

        assert state.level == FailSafeLevel.RESTRICTED
        assert state.allow_new_orders is False
        assert FailSafeAction.CANCEL_PENDING in state.pending_actions

    def test_escalate_to_halt(self) -> None:
        """Test escalation to HALT level."""
        controller = FailSafeController()
        state = controller.escalate_to(FailSafeLevel.HALT, "Critical issue")

        assert state.level == FailSafeLevel.HALT
        assert state.position_multiplier == 0.0
        assert controller.is_trading_allowed() is False
        assert FailSafeAction.HALT_TRADING in state.pending_actions

    def test_escalate_to_emergency(self) -> None:
        """Test escalation to EMERGENCY level."""
        controller = FailSafeController()
        state = controller.escalate_to(FailSafeLevel.EMERGENCY, "System failure")

        assert state.level == FailSafeLevel.EMERGENCY
        assert FailSafeAction.EMERGENCY_LIQUIDATION in state.pending_actions

    def test_escalation_to_lower_level_ignored(self) -> None:
        """Test that escalation to lower level is ignored."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.RESTRICTED, "Initial")

        # Try to escalate to lower level
        state = controller.escalate_to(FailSafeLevel.CAUTION, "Downgrade")

        assert state.level == FailSafeLevel.RESTRICTED

    def test_kill_switch_activates_halt(self) -> None:
        """Test that kill switch activates HALT level."""
        controller = FailSafeController()
        state = controller.activate_kill_switch("Emergency stop")

        assert state.level == FailSafeLevel.HALT
        assert controller.is_trading_allowed() is False


class TestFailSafeControllerDeescalation:
    """Tests for de-escalation behavior."""

    def test_deactivate_from_caution(self) -> None:
        """Test deactivation from CAUTION level."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        state = controller.deactivate(source="operator")

        assert state.level == FailSafeLevel.NORMAL
        assert state.active is False

    def test_step_down_from_restricted(self) -> None:
        """Test step down from RESTRICTED to CAUTION."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.RESTRICTED, "Test")

        state = controller.step_down(source="operator")

        assert state.level == FailSafeLevel.CAUTION

    def test_step_down_from_normal_stays_normal(self) -> None:
        """Test step down from NORMAL stays at NORMAL."""
        controller = FailSafeController()

        state = controller.step_down(source="operator")

        assert state.level == FailSafeLevel.NORMAL

    def test_manual_recovery_required_for_halt(self) -> None:
        """Test that HALT level requires operator intervention."""
        controller = FailSafeController()
        controller.activate_kill_switch("Critical")

        # System cannot deactivate
        state = controller.deactivate(source="system")
        assert state.level == FailSafeLevel.HALT

        # System cannot step down
        state = controller.step_down(source="system")
        assert state.level == FailSafeLevel.HALT

        # Operator can deactivate
        state = controller.deactivate(source="operator")
        assert state.level == FailSafeLevel.NORMAL


class TestFailSafeControllerStressReporting:
    """Tests for stress reporting and escalation."""

    def test_normal_stress_resets_tracking(self) -> None:
        """Test that normal stress level resets stress tracking."""
        controller = FailSafeController()

        state = controller.report_stress("normal")

        assert state.level == FailSafeLevel.NORMAL

    def test_sustained_stress_triggers_escalation(self) -> None:
        """Test that sustained stress triggers escalation."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time_offset = [0]

        def time_source() -> datetime:
            return base_time + timedelta(seconds=time_offset[0])

        controller = FailSafeController(time_source=time_source)

        # Report high stress over 70 iterations, 2 seconds apart
        # Total: 140 seconds, exceeds threshold of 60
        for i in range(70):
            time_offset[0] = i * 2
            controller.report_stress("high")

        state = controller.get_state()
        assert state.level >= FailSafeLevel.RESTRICTED


class TestFailSafeControllerAutoRecovery:
    """Tests for auto-recovery mechanism."""

    def test_auto_recovery_after_delay(self) -> None:
        """Test automatic recovery after delay period."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time_offset = [0]

        def time_source() -> datetime:
            return base_time + timedelta(minutes=time_offset[0])

        config = FailSafeConfig(auto_recover_delay_minutes=5)
        controller = FailSafeController(config=config, time_source=time_source)

        # Escalate to CAUTION (not in require_manual_recovery_levels)
        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        # Advance time past auto-recovery delay
        time_offset[0] = 10

        # Get state triggers auto-recovery check
        state = controller.get_state()

        assert state.level == FailSafeLevel.NORMAL

    def test_no_auto_recovery_for_halt(self) -> None:
        """Test that HALT level does not auto-recover."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time_offset = [0]

        def time_source() -> datetime:
            return base_time + timedelta(minutes=time_offset[0])

        config = FailSafeConfig(auto_recover_delay_minutes=5)
        controller = FailSafeController(config=config, time_source=time_source)

        controller.activate_kill_switch("Critical")

        # Advance time past auto-recovery delay
        time_offset[0] = 60

        state = controller.get_state()

        # Should still be halted - requires manual recovery
        assert state.level == FailSafeLevel.HALT


class TestFailSafeControllerActions:
    """Tests for action management."""

    def test_acknowledge_action(self) -> None:
        """Test action acknowledgement."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        initial_state = controller.get_state()
        assert FailSafeAction.REDUCE_POSITIONS in initial_state.pending_actions

        controller.acknowledge_action(FailSafeAction.REDUCE_POSITIONS)

        new_state = controller.get_state()
        assert FailSafeAction.REDUCE_POSITIONS not in new_state.pending_actions

    def test_get_pending_actions(self) -> None:
        """Test getting pending actions."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.RESTRICTED, "Test")

        actions = controller.get_pending_actions()

        assert FailSafeAction.REDUCE_POSITIONS in actions
        assert FailSafeAction.CANCEL_PENDING in actions


class TestFailSafeControllerHistory:
    """Tests for escalation history."""

    def test_get_history(self) -> None:
        """Test history retrieval."""
        controller = FailSafeController()

        controller.escalate_to(FailSafeLevel.CAUTION, "First")
        controller.escalate_to(FailSafeLevel.RESTRICTED, "Second")

        history = controller.get_history()

        assert len(history) == 2
        assert history[0]["target_level"] == "caution"
        assert history[1]["target_level"] == "restricted"

    def test_history_limit(self) -> None:
        """Test history limit."""
        controller = FailSafeController()

        # Add many escalations without reset (escalate up and down)
        for i in range(10):
            controller.escalate_to(FailSafeLevel.CAUTION, f"Event {i}")
            controller.deactivate(source="operator", reason=f"Reset {i}")

        history = controller.get_history(limit=5)

        # Each escalate + deactivate = 2 events, 10 iterations = 20 events
        # Limited to last 5
        assert len(history) == 5

    def test_reset_clears_history(self) -> None:
        """Test that reset clears history."""
        controller = FailSafeController()
        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        controller.reset()

        history = controller.get_history()
        assert len(history) == 0


class TestFailSafeControllerNegative:
    """Negative tests for FailSafeController."""

    def test_unknown_stress_level_defaults_to_normal(self) -> None:
        """Test that unknown stress level defaults to NORMAL behavior."""
        controller = FailSafeController()

        state = controller.report_stress("unknown_level")

        assert state.level == FailSafeLevel.NORMAL
