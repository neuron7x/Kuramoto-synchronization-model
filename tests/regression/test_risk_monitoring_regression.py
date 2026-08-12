# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for risk monitoring module.

These tests capture edge cases and bug fixes for:
- FailSafe controller state transitions
- Compliance manager audit trail integrity
- Advanced risk manager stress protocols
"""

from __future__ import annotations

import math
from pathlib import Path

from core.risk_monitoring.advanced_risk_manager import (
    AdvancedRiskManager,
    MarketDepthData,
    RiskState,
    StressResponseProtocol,
)
from core.risk_monitoring.compliance import (
    ComplianceManager,
    RegulationType,
)
from core.risk_monitoring.fail_safe import (
    FailSafeConfig,
    FailSafeController,
    FailSafeLevel,
)


class TestFailSafeRegressions:
    """Regression tests for FailSafe controller edge cases."""

    def test_emergency_without_liquidation_enabled_falls_back_to_halt(self) -> None:
        """Regression: Emergency activation with disabled liquidation must fall back to HALT.

        Bug: When emergency liquidation was disabled in config, calling
        activate_emergency() would still try to transition to EMERGENCY level.
        Fix: Now correctly falls back to HALT level.
        """
        config = FailSafeConfig(enable_emergency_liquidation=False)
        controller = FailSafeController(config=config)

        state = controller.activate_emergency("Test emergency", source="test")

        # Should fall back to HALT, not EMERGENCY
        assert state.level == FailSafeLevel.HALT
        assert state.active is True

    def test_escalation_to_same_level_ignored(self) -> None:
        """Regression: Repeated escalation to same level must be ignored.

        Bug: Multiple escalations to the same level could corrupt state.
        Fix: Now ignores escalation if not to a higher level.
        """
        controller = FailSafeController()

        # First escalation succeeds
        state1 = controller.escalate_to(FailSafeLevel.CAUTION, "First", source="test")
        assert state1.level == FailSafeLevel.CAUTION

        # Second escalation to same level is ignored
        state2 = controller.escalate_to(FailSafeLevel.CAUTION, "Second", source="test")
        assert state2.level == FailSafeLevel.CAUTION
        assert state2.reason == "First"  # Reason unchanged

    def test_manual_recovery_required_for_halt_level(self) -> None:
        """Regression: HALT level requires operator intervention to deactivate.

        Bug: System could auto-deactivate from HALT level.
        Fix: Now requires source="operator" for HALT and EMERGENCY levels.
        """
        controller = FailSafeController()
        controller.activate_kill_switch("Critical issue")

        # System cannot deactivate from HALT
        state = controller.deactivate(source="system", reason="Auto recovery")
        assert state.level == FailSafeLevel.HALT  # Still halted

        # Operator can deactivate
        state = controller.deactivate(source="operator", reason="Manual recovery")
        assert state.level == FailSafeLevel.NORMAL


class TestComplianceRegressions:
    """Regression tests for Compliance manager edge cases."""

    def test_audit_trail_hash_chain_integrity(self, tmp_path: Path) -> None:
        """Regression: Audit trail entries must maintain hash chain for tamper detection.

        Bug: Hash chain could be broken if entries were recorded too quickly.
        Fix: Now properly links each entry to the previous one.
        """
        manager = ComplianceManager(storage_path=tmp_path, entity_id="TEST")

        # Record multiple entries
        entry1 = manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed order",
        )
        entry2 = manager.record_audit_entry(
            event_type="execution",
            actor="system",
            action="executed order",
        )
        entry3 = manager.record_audit_entry(
            event_type="position",
            actor="system",
            action="updated position",
        )

        # First entry has no previous hash
        assert entry1.hash_chain is None

        # Second entry references first
        assert entry2.hash_chain is not None
        assert entry1.entry_id in entry2.hash_chain

        # Third entry references second
        assert entry3.hash_chain is not None
        assert entry2.entry_id in entry3.hash_chain

    def test_violation_resolution_updates_remediation(self, tmp_path: Path) -> None:
        """Regression: Resolving a violation must update remediation notes.

        Bug: Resolution notes were not being saved.
        Fix: Now properly updates the remediation field.
        """
        manager = ComplianceManager(storage_path=tmp_path)

        violation = manager.record_violation(
            regulation=RegulationType.MIFID_II,
            rule="Position limit exceeded",
            severity="warning",
            description="Position exceeded 10% limit",
        )

        # Resolve with notes
        success = manager.resolve_violation(
            violation.violation_id, "Reduced position to comply with limits"
        )

        assert success is True
        assert violation.resolved is True
        assert "Reduced position" in violation.remediation


class TestAdvancedRiskManagerRegressions:
    """Regression tests for Advanced Risk Manager edge cases."""

    def test_empty_market_depth_handles_gracefully(self) -> None:
        """Regression: Empty market depth data must not cause crash.

        Bug: Empty bids/asks would cause division by zero.
        Fix: Now returns default metrics for empty data.
        """
        manager = AdvancedRiskManager()

        empty_depth = MarketDepthData(bids=[], asks=[])
        metrics = manager.analyze_liquidity(empty_depth)

        assert metrics is not None
        assert metrics.spread_bps >= 0
        assert math.isfinite(metrics.bid_depth_value)
        assert math.isfinite(metrics.ask_depth_value)

    def test_nan_volatility_handled_safely(self) -> None:
        """Regression: NaN volatility input must be handled safely.

        Bug: NaN volatility would propagate through risk calculations.
        Fix: Now detects and replaces NaN with default value.
        """
        manager = AdvancedRiskManager()
        market_depth = MarketDepthData(
            bids=[(100.0, 1000.0)],
            asks=[(100.5, 1000.0)],
        )
        liquidity = manager.analyze_liquidity(market_depth)

        # Pass NaN volatility
        assessment = manager.assess_risk(
            current_price=100.0,
            volatility=float("nan"),
            liquidity_metrics=liquidity,
        )

        # Should produce valid assessment without NaN propagation
        assert math.isfinite(assessment.risk_score)
        assert 0 <= assessment.risk_score <= 1

    def test_stress_protocol_comparison_operators(self) -> None:
        """Regression: StressResponseProtocol comparison must work correctly.

        Bug: String comparison was used instead of severity ordering.
        Fix: Now uses proper severity-based comparison.
        """
        assert StressResponseProtocol.NORMAL < StressResponseProtocol.DEFENSIVE
        assert StressResponseProtocol.DEFENSIVE < StressResponseProtocol.PROTECTIVE
        assert StressResponseProtocol.PROTECTIVE < StressResponseProtocol.HALT
        assert StressResponseProtocol.HALT < StressResponseProtocol.EMERGENCY

        # Verify inverse
        assert StressResponseProtocol.EMERGENCY > StressResponseProtocol.NORMAL
        assert StressResponseProtocol.HALT >= StressResponseProtocol.HALT
        assert StressResponseProtocol.NORMAL <= StressResponseProtocol.NORMAL

    def test_risk_state_comparison_operators(self) -> None:
        """Regression: RiskState comparison must work correctly.

        Bug: String comparison was used instead of severity ordering.
        Fix: Now uses proper severity-based comparison.
        """
        assert RiskState.OPTIMAL < RiskState.STABLE
        assert RiskState.STABLE < RiskState.ELEVATED
        assert RiskState.ELEVATED < RiskState.STRESSED
        assert RiskState.STRESSED < RiskState.CRITICAL

        # Verify equality
        assert RiskState.OPTIMAL == RiskState.OPTIMAL
        assert not (RiskState.OPTIMAL != RiskState.OPTIMAL)
