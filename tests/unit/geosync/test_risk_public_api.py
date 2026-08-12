# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync.risk module public API."""

import pytest


class TestRiskModuleImports:
    """Test that all public API imports work correctly."""

    def test_import_risk_manager(self) -> None:
        """Test RiskManager import from geosync.risk."""
        from geosync.risk import RiskManager

        assert RiskManager is not None

    def test_import_risk_limits(self) -> None:
        """Test RiskLimits import from geosync.risk."""
        from geosync.risk import RiskLimits

        assert RiskLimits is not None

    def test_import_risk_error(self) -> None:
        """Test RiskError import from geosync.risk."""
        from geosync.risk import RiskError

        assert RiskError is not None

    def test_import_limit_violation(self) -> None:
        """Test LimitViolation import from geosync.risk."""
        from geosync.risk import LimitViolation

        assert LimitViolation is not None

    def test_import_kill_switch(self) -> None:
        """Test KillSwitch import from geosync.risk."""
        from geosync.risk import KillSwitch

        assert KillSwitch is not None

    def test_import_portfolio_heat(self) -> None:
        """Test portfolio_heat import from geosync.risk."""
        from geosync.risk import portfolio_heat

        assert portfolio_heat is not None

    def test_import_automated_tester(self) -> None:
        """Test AutomatedRiskTester import from geosync.risk."""
        from geosync.risk import AutomatedRiskTester

        assert AutomatedRiskTester is not None


class TestRiskLimitsCreation:
    """Test RiskLimits instantiation."""

    def test_create_risk_limits_defaults(self) -> None:
        """Test creating RiskLimits with defaults."""
        from geosync.risk import RiskLimits

        limits = RiskLimits()

        assert limits.max_notional == float("inf")
        assert limits.max_position == float("inf")
        assert limits.max_orders_per_interval == 60

    def test_create_risk_limits_custom(self) -> None:
        """Test creating RiskLimits with custom values."""
        from geosync.risk import RiskLimits

        limits = RiskLimits(
            max_notional=100_000,
            max_position=10,
            max_orders_per_interval=30,
        )

        assert limits.max_notional == 100_000
        assert limits.max_position == 10
        assert limits.max_orders_per_interval == 30


class TestRiskManagerCreation:
    """Test RiskManager instantiation."""

    def test_create_risk_manager(self) -> None:
        """Test creating RiskManager with default limits."""
        from geosync.risk import RiskLimits, RiskManager

        limits = RiskLimits()
        manager = RiskManager(limits)

        assert manager is not None
        assert manager.limits is limits

    def test_create_risk_manager_with_limits(self) -> None:
        """Test creating RiskManager with custom limits."""
        from geosync.risk import RiskLimits, RiskManager

        limits = RiskLimits(max_notional=50_000, max_position=5)
        manager = RiskManager(limits)

        assert manager.limits.max_notional == 50_000
        assert manager.limits.max_position == 5


class TestRiskManagerValidation:
    """Test RiskManager validation methods."""

    def test_validate_order_passes(self) -> None:
        """Test order validation that passes."""
        from geosync.risk import RiskLimits, RiskManager

        limits = RiskLimits(max_notional=100_000, max_position=10)
        manager = RiskManager(limits)

        # This should not raise
        manager.validate_order("BTC/USD", "buy", 1, 25_000.0)

    def test_validate_order_rejects_notional(self) -> None:
        """Test order validation that rejects on notional."""
        from geosync.risk import LimitViolation, RiskLimits, RiskManager

        limits = RiskLimits(max_notional=10_000, max_position=10)
        manager = RiskManager(limits)

        with pytest.raises(LimitViolation, match="Notional cap exceeded"):
            manager.validate_order("BTC/USD", "buy", 1, 25_000.0)

    def test_validate_order_rejects_position(self) -> None:
        """Test order validation that rejects on position."""
        from geosync.risk import LimitViolation, RiskLimits, RiskManager

        limits = RiskLimits(max_notional=1_000_000, max_position=0.5)
        manager = RiskManager(limits)

        with pytest.raises(LimitViolation, match="Position cap exceeded"):
            manager.validate_order("BTC/USD", "buy", 1, 50_000.0)


class TestRiskManagerExposure:
    """Test RiskManager exposure tracking."""

    def test_register_fill_updates_position(self) -> None:
        """Test that register_fill updates position."""
        from geosync.risk import RiskLimits, RiskManager

        limits = RiskLimits(max_notional=1_000_000, max_position=100)
        manager = RiskManager(limits)

        manager.register_fill("BTC/USD", "buy", 1.0, 50_000.0)

        assert manager.current_position("BTC/USD") == 1.0
        assert manager.current_notional("BTC/USD") == 50_000.0

    def test_exposure_snapshot(self) -> None:
        """Test exposure_snapshot returns correct data."""
        from geosync.risk import RiskLimits, RiskManager

        limits = RiskLimits(max_notional=1_000_000, max_position=100)
        manager = RiskManager(limits)

        manager.register_fill("BTC/USD", "buy", 1.0, 50_000.0)
        manager.register_fill("ETH/USD", "buy", 10.0, 3_000.0)

        snapshot = manager.exposure_snapshot()

        # Check that both symbols are in snapshot (case-insensitive)
        snapshot_keys_lower = {k.lower() for k in snapshot.keys()}
        assert "btc/usd" in snapshot_keys_lower
        assert "eth/usd" in snapshot_keys_lower


class TestKillSwitch:
    """Test KillSwitch functionality."""

    def test_kill_switch_not_triggered_initially(self) -> None:
        """Test KillSwitch is not triggered initially."""
        from geosync.risk import KillSwitch

        switch = KillSwitch()

        assert switch.is_triggered() is False

    def test_kill_switch_trigger(self) -> None:
        """Test KillSwitch can be triggered."""
        from geosync.risk import KillSwitch

        switch = KillSwitch()
        switch.trigger("Test reason")

        assert switch.is_triggered() is True
        assert switch.reason == "Test reason"

    def test_kill_switch_reset(self) -> None:
        """Test KillSwitch can be reset."""
        from geosync.risk import KillSwitch

        switch = KillSwitch()
        switch.trigger("Test reason")
        switch.reset()

        assert switch.is_triggered() is False

    def test_kill_switch_guard_raises(self) -> None:
        """Test KillSwitch guard raises when triggered."""
        from geosync.risk import KillSwitch, RiskError

        switch = KillSwitch()
        switch.trigger("Test reason")

        with pytest.raises(RiskError, match="Kill-switch engaged"):
            switch.guard()


class TestPortfolioHeat:
    """Test portfolio_heat function."""

    def test_portfolio_heat_empty(self) -> None:
        """Test portfolio_heat with empty positions."""
        from geosync.risk import portfolio_heat

        result = portfolio_heat([])

        assert result == 0.0

    def test_portfolio_heat_single_position(self) -> None:
        """Test portfolio_heat with single position."""
        from geosync.risk import portfolio_heat

        positions = [{"qty": 1.0, "price": 50_000.0, "risk_weight": 1.0, "side": "long"}]
        result = portfolio_heat(positions)

        assert result == 50_000.0

    def test_portfolio_heat_multiple_positions(self) -> None:
        """Test portfolio_heat with multiple positions."""
        from geosync.risk import portfolio_heat

        positions = [
            {"qty": 1.0, "price": 50_000.0, "risk_weight": 1.0, "side": "long"},
            {"qty": 10.0, "price": 3_000.0, "risk_weight": 0.5, "side": "long"},
        ]
        result = portfolio_heat(positions)

        # 50000 * 1.0 * 1.0 + 30000 * 0.5 = 50000 + 15000 = 65000
        assert result == 65_000.0
