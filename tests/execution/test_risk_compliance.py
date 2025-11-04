"""Unit tests for risk compliance checks."""

from __future__ import annotations

from domain import Order, OrderSide
from execution.compliance import RiskCompliance, RiskConfig


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
        portfolio_state = {"positions": {}, "gross_exposure": 0.0, "equity": 100000.0, "peak_equity": 100000.0}

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
        portfolio_state = {"positions": {}, "gross_exposure": 0.0, "equity": 100000.0, "peak_equity": 100000.0}

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
        portfolio_state = {"positions": {}, "gross_exposure": 0.0, "equity": 100000.0, "peak_equity": 100000.0}

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
        portfolio_state = {"positions": {}, "gross_exposure": 0.0, "equity": 100000.0, "peak_equity": 100000.0}

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
        portfolio_state = {"positions": {}, "gross_exposure": 0.0, "equity": 100000.0, "peak_equity": 100000.0}

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
