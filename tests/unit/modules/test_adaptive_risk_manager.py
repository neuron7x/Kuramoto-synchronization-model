"""
Tests for Adaptive Risk Manager Module
"""

import numpy as np

from modules.adaptive_risk_manager import (
    AdaptiveRiskManager,
    MarketCondition,
)


class TestAdaptiveRiskManager:
    """Test suite for AdaptiveRiskManager"""

    def test_initialization(self):
        """Test risk manager initialization"""
        manager = AdaptiveRiskManager(base_capital=100000.0, risk_tolerance=0.02)

        assert manager.base_capital == 100000.0
        assert manager.risk_tolerance == 0.02
        assert manager.var_window == 252
        assert manager._current_market_condition == MarketCondition.NORMAL

    def test_calculate_var_cvar(self):
        """Test VaR and CVaR calculation"""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        # Generate test returns
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 1000)

        var_95, cvar_95 = manager.calculate_var_cvar(returns, 0.95)

        assert var_95 > 0
        assert cvar_95 > 0
        assert cvar_95 >= var_95  # CVaR should be >= VaR

    def test_assess_market_condition(self):
        """Test market condition assessment"""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        # Low volatility - CALM
        condition = manager.assess_market_condition(0.005)
        assert condition == MarketCondition.CALM

        # Normal volatility
        condition = manager.assess_market_condition(0.01)
        assert condition == MarketCondition.NORMAL

        # High volatility - VOLATILE
        condition = manager.assess_market_condition(0.02)
        assert condition == MarketCondition.VOLATILE

        # Extreme volatility
        condition = manager.assess_market_condition(0.05)
        assert condition == MarketCondition.EXTREME

    def test_calculate_position_size(self):
        """Test position size calculation"""
        manager = AdaptiveRiskManager(base_capital=100000.0, risk_tolerance=0.02)

        size = manager.calculate_position_size(
            symbol="BTCUSD", price=50000.0, volatility=0.01, confidence=0.8
        )

        assert size > 0
        assert size <= manager.base_capital * 0.2  # Max 20% per position
