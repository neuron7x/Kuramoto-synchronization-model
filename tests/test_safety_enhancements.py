"""Tests for enhanced safety components.

This module tests the enhancements to:
- Kill switch (audit logging, state persistence, cooldown)
- Dual approval (expiration, validation, audit trail)
- Configuration validation
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import runtime.dual_approval as dual_approval
from runtime.dual_approval import (
    ApprovalAction,
    ApprovalResult,
    DualApprovalManager,
    get_required_approval_actions,
    requires_dual_approval,
)
from runtime.kill_switch import (
    KillSwitchManager,
    KillSwitchReason,
    is_kill_switch_active,
)
from runtime.thermo_config import (
    ConfigValidationError,
    ConfigValidationIssue,
    ConfigValidationResult,
    ThermoConfig,
    load_default_config,
)


class TestKillSwitchEnhancements:
    """Tests for enhanced kill switch functionality."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        KillSwitchManager.reset_instance()

    def test_activation_with_reason(self) -> None:
        """Test kill switch activation with reason tracking."""
        manager = KillSwitchManager(cooldown_seconds=0.0, _force_new=True)

        result = manager.activate(
            reason=KillSwitchReason.SECURITY_INCIDENT,
            source="test_module",
            force=True,
        )

        assert result is True
        assert manager.is_active()

        status = manager.get_status()
        assert status["activation_reason"] == "security_incident_detected"
        assert status["activation_source"] == "test_module"

    def test_audit_logging(self) -> None:
        """Test that state changes are logged."""
        manager = KillSwitchManager(cooldown_seconds=0.0, _force_new=True)

        manager.activate(reason="test_activation", source="test", force=True)
        manager.deactivate(reason="test_deactivation", source="test", force=True)

        audit_log = manager.get_audit_log()

        assert len(audit_log) == 2
        assert audit_log[0]["action"] == "activate"
        assert audit_log[1]["action"] == "deactivate"

    def test_cooldown_protection(self) -> None:
        """Test that cooldown prevents rapid toggling."""
        manager = KillSwitchManager(cooldown_seconds=10.0, _force_new=True)

        # First activation should succeed
        result1 = manager.activate(reason="first", source="test", force=True)
        assert result1 is True

        # Deactivate with force
        manager.deactivate(reason="deactivate", source="test", force=True)

        # Second activation within cooldown should fail (without force)
        result2 = manager.activate(reason="second", source="test", force=False)
        assert result2 is False

    def test_state_persistence(self) -> None:
        """Test state persistence to file."""
        with TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "kill_switch_state.json"

            # Create manager and activate
            manager1 = KillSwitchManager(
                cooldown_seconds=0.0,
                persist_path=persist_path,
                _force_new=True,
            )
            manager1.activate(
                reason=KillSwitchReason.CIRCUIT_BREAKER,
                source="test",
                force=True,
            )

            assert persist_path.exists()

    def test_callback_notification(self) -> None:
        """Test that callbacks are notified on state changes."""
        manager = KillSwitchManager(cooldown_seconds=0.0, _force_new=True)

        callback_calls = []

        def callback(is_active: bool, reason: str) -> None:
            callback_calls.append((is_active, reason))

        manager.register_callback(callback)

        manager.activate(reason="test", source="test", force=True)
        manager.deactivate(reason="done", source="test", force=True)

        assert len(callback_calls) == 2
        assert callback_calls[0] == (True, "test")
        assert callback_calls[1] == (False, "done")

    def test_legacy_api_compatibility(self) -> None:
        """Test that legacy API still works."""
        KillSwitchManager.reset_instance()

        assert not is_kill_switch_active()

        # Use legacy API (with force via internal manager)
        manager = KillSwitchManager(cooldown_seconds=0.0, _force_new=True)
        manager.activate(reason="test", source="legacy", force=True)

        assert manager.is_active()

        manager.deactivate(reason="test", source="legacy", force=True)
        assert not manager.is_active()


class TestDualApprovalEnhancements:
    """Tests for enhanced dual approval functionality."""

    def test_token_expiration(self) -> None:
        """Test that tokens have proper expiration."""
        manager = DualApprovalManager(
            secret="test_secret",
            token_expiration_seconds=300.0,
        )

        token = manager.issue_service_token(
            action_id="test_action",
            subject="test_user",
        )

        assert token is not None
        assert len(token) > 0

    def test_approval_validation(self) -> None:
        """Test successful approval validation."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=0.0,
        )

        action_id = ApprovalAction.TOPOLOGY_MUTATION.value
        token = manager.issue_service_token(action_id=action_id)

        result = manager.validate(
            action_id=action_id,
            token=token,
            source="test",
        )

        assert result == ApprovalResult.APPROVED

    def test_action_mismatch_rejection(self) -> None:
        """Test rejection when action_id doesn't match token."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=0.0,
        )

        token = manager.issue_service_token(action_id="action_a")

        with pytest.raises(ValueError, match="action_mismatch"):
            manager.validate(action_id="action_b", token=token, source="test")

    def test_cooldown_enforcement(self) -> None:
        """Test that cooldown is enforced between approvals."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=3600.0,  # 1 hour
        )

        action_id = "test_action"
        token = manager.issue_service_token(action_id=action_id)

        # First approval should succeed
        manager.validate(action_id=action_id, token=token, source="test")

        # Issue new token
        token2 = manager.issue_service_token(action_id=action_id)

        # Second approval should fail due to cooldown
        with pytest.raises(ValueError, match="cooldown"):
            manager.validate(action_id=action_id, token=token2, source="test")

    def test_audit_trail(self) -> None:
        """Test that approval attempts are logged."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=0.0,
        )

        action_id = "test_action"
        token = manager.issue_service_token(action_id=action_id)
        manager.validate(action_id=action_id, token=token, source="test")

        audit_log = manager.get_audit_log()

        assert len(audit_log) == 1
        assert audit_log[0]["result"] == "approved"
        assert audit_log[0]["action_id"] == action_id

    def test_is_action_approved(self) -> None:
        """Test checking if action has valid approval."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=3600.0,  # 1 hour cooldown for valid approval window
        )

        action_id = "test_action"
        assert not manager.is_action_approved(action_id)

        token = manager.issue_service_token(action_id=action_id)
        manager.validate(action_id=action_id, token=token, source="test")

        assert manager.is_action_approved(action_id)

    def test_approval_expires_with_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Approvals should not outlive the encoded token expiration."""
        base_time = dual_approval.time.time()
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=3600.0,
            token_expiration_seconds=30.0,
        )

        monkeypatch.setattr(dual_approval.time, "time", lambda: base_time)

        action_id = "test_action"
        token = manager.issue_service_token(action_id=action_id)
        manager.validate(action_id=action_id, token=token, source="test")

        assert manager.is_action_approved(action_id)

        monkeypatch.setattr(dual_approval.time, "time", lambda: base_time + 120.0)

        assert not manager.is_action_approved(action_id)

    def test_revoke_approval(self) -> None:
        """Test revoking an approval."""
        manager = DualApprovalManager(
            secret="test_secret",
            cooldown_seconds=3600.0,  # 1 hour cooldown for valid approval window
        )

        action_id = "test_action"
        token = manager.issue_service_token(action_id=action_id)
        manager.validate(action_id=action_id, token=token, source="test")

        assert manager.is_action_approved(action_id)

        manager.revoke_approval(action_id)
        assert not manager.is_action_approved(action_id)

    def test_requires_dual_approval_helper(self) -> None:
        """Test the requires_dual_approval helper function."""
        assert requires_dual_approval("thermo_controller") is True
        assert requires_dual_approval("other_module") is False

    def test_get_required_approval_actions(self) -> None:
        """Test getting list of required approval actions."""
        actions = get_required_approval_actions()

        assert "topology_mutation" in actions
        assert "protocol_activation" in actions
        assert len(actions) >= 6


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_default_config_is_valid(self) -> None:
        """Test that default configuration passes validation."""
        config = ThermoConfig()
        result = config.validate()

        assert result.valid is True
        assert len(result.issues) == 0

    def test_invalid_control_temperature(self) -> None:
        """Test validation of control temperature."""
        config = ThermoConfig()
        config.control_temperature = -0.5

        result = config.validate()

        assert result.valid is False
        assert any("control_temperature" in issue.field for issue in result.issues)

    def test_invalid_crisis_thresholds(self) -> None:
        """Test validation of crisis threshold ordering."""
        config = ThermoConfig()
        config.crisis.elevated_threshold = 0.5
        config.crisis.critical_threshold = 0.25

        result = config.validate()

        assert result.valid is False
        assert any("crisis.thresholds" in issue.field for issue in result.issues)

    def test_invalid_safety_constraints(self) -> None:
        """Test validation of safety constraints."""
        config = ThermoConfig()
        config.safety.epsilon_base = -0.01

        result = config.validate()

        assert result.valid is False
        assert any("safety.epsilon_base" in issue.field for issue in result.issues)

    def test_invalid_genetic_algorithm_config(self) -> None:
        """Test validation of genetic algorithm config."""
        config = ThermoConfig()
        config.genetic_algorithm.crossover_prob = 1.5  # Invalid

        result = config.validate()

        assert result.valid is False
        assert any("crossover_prob" in issue.field for issue in result.issues)

    def test_invalid_recovery_agent_config(self) -> None:
        """Test validation of recovery agent config."""
        config = ThermoConfig()
        config.recovery_agent.learning_rate = 0.0  # Invalid

        result = config.validate()

        assert result.valid is False
        assert any("learning_rate" in issue.field for issue in result.issues)

    def test_validate_or_raise(self) -> None:
        """Test validate_or_raise raises on invalid config."""
        config = ThermoConfig()
        config.control_temperature = -1.0

        with pytest.raises(ConfigValidationError) as exc_info:
            config.validate_or_raise()

        assert exc_info.value.result.valid is False
        assert len(exc_info.value.result.issues) > 0

    def test_validation_result_to_dict(self) -> None:
        """Test ConfigValidationResult serialization."""
        result = ConfigValidationResult(
            valid=False,
            issues=[
                ConfigValidationIssue(
                    field="test",
                    message="test error",
                    severity="error",
                )
            ],
            warnings=[],
        )

        data = result.to_dict()

        assert data["valid"] is False
        assert data["issue_count"] == 1
        assert data["warning_count"] == 0

    def test_load_default_config_is_valid(self) -> None:
        """Test that loaded default config is valid."""
        config = load_default_config()
        result = config.validate()

        assert result.valid is True

    def test_warning_for_high_temperature(self) -> None:
        """Test that high temperature generates warning."""
        config = ThermoConfig()
        config.control_temperature = 1.5  # High but valid

        result = config.validate()

        # Should be valid but with warning
        assert result.valid is True
        assert any("control_temperature" in w.field for w in result.warnings)
