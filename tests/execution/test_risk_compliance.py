# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for risk compliance checks."""

from __future__ import annotations

import pytest

from domain import Order, OrderSide
from execution.compliance import RiskCompliance, RiskConfig


class DummyMetrics:
    """Simple metrics collector used to validate instrumentation hooks."""

    def __init__(self) -> None:
        self.enabled = True
        self.kill_switch_states: list[tuple[bool, str]] = []
        self.gross_exposures: list[float] = []
        self.daily_drawdowns: list[tuple[float, str, str]] = []
        self.rejections: list[str] = []
        self.open_orders: list[tuple[int, str]] = []

    def record_kill_switch(self, enabled: bool, env: str = "prod") -> None:
        self.kill_switch_states.append((enabled, env))

    def record_gross_exposure(self, exposure: float, env: str = "prod") -> None:
        self.gross_exposures.append(float(exposure))

    def record_daily_drawdown(
        self, drawdown: float, mode: str = "percent", env: str = "prod"
    ) -> None:
        self.daily_drawdowns.append((float(drawdown), mode, env))

    def record_rejection(self, reason: str) -> None:
        self.rejections.append(reason)

    def record_open_orders(self, count: int, env: str = "prod") -> None:
        self.open_orders.append((int(count), env))


class TestRiskCompliance:
    """Test suite for RiskCompliance class."""

    def test_kill_switch_blocks_all_orders(self):
        """Test that kill switch blocks all orders when enabled."""
        config = RiskConfig(kill_switch=True)
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 100000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert "Kill switch is enabled" in decision.reasons
        assert "kill_switch" in decision.breached_limits

    def test_kill_switch_toggle(self):
        """Test toggling kill switch on and off."""
        config = RiskConfig(kill_switch=False)
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 100000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)
        assert decision.allowed

        compliance.set_kill_switch(True)
        decision = compliance.check_order(order, market_data, portfolio_state)
        assert not decision.allowed

        compliance.set_kill_switch(False)
        decision = compliance.check_order(order, market_data, portfolio_state)
        assert decision.allowed

    def test_max_notional_per_order_violation(self):
        """Test that orders exceeding max notional are blocked."""
        config = RiskConfig(kill_switch=False, max_notional_per_order=10000.0)
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 100000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("notional" in reason.lower() for reason in decision.reasons)
        assert "max_notional_per_order" in decision.breached_limits

    def test_max_notional_per_order_allowed(self):
        """Test that orders within max notional are allowed."""
        config = RiskConfig(kill_switch=False, max_notional_per_order=100000.0)
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 100000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert decision.allowed

    def test_per_symbol_position_cap_units(self):
        """Test per-symbol position cap in units mode."""
        config = RiskConfig(
            kill_switch=False,
            per_symbol_position_cap_type="units",
            per_symbol_position_cap_default=5.0,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=3.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {"BTC/USD": 3.0},
            "gross_exposure": 150000.0,
            "equity": 200000.0,
            "peak_equity": 200000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("Position" in reason for reason in decision.reasons)

    def test_per_symbol_position_cap_notional(self):
        """Test per-symbol position cap in notional mode."""
        config = RiskConfig(
            kill_switch=False,
            per_symbol_position_cap_type="notional",
            per_symbol_position_cap_default=100000.0,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=3.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {"BTC/USD": 1.0},
            "gross_exposure": 50000.0,
            "equity": 200000.0,
            "peak_equity": 200000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("notional" in reason.lower() for reason in decision.reasons)

    def test_max_gross_exposure_violation(self):
        """Test that orders exceeding max gross exposure are blocked."""
        config = RiskConfig(kill_switch=False, max_gross_exposure=150000.0)
        compliance = RiskCompliance(config)

        order = Order(
            symbol="ETH/USD",
            side=OrderSide.BUY,
            quantity=50.0,
            price=3000.0,
        )

        market_data = {"price": 3000.0}
        portfolio_state = {
            "positions": {"BTC/USD": 1.0},
            "gross_exposure": 50000.0,
            "equity": 200000.0,
            "peak_equity": 200000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("Gross exposure" in reason for reason in decision.reasons)
        assert "max_gross_exposure" in decision.breached_limits

    def test_daily_max_drawdown_percent_violation(self):
        """Test that orders are blocked when daily drawdown exceeds threshold."""
        config = RiskConfig(
            kill_switch=False,
            daily_max_drawdown_mode="percent",
            daily_max_drawdown_threshold=0.10,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 85000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("drawdown" in reason.lower() for reason in decision.reasons)
        assert "daily_max_drawdown" in decision.breached_limits

    def test_daily_max_drawdown_notional_violation(self):
        """Test daily drawdown in notional mode."""
        config = RiskConfig(
            kill_switch=False,
            daily_max_drawdown_mode="notional",
            daily_max_drawdown_threshold=10000.0,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 85000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("drawdown" in reason.lower() for reason in decision.reasons)

    def test_max_open_orders_violation(self):
        """Test that max open orders limit is enforced."""
        config = RiskConfig(kill_switch=False, max_open_orders_per_account=5)
        compliance = RiskCompliance(config)

        for _ in range(5):
            compliance.register_order_open()

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 100000.0,
            "peak_equity": 100000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert any("Open orders" in reason for reason in decision.reasons)

    def test_get_state(self):
        """Test that get_state returns current compliance state."""
        config = RiskConfig(
            kill_switch=True,
            max_notional_per_order=10000.0,
            max_gross_exposure=50000.0,
        )
        compliance = RiskCompliance(config)

        state = compliance.get_state()

        assert state["kill_switch"] is True
        assert state["max_notional_per_order"] == 10000.0
        assert state["max_gross_exposure"] == 50000.0
        assert "timestamp" in state

    def test_multiple_violations(self):
        """Test that multiple violations are all reported."""
        config = RiskConfig(
            kill_switch=False,
            max_notional_per_order=10000.0,
            max_gross_exposure=150000.0,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=5.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {"ETH/USD": 50.0},
            "gross_exposure": 100000.0,
            "equity": 200000.0,
            "peak_equity": 200000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert not decision.allowed
        assert len(decision.reasons) >= 2
        assert "max_notional_per_order" in decision.breached_limits
        assert "max_gross_exposure" in decision.breached_limits

    def test_disabled_checks_allow_orders(self):
        """Test that orders are allowed when all checks are disabled (0 limits)."""
        config = RiskConfig(
            kill_switch=False,
            max_notional_per_order=0.0,
            max_gross_exposure=0.0,
            daily_max_drawdown_threshold=0.0,
        )
        compliance = RiskCompliance(config)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=100.0,
            price=50000.0,
        )

        market_data = {"price": 50000.0}
        portfolio_state = {
            "positions": {"BTC/USD": 50.0},
            "gross_exposure": 5000000.0,
            "equity": 1000000.0,
            "peak_equity": 2000000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert decision.allowed
        assert len(decision.reasons) == 0

    def test_metrics_instrumentation_is_invoked(self):
        """RiskCompliance should surface state transitions through metrics hooks."""

        config = RiskConfig(
            kill_switch=False,
            max_notional_per_order=1000.0,
            daily_max_drawdown_mode="percent",
            daily_max_drawdown_threshold=0.05,
            max_open_orders_per_account=1,
        )
        metrics = DummyMetrics()
        compliance = RiskCompliance(config, metrics=metrics)

        # Initial state snapshot recorded at construction time.
        assert metrics.kill_switch_states[0][0] is False
        assert metrics.open_orders[0][0] == 0

        compliance.set_kill_switch(True)
        compliance.set_kill_switch(False)
        compliance.register_order_open()
        compliance.register_order_close()

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=2000.0,
        )
        market_data = {"price": 2000.0}
        portfolio_state = {
            "positions": {},
            "gross_exposure": 0.0,
            "equity": 900.0,
            "peak_equity": 1000.0,
        }

        decision = compliance.check_order(order, market_data, portfolio_state)

        assert decision.allowed is False
        # Latest kill switch change should be captured.
        assert metrics.kill_switch_states[-1][0] is False
        # Open orders metric should reflect increment and decrement.
        assert [entry[0] for entry in metrics.open_orders[-2:]] == [1, 0]
        # Gross exposure metric reflects the projected exposure including the order.
        assert metrics.gross_exposures[-1] == pytest.approx(2000.0)
        # Daily drawdown metric recorded once with percent mode.
        value, mode, _env = metrics.daily_drawdowns[-1]
        assert mode == "percent"
        assert value == pytest.approx(0.10, rel=1e-6)
        assert {"max_notional_per_order", "daily_max_drawdown"}.issubset(set(metrics.rejections))

    def test_update_config_validates_keys(self):
        """Partial config updates should be validated and applied atomically."""

        config = RiskConfig(max_notional_per_order=1000.0)
        compliance = RiskCompliance(config)

        updated = compliance.update_config(max_notional_per_order=2000.0)
        assert updated.max_notional_per_order == 2000.0
        assert compliance.get_state()["max_notional_per_order"] == 2000.0

        with pytest.raises(ValueError):
            compliance.update_config(unknown_option=1)
