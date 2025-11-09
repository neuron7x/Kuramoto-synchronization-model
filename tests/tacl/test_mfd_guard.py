# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Crisis scenario tests for MFD (Monotonic Free-energy Decrease) guard checks.

Tests verify that the TACL system properly enforces MFD constraints
and prevents actions that would increase free energy beyond acceptable bounds.
"""
from __future__ import annotations

import pytest

from tradepulse.runtime.behavior_contract import (
    ActionClass,
    SystemState,
    get_current_state,
    tacl_gate,
)


class TestMFDGuard:
    """Test suite for MFD guard enforcement."""

    def test_mfd_guard_allows_energy_decrease(self) -> None:
        """Verify that actions decreasing free energy are allowed."""
        F_now = 1.0
        F_next = 0.9
        epsilon = 0.01

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A1_LOCAL_CORRECTION,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=False,
        )

        assert decision.allowed is True
        assert decision.reason == "allowed"

    def test_mfd_guard_blocks_large_energy_spike(self) -> None:
        """Verify that large free energy increases are blocked."""
        F_now = 1.0
        F_next = 1.5  # Large spike
        epsilon = 0.01

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A1_LOCAL_CORRECTION,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=False,
        )

        assert decision.allowed is False
        assert decision.reason == "free_energy_spike"

    def test_mfd_guard_allows_small_increase_within_epsilon(self) -> None:
        """Verify that small increases within epsilon tolerance are allowed."""
        F_now = 1.0
        F_next = 1.005  # Small increase within epsilon
        epsilon = 0.01

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A1_LOCAL_CORRECTION,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=False,
        )

        assert decision.allowed is True
        assert decision.reason == "allowed"

    def test_mfd_guard_blocks_increase_without_recovery_path(self) -> None:
        """Verify that increases without a recovery path are blocked."""
        F_now = 1.0
        F_next = 1.002  # Very small increase but no recovery path
        epsilon = 0.01

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A1_LOCAL_CORRECTION,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=False,
        )

        assert decision.allowed is False
        assert decision.reason == "no_recovery_path"

    def test_mfd_guard_allows_increase_with_recovery_path(self) -> None:
        """Verify that increases with a recovery path are allowed."""
        F_now = 1.0
        F_next = 1.002  # Small increase with recovery path
        epsilon = 0.01

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A1_LOCAL_CORRECTION,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=True,
            dual_approved=False,
        )

        assert decision.allowed is True
        assert decision.reason == "allowed"

    def test_system_state_classification(self) -> None:
        """Test system state classification based on free energy."""
        F_baseline = 1.0

        # Normal state
        state = get_current_state(F_current=1.05, F_baseline=F_baseline)
        assert state == SystemState.NORMAL

        # Degraded state (10% deviation)
        state = get_current_state(F_current=1.15, F_baseline=F_baseline)
        assert state == SystemState.DEGRADED

        # Crisis state (20% deviation)
        state = get_current_state(F_current=1.25, F_baseline=F_baseline)
        assert state == SystemState.CRISIS

    def test_mfd_guard_blocks_systemic_actions_in_crisis(self) -> None:
        """Verify that systemic actions are blocked in crisis state."""
        F_now = 1.25  # Crisis level
        F_next = 1.24  # Decreasing
        F_baseline = 1.0
        epsilon = 0.01

        system_state = get_current_state(F_now, F_baseline)
        assert system_state == SystemState.CRISIS

        decision = tacl_gate(
            module_name="test_module",
            action_class=ActionClass.A2_SYSTEMIC,
            system_state=system_state,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=True,
        )

        assert decision.allowed is False
        assert decision.reason == "crisis_downgrade"

    def test_mfd_guard_requires_dual_approval_for_systemic(self) -> None:
        """Verify that systemic actions require dual approval."""
        F_now = 1.0
        F_next = 0.9
        epsilon = 0.01

        # Without dual approval
        decision = tacl_gate(
            module_name="thermo_controller",  # Module that requires dual approval
            action_class=ActionClass.A2_SYSTEMIC,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=False,
        )

        assert decision.allowed is False
        assert decision.reason == "dual_approval_missing"

        # With dual approval
        decision = tacl_gate(
            module_name="thermo_controller",
            action_class=ActionClass.A2_SYSTEMIC,
            system_state=SystemState.NORMAL,
            F_now=F_now,
            F_next=F_next,
            epsilon=epsilon,
            recovery_path=False,
            dual_approved=True,
        )

        assert decision.allowed is True
        assert decision.reason == "allowed"


@pytest.mark.integration
class TestMFDGuardIntegration:
    """Integration tests for MFD guard with link_activator."""

    def test_link_activator_respects_mfd_guard(self) -> None:
        """Verify that link_activator respects MFD guard checks."""
        from tradepulse.runtime.link_activator import LinkActivator

        # Create activator with low baseline to trigger violations
        activator = LinkActivator(F_baseline=0.001, epsilon=0.0001)

        # This should succeed (within budget)
        result = activator.apply("metallic", "node_a", "node_b")
        assert result.success is True

        # Simulate many activations to exhaust free energy budget
        for _ in range(100):
            result = activator.apply("metallic", "node_x", "node_y")

        # Eventually should hit MFD guard
        assert any(
            "MFD_VIOLATION" in entry.get("error", "")
            for entry in activator.get_activation_history()
        )
