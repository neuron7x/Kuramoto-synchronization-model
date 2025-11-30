# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive configuration validation tests for module and controller configurations.

This module provides enhanced testing of configuration validation across
the TradePulse system, ensuring robust parameter validation and error handling.

Test Coverage:
- Configuration boundary conditions
- Parameter type validation
- Range validation for numeric parameters
- Required vs optional field handling
- Error message clarity
"""

from __future__ import annotations

import math

import numpy as np

from modules.adaptive_risk_manager import (
    AdaptiveRiskManager,
    MarketCondition,
    PositionLimit,
    RiskLevel,
)
from modules.agent_coordinator import (
    AgentCoordinator,
    AgentStatus,
    AgentType,
    Priority,
)
from modules.dynamic_position_sizer import (
    DynamicPositionSizer,
    SizingMethod,
)
from modules.market_regime_analyzer import (
    MarketRegimeAnalyzer,
    RegimeType,
    TrendStrength,
)


class TestAdaptiveRiskManagerConfigValidation:
    """Configuration validation tests for AdaptiveRiskManager."""

    def test_initialization_with_default_parameters(self):
        """Test initialization with default parameter values."""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        assert manager.base_capital == 100000.0
        assert manager.risk_tolerance == 0.02  # default
        assert manager.var_window == 252  # default
        assert manager.volatility_window == 20  # default
        assert manager.enable_tacl_integration is True  # default

    def test_initialization_with_custom_parameters(self):
        """Test initialization with custom parameter values."""
        manager = AdaptiveRiskManager(
            base_capital=50000.0,
            risk_tolerance=0.05,
            var_window=100,
            volatility_window=10,
            enable_tacl_integration=False,
        )

        assert manager.base_capital == 50000.0
        assert manager.risk_tolerance == 0.05
        assert manager.var_window == 100
        assert manager.volatility_window == 10
        assert manager.enable_tacl_integration is False

    def test_boundary_capital_values(self):
        """Test risk manager with boundary capital values."""
        # Small capital
        manager_small = AdaptiveRiskManager(base_capital=100.0)
        assert manager_small.base_capital == 100.0

        # Large capital
        manager_large = AdaptiveRiskManager(base_capital=1_000_000_000.0)
        assert manager_large.base_capital == 1_000_000_000.0

    def test_risk_tolerance_boundaries(self):
        """Test risk tolerance at boundary values."""
        # Very small tolerance
        manager_small = AdaptiveRiskManager(base_capital=100000.0, risk_tolerance=0.001)
        assert manager_small.risk_tolerance == 0.001

        # Larger tolerance
        manager_large = AdaptiveRiskManager(base_capital=100000.0, risk_tolerance=0.1)
        assert manager_large.risk_tolerance == 0.1

    def test_var_cvar_with_insufficient_data(self):
        """Test VaR/CVaR calculation returns zeros with insufficient data."""
        manager = AdaptiveRiskManager(base_capital=100000.0)
        returns = np.array([0.01, 0.02])  # Only 2 data points

        var, cvar = manager.calculate_var_cvar(returns, 0.95)

        assert var == 0.0
        assert cvar == 0.0

    def test_var_cvar_with_empty_returns(self):
        """Test VaR/CVaR calculation with empty returns array."""
        manager = AdaptiveRiskManager(base_capital=100000.0)
        returns = np.array([])

        var, cvar = manager.calculate_var_cvar(returns, 0.95)

        assert var == 0.0
        assert cvar == 0.0

    def test_market_condition_classification_boundaries(self):
        """Test market condition classification at boundary volatilities."""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        # Test each boundary precisely with sufficient margin for float precision
        # Calm: annual_vol < 0.15
        calm_boundary = 0.14 / np.sqrt(252)  # Well below 0.15
        assert manager.assess_market_condition(calm_boundary) == MarketCondition.CALM

        # Normal: 0.15 <= annual_vol < 0.25
        normal_mid = 0.20 / np.sqrt(252)  # Middle of normal range
        assert manager.assess_market_condition(normal_mid) == MarketCondition.NORMAL

        # Volatile: 0.25 <= annual_vol < 0.40
        volatile_mid = 0.32 / np.sqrt(252)  # Middle of volatile range
        assert manager.assess_market_condition(volatile_mid) == MarketCondition.VOLATILE

        # Extreme: annual_vol >= 0.40
        extreme_value = 0.50 / np.sqrt(252)  # Well above 0.40
        assert manager.assess_market_condition(extreme_value) == MarketCondition.EXTREME

    def test_position_limit_model_validation(self):
        """Test PositionLimit model validates field constraints."""
        # Valid position limit
        limit = PositionLimit(
            symbol="BTCUSD",
            max_position_size=10000.0,
            max_leverage=5.0,
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
        )
        assert limit.symbol == "BTCUSD"
        assert limit.max_leverage == 5.0

    def test_portfolio_risk_utilization_boundaries(self):
        """Test portfolio risk assessment at utilization boundaries."""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        # Test empty portfolio
        empty_risk = manager.assess_portfolio_risk({}, {})
        assert empty_risk.utilization_pct == 0.0
        assert empty_risk.risk_level == RiskLevel.LOW

        # Test with positions
        positions = {"BTCUSD": 1.0, "ETHUSD": 2.0}
        prices = {"BTCUSD": 50000.0, "ETHUSD": 3000.0}
        portfolio_risk = manager.assess_portfolio_risk(positions, prices)

        assert portfolio_risk.total_exposure > 0
        assert portfolio_risk.active_positions == 2


class TestDynamicPositionSizerConfigValidation:
    """Configuration validation tests for DynamicPositionSizer."""

    def test_initialization_with_all_methods(self):
        """Test initialization with each sizing method."""
        for method in SizingMethod:
            sizer = DynamicPositionSizer(
                base_capital=100000.0,
                default_method=method,
            )
            assert sizer.default_method == method

    def test_kelly_calculation_edge_cases(self):
        """Test Kelly criterion calculation at edge conditions."""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        # Perfect win rate (boundary)
        kelly_perfect = sizer.calculate_kelly_size(1.0, 0.02, 0.01)
        assert kelly_perfect == 0.0  # win_rate >= 1 returns 0

        # Win rate just above zero
        kelly_low = sizer.calculate_kelly_size(0.01, 0.02, 0.01)
        assert kelly_low == 0.0  # Expected to be 0 due to negative Kelly

    def test_kelly_with_high_reward_to_risk(self):
        """Test Kelly with favorable reward-to-risk ratio."""
        sizer = DynamicPositionSizer(base_capital=100000.0, kelly_fraction=0.25)

        # High reward-to-risk
        kelly = sizer.calculate_kelly_size(
            win_rate=0.55,
            avg_win=0.04,
            avg_loss=0.01,
            fractional=True,
        )

        # Kelly should be positive for profitable strategy
        assert kelly > 0
        # Maximum uncapped Kelly is 0.5, with fractional Kelly (0.25) the cap is 0.125
        max_kelly_cap = 0.125
        assert kelly <= max_kelly_cap

    def test_volatility_adjustment_boundaries(self):
        """Test volatility adjustment at extreme values."""
        sizer = DynamicPositionSizer(base_capital=100000.0, volatility_target=0.15)
        base_size = 10000.0

        # Very low volatility (should increase size significantly)
        size_low = sizer.calculate_volatility_adjusted_size(0.001, base_size)
        assert size_low > base_size  # Size should increase

        # Very high volatility (should decrease size)
        size_high = sizer.calculate_volatility_adjusted_size(0.1, base_size)
        assert size_high < base_size  # Size should decrease

    def test_risk_parity_with_empty_portfolio(self):
        """Test risk parity sizing with empty portfolio volatilities."""
        sizer = DynamicPositionSizer(base_capital=100000.0, max_position_pct=0.1)

        size = sizer.calculate_risk_parity_size("BTCUSD", 0.02, {})

        # Should return max position size when no portfolio data
        assert size == sizer.base_capital * sizer.max_position_pct

    def test_risk_parity_with_zero_volatility(self):
        """Test risk parity sizing when volatility is zero."""
        sizer = DynamicPositionSizer(base_capital=100000.0, max_position_pct=0.1)

        portfolio_vols = {"BTCUSD": 0.02, "ETHUSD": 0.0}
        size = sizer.calculate_risk_parity_size("BTCUSD", 0.0, portfolio_vols)

        # Should return max position size for zero volatility
        assert size == sizer.base_capital * sizer.max_position_pct


class TestMarketRegimeAnalyzerConfigValidation:
    """Configuration validation tests for MarketRegimeAnalyzer."""

    def test_initialization_parameters(self):
        """Test analyzer initialization with custom parameters."""
        analyzer = MarketRegimeAnalyzer(
            regime_window=50,
            transition_threshold=0.8,
            min_regime_duration=5,
        )

        assert analyzer.regime_window == 50
        assert analyzer.transition_threshold == 0.8
        assert analyzer.min_regime_duration == 5

    def test_hurst_exponent_with_minimal_data(self):
        """Test Hurst exponent calculation with minimal data."""
        analyzer = MarketRegimeAnalyzer()

        # Less than 20 data points
        prices_short = np.array([100.0, 101.0, 102.0])
        hurst = analyzer.calculate_hurst_exponent(prices_short)

        # Should return 0.5 (random walk) for insufficient data
        assert hurst == 0.5

    def test_hurst_exponent_bounds(self):
        """Test Hurst exponent is always within [0, 1]."""
        analyzer = MarketRegimeAnalyzer()

        # Random prices
        np.random.seed(42)
        prices = np.cumsum(np.random.normal(0, 1, 200)) + 100

        hurst = analyzer.calculate_hurst_exponent(prices)

        assert 0.0 <= hurst <= 1.0

    def test_adf_test_with_minimal_data(self):
        """Test ADF test with minimal data returns defaults."""
        analyzer = MarketRegimeAnalyzer()

        prices_short = np.array([100.0, 101.0, 102.0])
        stat, pvalue = analyzer.augmented_dickey_fuller_test(prices_short)

        assert stat == 0.0
        assert pvalue == 1.0

    def test_trend_strength_classification_all_levels(self):
        """Test trend strength classification covers all levels."""
        analyzer = MarketRegimeAnalyzer()

        # Very weak trend
        prices_flat = np.full(100, 100.0)
        _, strength = analyzer.calculate_trend_strength(prices_flat)
        assert strength == TrendStrength.VERY_WEAK

        # Strong trend
        prices_strong = np.linspace(100, 200, 100)
        _, strength = analyzer.calculate_trend_strength(prices_strong)
        assert strength in [TrendStrength.STRONG, TrendStrength.VERY_STRONG]

    def test_regime_classification_unknown_on_insufficient_data(self):
        """Test regime classification returns UNKNOWN with insufficient data."""
        analyzer = MarketRegimeAnalyzer(min_regime_duration=10)

        prices_short = np.array([100.0, 101.0, 102.0])
        metrics = analyzer.classify_regime(prices_short)

        assert metrics.regime_type == RegimeType.UNKNOWN
        assert metrics.regime_confidence == 0.0


class TestAgentCoordinatorConfigValidation:
    """Configuration validation tests for AgentCoordinator."""

    def test_initialization_parameters(self):
        """Test coordinator initialization parameters."""
        coordinator = AgentCoordinator(
            max_concurrent_tasks=5,
            enable_conflict_resolution=False,
        )

        assert coordinator.max_concurrent_tasks == 5
        assert coordinator.enable_conflict_resolution is False

    def test_agent_types_coverage(self):
        """Test all agent types can be registered."""

        class MockHandler:
            pass

        coordinator = AgentCoordinator()

        for agent_type in AgentType:
            agent_id = f"agent_{agent_type.value}"
            coordinator.register_agent(
                agent_id=agent_id,
                agent_type=agent_type,
                name=f"Test {agent_type.value}",
                description=f"Test agent for {agent_type.value}",
                handler=MockHandler(),
            )

        # All agent types should be registered
        assert len(coordinator._agents) == len(AgentType)

    def test_priority_ordering(self):
        """Test priority values are correctly ordered."""
        assert Priority.LOW.value < Priority.NORMAL.value
        assert Priority.NORMAL.value < Priority.HIGH.value
        assert Priority.HIGH.value < Priority.CRITICAL.value
        assert Priority.CRITICAL.value < Priority.EMERGENCY.value

    def test_status_transitions(self):
        """Test agent status can be updated to all states."""

        class MockHandler:
            pass

        coordinator = AgentCoordinator()
        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Test Agent",
            "Description",
            MockHandler(),
        )

        for status in AgentStatus:
            coordinator.update_agent_status("agent_1", status)
            assert coordinator._agents["agent_1"].status == status

    def test_dependency_check_with_missing_dependency(self):
        """Test dependency check fails when dependency is missing."""

        class MockHandler:
            pass

        coordinator = AgentCoordinator()
        metadata = coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Test Agent",
            "Description",
            MockHandler(),
            dependencies={"missing_agent"},
        )

        # Dependency check should fail
        result = coordinator._check_dependencies(metadata)
        assert result is False

    def test_dependency_check_with_error_dependency(self):
        """Test dependency check fails when dependency is in ERROR state."""

        class MockHandler:
            pass

        coordinator = AgentCoordinator()
        coordinator.register_agent(
            "dependency_agent",
            AgentType.RISK_MANAGER,
            "Dependency Agent",
            "Description",
            MockHandler(),
        )
        coordinator.update_agent_status("dependency_agent", AgentStatus.ERROR)

        metadata = coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Test Agent",
            "Description",
            MockHandler(),
            dependencies={"dependency_agent"},
        )

        # Dependency check should fail due to ERROR status
        result = coordinator._check_dependencies(metadata)
        assert result is False


class TestNumericPrecisionValidation:
    """Tests for numeric precision in calculations."""

    def test_var_cvar_precision(self):
        """Test VaR/CVaR calculation precision."""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        # Use known distribution
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 1000)

        var_95, cvar_95 = manager.calculate_var_cvar(returns, 0.95)

        # VaR and CVaR should be finite
        assert math.isfinite(var_95)
        assert math.isfinite(cvar_95)
        # CVaR should be >= VaR
        assert cvar_95 >= var_95 - 1e-10  # Small tolerance for float comparison

    def test_risk_metrics_all_finite(self):
        """Test all risk metrics are finite values."""
        manager = AdaptiveRiskManager(base_capital=100000.0)

        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100)

        metrics = manager.calculate_risk_metrics(returns)

        assert math.isfinite(metrics.var_95)
        assert math.isfinite(metrics.cvar_95)
        assert math.isfinite(metrics.var_99)
        assert math.isfinite(metrics.cvar_99)
        assert math.isfinite(metrics.sharpe_ratio)
        assert math.isfinite(metrics.sortino_ratio)
        assert math.isfinite(metrics.max_drawdown)
        assert math.isfinite(metrics.volatility)

    def test_position_size_precision(self):
        """Test position size calculations maintain precision."""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        result = sizer.calculate_adaptive_size(
            symbol="BTCUSD",
            price=50000.0,
            volatility=0.015,
            confidence=0.8,
            win_rate=0.55,
            avg_win=0.02,
            avg_loss=0.01,
        )

        # All result values should be finite
        assert math.isfinite(result.recommended_size)
        assert math.isfinite(result.kelly_fraction)
        assert math.isfinite(result.volatility_adjustment)
        assert math.isfinite(result.risk_adjusted_size)

    def test_hurst_exponent_numeric_stability(self):
        """Test Hurst exponent calculation is numerically stable."""
        analyzer = MarketRegimeAnalyzer()

        # Test with various price patterns
        np.random.seed(42)
        prices_normal = np.cumsum(np.random.normal(0, 1, 200)) + 100
        prices_uniform = np.cumsum(np.random.uniform(-1, 1, 200)) + 100
        prices_trending = np.linspace(100, 200, 200)

        for prices in [prices_normal, prices_uniform, prices_trending]:
            hurst = analyzer.calculate_hurst_exponent(prices)
            assert math.isfinite(hurst)
            assert 0.0 <= hurst <= 1.0
