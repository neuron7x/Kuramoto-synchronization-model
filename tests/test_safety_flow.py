# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for the central risk engine and safety flow.

This test module validates the complete safety infrastructure:
- Environment modes (BACKTEST, PAPER, LIVE)
- Central risk engine with configurable limits
- Kill-switch and safe-mode mechanisms
- Integration tests for safety scenarios
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from tradepulse.risk import (
    CentralRiskEngine,
    EnvironmentConfig,
    EnvironmentMode,
    RiskEngineConfig,
    RiskStatus,
    SafetyController,
    SafetyState,
    get_current_mode,
    is_live_trading_allowed,
    load_risk_config,
    require_mode,
    set_current_mode,
    validate_environment,
)
from tradepulse.risk.engine import (
    MarketState,
    OrderContext,
    PortfolioState,
    RiskViolation,
)
from tradepulse.risk.environment import EnvironmentError
from tradepulse.risk.kill_switch import KillSwitchTriggeredError, SafetyMode


class TestEnvironmentModes:
    """Tests for environment mode handling."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None
        os.environ.pop("TRADEPULSE_ENV_MODE", None)

    def teardown_method(self) -> None:
        """Clean up after each test."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None
        os.environ.pop("TRADEPULSE_ENV_MODE", None)

    def test_environment_mode_from_string(self) -> None:
        """Test parsing environment modes from strings."""
        assert EnvironmentMode.from_string("backtest") == EnvironmentMode.BACKTEST
        assert EnvironmentMode.from_string("PAPER") == EnvironmentMode.PAPER
        assert EnvironmentMode.from_string("Live") == EnvironmentMode.LIVE

    def test_environment_mode_invalid_string(self) -> None:
        """Test that invalid mode strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid environment mode"):
            EnvironmentMode.from_string("invalid")

    def test_default_mode_is_backtest(self) -> None:
        """Test that default mode is BACKTEST."""
        mode = get_current_mode()
        assert mode == EnvironmentMode.BACKTEST

    def test_mode_from_environment_variable(self) -> None:
        """Test that mode can be set via environment variable."""
        os.environ["TRADEPULSE_ENV_MODE"] = "paper"
        mode = get_current_mode()
        assert mode == EnvironmentMode.PAPER

    def test_set_current_mode(self) -> None:
        """Test setting the current mode."""
        set_current_mode(EnvironmentMode.LIVE)
        assert get_current_mode() == EnvironmentMode.LIVE

        set_current_mode("paper")
        assert get_current_mode() == EnvironmentMode.PAPER

    def test_environment_config_for_backtest(self) -> None:
        """Test configuration for BACKTEST mode."""
        config = EnvironmentConfig.for_mode(EnvironmentMode.BACKTEST)
        assert config.require_api_keys is False
        assert config.require_risk_engine is False
        assert config.allow_real_orders is False
        assert config.enforce_kill_switch is False

    def test_environment_config_for_paper(self) -> None:
        """Test configuration for PAPER mode."""
        config = EnvironmentConfig.for_mode(EnvironmentMode.PAPER)
        assert config.require_api_keys is False
        assert config.require_risk_engine is True
        assert config.allow_real_orders is False
        assert config.enforce_kill_switch is True

    def test_environment_config_for_live(self) -> None:
        """Test configuration for LIVE mode."""
        config = EnvironmentConfig.for_mode(EnvironmentMode.LIVE)
        assert config.require_api_keys is True
        assert config.require_risk_engine is True
        assert config.allow_real_orders is True
        assert config.enforce_kill_switch is True

    def test_validate_environment_live_without_keys(self) -> None:
        """Test that LIVE mode requires API keys."""
        valid, errors = validate_environment(
            EnvironmentMode.LIVE,
            api_keys_present=False,
            risk_engine_enabled=True,
        )
        assert valid is False
        assert any("API keys" in e for e in errors)

    def test_validate_environment_live_without_risk_engine(self) -> None:
        """Test that LIVE mode requires risk engine."""
        valid, errors = validate_environment(
            EnvironmentMode.LIVE,
            api_keys_present=True,
            risk_engine_enabled=False,
        )
        assert valid is False
        assert any("risk engine" in e for e in errors)

    def test_validate_environment_live_valid(self) -> None:
        """Test valid LIVE mode configuration."""
        valid, errors = validate_environment(
            EnvironmentMode.LIVE,
            api_keys_present=True,
            risk_engine_enabled=True,
        )
        assert valid is True
        assert len(errors) == 0

    def test_is_live_trading_allowed(self) -> None:
        """Test checking if live trading is allowed."""
        set_current_mode(EnvironmentMode.BACKTEST)
        assert is_live_trading_allowed() is False

        set_current_mode(EnvironmentMode.PAPER)
        assert is_live_trading_allowed() is False

        set_current_mode(EnvironmentMode.LIVE)
        assert is_live_trading_allowed() is True

    def test_require_mode_decorator(self) -> None:
        """Test the require_mode decorator."""

        @require_mode(EnvironmentMode.LIVE)
        def live_only_function() -> str:
            return "executed"

        set_current_mode(EnvironmentMode.LIVE)
        assert live_only_function() == "executed"

        set_current_mode(EnvironmentMode.PAPER)
        with pytest.raises(EnvironmentError, match="only allowed in modes"):
            live_only_function()

    def test_require_mode_multiple_modes(self) -> None:
        """Test require_mode with multiple allowed modes."""

        @require_mode(EnvironmentMode.PAPER, EnvironmentMode.LIVE)
        def trading_function() -> str:
            return "executed"

        set_current_mode(EnvironmentMode.PAPER)
        assert trading_function() == "executed"

        set_current_mode(EnvironmentMode.LIVE)
        assert trading_function() == "executed"

        set_current_mode(EnvironmentMode.BACKTEST)
        with pytest.raises(EnvironmentError):
            trading_function()


class TestRiskEngineConfig:
    """Tests for risk engine configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = RiskEngineConfig()
        assert config.enable_risk_checks is True
        assert config.max_leverage > 0

    def test_config_from_dict(self) -> None:
        """Test creating config from dictionary."""
        data = {
            "max_position_size_default": 50.0,
            "max_notional_per_order": 50000.0,
            "max_leverage": 3.0,
            "enable_risk_checks": True,
        }
        config = RiskEngineConfig.from_dict(data)
        assert config.max_position_size_default == 50.0
        assert config.max_notional_per_order == 50000.0
        assert config.max_leverage == 3.0

    def test_config_to_dict(self) -> None:
        """Test converting config to dictionary."""
        config = RiskEngineConfig(max_leverage=5.0)
        data = config.to_dict()
        assert data["max_leverage"] == 5.0
        assert "enable_risk_checks" in data

    def test_load_config_from_yaml(self) -> None:
        """Test loading configuration from YAML file."""
        yaml_content = """
max_position_size_default: 100.0
max_notional_per_order: 100000.0
max_leverage: 5.0
enable_risk_checks: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = load_risk_config(Path(f.name))
                assert config.max_position_size_default == 100.0
                assert config.max_leverage == 5.0
            finally:
                os.unlink(f.name)

    def test_load_config_from_json(self) -> None:
        """Test loading configuration from JSON file."""
        json_content = {
            "max_position_size_default": 75.0,
            "max_leverage": 4.0,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            f.flush()

            try:
                config = load_risk_config(Path(f.name))
                assert config.max_position_size_default == 75.0
                assert config.max_leverage == 4.0
            finally:
                os.unlink(f.name)

    def test_symbol_limits(self) -> None:
        """Test per-symbol limit configuration."""
        from tradepulse.risk.config import SymbolLimits

        config = RiskEngineConfig(
            max_position_size_default=100.0,
            symbol_limits={
                "BTC/USD": SymbolLimits(max_position_size=10.0),
            },
        )

        btc_limits = config.get_symbol_limits("BTC/USD")
        assert btc_limits.max_position_size == 10.0

        eth_limits = config.get_symbol_limits("ETH/USD")
        assert eth_limits.max_position_size == 100.0  # Default


class TestSafetyController:
    """Tests for kill-switch and safe-mode functionality."""

    def test_initial_state(self) -> None:
        """Test initial safety state."""
        controller = SafetyController()
        assert controller.is_kill_switch_active() is False
        assert controller.is_safe_mode_active() is False
        assert controller.get_position_multiplier() == 1.0

    def test_activate_kill_switch(self) -> None:
        """Test kill-switch activation."""
        controller = SafetyController()
        controller.activate_kill_switch(
            reason="test_activation",
            source="test",
        )

        assert controller.is_kill_switch_active() is True
        state = controller.state
        assert state.kill_switch_reason == "test_activation"
        assert state.mode == SafetyMode.HALTED

    def test_deactivate_kill_switch(self) -> None:
        """Test kill-switch deactivation."""
        controller = SafetyController()
        controller.activate_kill_switch(reason="test", source="test")
        controller.deactivate_kill_switch(source="operator", reason="reset")

        assert controller.is_kill_switch_active() is False
        assert controller.state.mode == SafetyMode.NORMAL

    def test_activate_safe_mode(self) -> None:
        """Test safe mode activation."""
        controller = SafetyController(safe_mode_position_multiplier=0.5)
        controller.activate_safe_mode(
            reason="drawdown_warning",
            source="risk_engine",
        )

        assert controller.is_safe_mode_active() is True
        assert controller.get_position_multiplier() == 0.5
        assert controller.state.mode == SafetyMode.SAFE

    def test_safe_mode_with_custom_multiplier(self) -> None:
        """Test safe mode with custom position multiplier."""
        controller = SafetyController()
        controller.activate_safe_mode(
            reason="test",
            source="test",
            position_multiplier=0.25,
        )

        assert controller.get_position_multiplier() == 0.25

    def test_kill_switch_overrides_safe_mode(self) -> None:
        """Test that kill-switch takes precedence over safe mode."""
        controller = SafetyController()
        controller.activate_safe_mode(reason="safe", source="test")
        controller.activate_kill_switch(reason="emergency", source="test")

        assert controller.state.mode == SafetyMode.HALTED
        assert controller.should_force_paper_trading() is True

    def test_guard_order_raises_when_halted(self) -> None:
        """Test that guard_order raises when kill-switch is active."""
        controller = SafetyController()
        controller.activate_kill_switch(reason="test", source="test")

        with pytest.raises(KillSwitchTriggeredError, match="test"):
            controller.guard_order()

    def test_state_persistence(self) -> None:
        """Test state persistence to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "safety_state.json"

            # Create controller and activate kill-switch
            controller1 = SafetyController(persist_path=persist_path)
            controller1.activate_kill_switch(reason="persist_test", source="test")

            assert persist_path.exists()

            # Create new controller and verify state loaded
            controller2 = SafetyController(persist_path=persist_path)
            assert controller2.is_kill_switch_active() is True
            assert controller2.state.kill_switch_reason == "persist_test"

    def test_audit_log(self) -> None:
        """Test audit logging of state changes."""
        controller = SafetyController()
        controller.activate_kill_switch(reason="test1", source="test")
        controller.deactivate_kill_switch(source="operator", reason="reset")

        audit_log = controller.get_audit_log()
        assert len(audit_log) == 2
        assert audit_log[0]["action"] == "kill_switch_activated"
        assert audit_log[1]["action"] == "kill_switch_deactivated"

    def test_callback_notification(self) -> None:
        """Test callback notifications on state changes."""
        controller = SafetyController()
        states_received: list[SafetyState] = []

        def callback(state: SafetyState) -> None:
            states_received.append(state)

        controller.register_callback(callback)
        controller.activate_kill_switch(reason="test", source="test")

        assert len(states_received) == 1
        assert states_received[0].kill_switch_active is True


class TestCentralRiskEngine:
    """Tests for the central risk engine."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None
        set_current_mode(EnvironmentMode.PAPER)

    def teardown_method(self) -> None:
        """Clean up after tests."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None

    def _create_engine(
        self,
        config: RiskEngineConfig | None = None,
        safety: SafetyController | None = None,
    ) -> CentralRiskEngine:
        """Create a risk engine for testing."""
        return CentralRiskEngine(
            config=config or RiskEngineConfig(),
            safety_controller=safety or SafetyController(),
        )

    def _create_order(
        self,
        symbol: str = "BTC/USD",
        side: str = "buy",
        quantity: float = 1.0,
        price: float = 50000.0,
    ) -> OrderContext:
        """Create an order context for testing."""
        return OrderContext(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
        )

    def _create_portfolio(
        self,
        positions: dict[str, float] | None = None,
        equity: float = 100000.0,
        peak_equity: float | None = None,
        daily_pnl: float = 0.0,
        total_exposure: float = 0.0,
    ) -> PortfolioState:
        """Create a portfolio state for testing."""
        return PortfolioState(
            positions=positions or {},
            equity=equity,
            peak_equity=peak_equity or equity,
            daily_pnl=daily_pnl,
            total_exposure=total_exposure,
        )

    def _create_market(self, prices: dict[str, float] | None = None) -> MarketState:
        """Create a market state for testing."""
        return MarketState(prices=prices or {"BTC/USD": 50000.0})

    def test_order_allowed_within_limits(self) -> None:
        """Test that orders within limits are allowed."""
        config = RiskEngineConfig(
            max_position_size_default=100.0,
            max_notional_per_order=1000000.0,
        )
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(quantity=1.0, price=50000.0),
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.allowed is True
        assert decision.risk_status == RiskStatus.OK
        assert len(decision.violations) == 0

    def test_order_blocked_by_kill_switch(self) -> None:
        """Test that orders are blocked when kill-switch is active."""
        safety = SafetyController()
        safety.activate_kill_switch(reason="test", source="test")
        engine = self._create_engine(safety=safety)

        decision = engine.assess_order(
            self._create_order(),
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.KILL_SWITCH_ACTIVE in decision.violations
        assert decision.risk_status == RiskStatus.HALTED

    def test_order_blocked_by_position_limit(self) -> None:
        """Test that orders exceeding position limits are blocked."""
        config = RiskEngineConfig(max_position_size_default=5.0)
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(quantity=10.0),
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.POSITION_LIMIT_EXCEEDED in decision.violations

    def test_order_blocked_by_notional_limit(self) -> None:
        """Test that orders exceeding notional limits are blocked."""
        config = RiskEngineConfig(max_notional_per_order=10000.0)
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(quantity=1.0, price=50000.0),  # 50k notional
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.NOTIONAL_LIMIT_EXCEEDED in decision.violations

    def test_order_blocked_by_exposure_limit(self) -> None:
        """Test that orders exceeding exposure limits are blocked."""
        config = RiskEngineConfig(max_total_exposure=100000.0)
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(quantity=1.0, price=50000.0),
            self._create_portfolio(total_exposure=60000.0),  # Will exceed 100k
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.EXPOSURE_LIMIT_EXCEEDED in decision.violations

    def test_order_blocked_by_leverage_limit(self) -> None:
        """Test that orders exceeding leverage limits are blocked."""
        config = RiskEngineConfig(max_leverage=2.0, max_total_exposure=float("inf"))
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(quantity=5.0, price=50000.0),  # 250k notional
            self._create_portfolio(equity=100000.0, total_exposure=0.0),
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.LEVERAGE_LIMIT_EXCEEDED in decision.violations

    def test_safe_mode_reduces_position(self) -> None:
        """Test that safe mode reduces position sizes."""
        safety = SafetyController(safe_mode_position_multiplier=0.5)
        safety.activate_safe_mode(reason="test", source="test")
        engine = self._create_engine(safety=safety)

        decision = engine.assess_order(
            self._create_order(quantity=10.0),
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.adjusted_quantity == 5.0
        assert decision.metadata.get("safe_mode_active") is True

    def test_risk_engine_disabled_in_live_mode(self) -> None:
        """Test that risk engine cannot be disabled in LIVE mode."""
        set_current_mode(EnvironmentMode.LIVE)
        config = RiskEngineConfig(enable_risk_checks=False)
        engine = self._create_engine(config)

        decision = engine.assess_order(
            self._create_order(),
            self._create_portfolio(),
            self._create_market(),
        )

        assert decision.allowed is False
        assert RiskViolation.RISK_ENGINE_DISABLED in decision.violations

    def test_auto_kill_switch_on_loss_threshold(self) -> None:
        """Test automatic kill-switch activation on loss threshold."""
        config = RiskEngineConfig(kill_switch_loss_threshold=10000.0)
        safety = SafetyController()
        engine = self._create_engine(config, safety)

        # Assess with large loss
        engine.assess_order(
            self._create_order(),
            self._create_portfolio(daily_pnl=-15000.0),
            self._create_market(),
        )

        assert safety.is_kill_switch_active() is True

    def test_profit_does_not_trigger_loss_limits(self) -> None:
        """Ensure profitable days do not trigger loss-based protections."""
        config = RiskEngineConfig(max_daily_loss=1000.0, kill_switch_loss_threshold=2000.0)
        safety = SafetyController()
        engine = self._create_engine(config, safety)

        decision = engine.assess_order(
            self._create_order(),
            self._create_portfolio(daily_pnl=5000.0),
            self._create_market(),
        )

        assert safety.is_kill_switch_active() is False
        assert RiskViolation.DAILY_LOSS_LIMIT_EXCEEDED not in decision.violations

    def test_rate_limiting(self) -> None:
        """Test order rate limiting."""
        config = RiskEngineConfig(max_orders_per_minute=3)
        engine = self._create_engine(config)

        # First 3 orders should succeed
        for _ in range(3):
            decision = engine.assess_order(
                self._create_order(),
                self._create_portfolio(),
                self._create_market(),
            )
            assert decision.allowed is True

        # 4th order should be rate limited
        decision = engine.assess_order(
            self._create_order(),
            self._create_portfolio(),
            self._create_market(),
        )
        assert decision.allowed is False
        assert RiskViolation.ORDER_RATE_EXCEEDED in decision.violations

    def test_assess_after_trade(self) -> None:
        """Test post-trade risk assessment."""
        engine = self._create_engine()

        status = engine.assess_after_trade(self._create_portfolio(daily_pnl=-1000.0))

        assert status in [RiskStatus.OK, RiskStatus.WARNING]

    def test_get_status(self) -> None:
        """Test getting engine status."""
        engine = self._create_engine()
        status = engine.get_status()

        assert "enabled" in status
        assert "kill_switch_active" in status
        assert "safe_mode_active" in status
        assert "environment_mode" in status


class TestSafetyFlowIntegration:
    """Integration tests for complete safety flow scenarios."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None
        set_current_mode(EnvironmentMode.PAPER)

    def teardown_method(self) -> None:
        """Clean up after tests."""
        import tradepulse.risk.environment as env_module

        env_module._current_mode = None

    def test_normal_trading_flow(self) -> None:
        """Test normal trading flow with all orders passing."""
        config = RiskEngineConfig(
            max_position_size_default=100.0,
            max_notional_per_order=1000000.0,
            max_total_exposure=10000000.0,
        )
        safety = SafetyController()
        engine = CentralRiskEngine(config, safety_controller=safety)

        portfolio = PortfolioState(
            positions={},
            equity=1000000.0,
            peak_equity=1000000.0,
        )
        market = MarketState(prices={"BTC/USD": 50000.0})

        # Execute multiple trades
        for i in range(5):
            order = OrderContext(
                symbol="BTC/USD",
                side="buy",
                quantity=1.0,
                price=50000.0,
            )
            decision = engine.assess_order(order, portfolio, market)
            assert decision.allowed is True
            assert decision.risk_status == RiskStatus.OK

    def test_loss_triggers_safe_mode_then_kill_switch(self) -> None:
        """Test escalation from safe mode to kill switch on losses."""
        config = RiskEngineConfig(
            max_daily_loss_percent=0.10,  # 10%
            kill_switch_loss_threshold=50000.0,
            safe_mode_position_multiplier=0.25,
        )
        safety = SafetyController(safe_mode_position_multiplier=0.5)
        engine = CentralRiskEngine(config, safety_controller=safety)

        market = MarketState(prices={"BTC/USD": 50000.0})

        # Initial portfolio with some drawdown
        portfolio = PortfolioState(
            positions={},
            equity=95000.0,  # 5% down
            peak_equity=100000.0,
            daily_pnl=-5000.0,
        )

        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            portfolio,
            market,
        )
        assert decision.allowed is True

        # More losses - should trigger safe mode
        portfolio = PortfolioState(
            positions={},
            equity=88000.0,  # 12% down
            peak_equity=100000.0,
            daily_pnl=-12000.0,
        )

        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            portfolio,
            market,
        )
        # Should still allow but in safe mode or with warnings

        # Severe losses - should trigger kill switch
        portfolio = PortfolioState(
            positions={},
            equity=40000.0,
            peak_equity=100000.0,
            daily_pnl=-60000.0,
        )

        # The assess_order call should trigger auto kill-switch
        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            portfolio,
            market,
        )

        assert safety.is_kill_switch_active() is True

    def test_live_mode_requires_risk_engine(self) -> None:
        """Test that LIVE mode requires risk engine to be enabled."""
        set_current_mode(EnvironmentMode.LIVE)

        config = RiskEngineConfig(enable_risk_checks=False)
        engine = CentralRiskEngine(config, safety_controller=SafetyController())

        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            PortfolioState(equity=100000.0, peak_equity=100000.0),
            MarketState(),
        )

        assert decision.allowed is False
        assert RiskViolation.RISK_ENGINE_DISABLED in decision.violations

    def test_paper_mode_marks_orders_as_simulated(self) -> None:
        """Test that PAPER mode marks orders as simulated."""
        set_current_mode(EnvironmentMode.PAPER)

        engine = CentralRiskEngine(
            RiskEngineConfig(),
            safety_controller=SafetyController(),
        )

        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            PortfolioState(equity=100000.0, peak_equity=100000.0),
            MarketState(),
        )

        assert decision.allowed is True
        assert decision.metadata.get("simulated") is True

    def test_kill_switch_blocks_all_subsequent_orders(self) -> None:
        """Test that kill-switch blocks all orders until reset."""
        safety = SafetyController()
        engine = CentralRiskEngine(
            RiskEngineConfig(),
            safety_controller=safety,
        )

        portfolio = PortfolioState(equity=100000.0, peak_equity=100000.0)
        market = MarketState()

        # First order succeeds
        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            portfolio,
            market,
        )
        assert decision.allowed is True

        # Activate kill-switch
        safety.activate_kill_switch(reason="emergency", source="operator")

        # All subsequent orders blocked
        for _ in range(5):
            decision = engine.assess_order(
                OrderContext("BTC/USD", "buy", 1.0, 50000.0),
                portfolio,
                market,
            )
            assert decision.allowed is False
            assert decision.risk_status == RiskStatus.HALTED

        # Deactivate kill-switch
        safety.deactivate_kill_switch(source="operator", reason="resolved")

        # Orders now allowed
        decision = engine.assess_order(
            OrderContext("BTC/USD", "buy", 1.0, 50000.0),
            portfolio,
            market,
        )
        assert decision.allowed is True
