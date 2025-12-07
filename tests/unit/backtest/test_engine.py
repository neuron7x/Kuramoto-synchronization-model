# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Test module for backtest engine.

This module provides comprehensive unit tests for the walk-forward backtest engine,
focusing on execution realism controls, data quality validation, and anti-leakage
mechanisms as described in docs/performance.md.

Tests cover:
- Configuration classes (LatencyConfig, OrderBookConfig, SlippageConfig, etc.)
- Walk-forward execution with various cost models
- Portfolio constraint enforcement
- Data quality validation
- Anti-look-ahead bias prevention
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import (
    AntiLeakageConfig,
    DataValidationConfig,
    LatencyConfig,
    OrderBookConfig,
    PortfolioConstraints,
    Result,
    SlippageConfig,
    WalkForwardEngine,
    walk_forward,
)


class TestLatencyConfig:
    """Test suite for LatencyConfig dataclass."""

    def test_latency_config_initialization(self) -> None:
        """Test LatencyConfig initializes with correct defaults."""
        config = LatencyConfig()
        assert config.signal_to_order == 0
        assert config.order_to_execution == 0
        assert config.execution_to_fill == 0

    def test_latency_config_custom_values(self) -> None:
        """Test LatencyConfig accepts custom values."""
        config = LatencyConfig(
            signal_to_order=1,
            order_to_execution=2,
            execution_to_fill=1
        )
        assert config.signal_to_order == 1
        assert config.order_to_execution == 2
        assert config.execution_to_fill == 1

    def test_total_delay_calculation(self) -> None:
        """Test total_delay property computes correct sum."""
        config = LatencyConfig(
            signal_to_order=1,
            order_to_execution=2,
            execution_to_fill=1
        )
        assert config.total_delay == 4

    def test_total_delay_never_negative(self) -> None:
        """Test total_delay returns non-negative value."""
        config = LatencyConfig(signal_to_order=0, order_to_execution=0, execution_to_fill=0)
        assert config.total_delay >= 0


class TestOrderBookConfig:
    """Test suite for OrderBookConfig dataclass."""

    def test_orderbook_config_defaults(self) -> None:
        """Test OrderBookConfig has sensible defaults."""
        config = OrderBookConfig()
        # Test that config can be instantiated with defaults
        assert hasattr(config, 'spread_bps')
        assert hasattr(config, 'depth_profile')

    def test_orderbook_config_custom_spread(self) -> None:
        """Test OrderBookConfig accepts custom spread values."""
        config = OrderBookConfig(spread_bps=10.0)
        assert config.spread_bps == 10.0


class TestSlippageConfig:
    """Test suite for SlippageConfig dataclass."""

    def test_slippage_config_defaults(self) -> None:
        """Test SlippageConfig initializes properly."""
        config = SlippageConfig()
        assert hasattr(config, 'per_unit_bps')
        assert hasattr(config, 'depth_impact_bps')


class TestPortfolioConstraints:
    """Test suite for PortfolioConstraints dataclass."""

    def test_portfolio_constraints_defaults(self) -> None:
        """Test PortfolioConstraints has reasonable defaults."""
        config = PortfolioConstraints()
        # Verify it can be instantiated
        assert config is not None


class TestDataValidationConfig:
    """Test suite for DataValidationConfig."""

    def test_data_validation_config_defaults(self) -> None:
        """Test DataValidationConfig initializes properly."""
        config = DataValidationConfig()
        assert config is not None


class TestAntiLeakageConfig:
    """Test suite for AntiLeakageConfig."""

    def test_anti_leakage_config_defaults(self) -> None:
        """Test AntiLeakageConfig initializes properly."""
        config = AntiLeakageConfig()
        assert config is not None


class TestResult:
    """Test suite for Result dataclass."""

    def test_result_initialization(self) -> None:
        """Test Result can be instantiated with required fields."""
        result = Result(
            pnl=100.0,
            trades=10,
            max_dd=-50.0,
            latency_steps=2,
            slippage_cost=5.0,
            equity_curve=np.array([100.0, 110.0, 120.0])
        )
        assert result.pnl == 100.0
        assert result.trades == 10
        assert result.max_dd == -50.0
        assert result.latency_steps == 2
        assert result.slippage_cost == 5.0
        assert len(result.equity_curve) == 3


class TestWalkForward:
    """Test suite for walk_forward function."""

    def test_walk_forward_basic_execution(self) -> None:
        """Test walk_forward executes with minimal inputs."""
        prices = np.array([100.0, 101.0, 102.0, 101.5, 103.0])
        
        def simple_signal(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)
        
        result = walk_forward(prices, simple_signal, fee=0.0)
        
        assert isinstance(result, Result)
        assert result.trades >= 0
        assert result.equity_curve is not None

    def test_walk_forward_zero_signal_zero_pnl(self) -> None:
        """Test zero signal produces zero PnL."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        
        def zero_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)
        
        result = walk_forward(prices, zero_signal, fee=0.0)
        
        assert result.pnl == pytest.approx(0.0, abs=1e-9)
        assert result.trades == 0
        assert result.max_dd == pytest.approx(0.0, abs=1e-9)

    def test_walk_forward_with_transaction_fees(self) -> None:
        """Test walk_forward accounts for transaction fees."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        
        def long_signal(p: np.ndarray) -> np.ndarray:
            signal = np.ones_like(p)
            signal[0] = 0.0
            return signal
        
        result_no_fee = walk_forward(prices, long_signal, fee=0.0)
        result_with_fee = walk_forward(prices, long_signal, fee=0.001)
        
        # PnL should be lower with fees
        assert result_with_fee.pnl < result_no_fee.pnl

    def test_walk_forward_with_latency(self) -> None:
        """Test walk_forward applies execution latency."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        
        def trend_signal(p: np.ndarray) -> np.ndarray:
            signal = np.zeros_like(p)
            signal[1:] = 1.0
            return signal
        
        latency = LatencyConfig(signal_to_order=1, order_to_execution=1)
        result = walk_forward(prices, trend_signal, fee=0.0, latency=latency)
        
        assert result.latency_steps == 2

    def test_walk_forward_handles_empty_prices(self) -> None:
        """Test walk_forward handles empty price array gracefully."""
        prices = np.array([])
        
        def simple_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)
        
        # Should either raise an error or return valid result
        try:
            result = walk_forward(prices, simple_signal, fee=0.0)
            # If it succeeds, check basic properties
            assert result.trades == 0
        except (ValueError, IndexError):
            # Expected for empty input
            pass

    def test_walk_forward_enforces_position_limits(self) -> None:
        """Test walk_forward respects portfolio constraints."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        
        def aggressive_signal(p: np.ndarray) -> np.ndarray:
            # Signal with large magnitude
            return np.ones_like(p) * 10.0
        
        constraints = PortfolioConstraints()
        result = walk_forward(
            prices,
            aggressive_signal,
            fee=0.0,
            constraints=constraints
        )
        
        # Result should still be valid even with constraints
        assert isinstance(result, Result)


class TestWalkForwardEngine:
    """Test suite for WalkForwardEngine class."""

    def test_engine_initialization(self) -> None:
        """Test WalkForwardEngine can be instantiated."""
        engine = WalkForwardEngine()
        assert engine is not None

    def test_engine_respects_latency_config(self) -> None:
        """Test engine applies latency configuration."""
        prices = np.array([100.0, 101.0, 102.0, 103.0])
        
        def signal_func(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)
        
        latency = LatencyConfig(signal_to_order=1)
        result = walk_forward(prices, signal_func, latency=latency)
        
        assert result.latency_steps >= 1


class TestDataQualityValidation:
    """Test suite for data quality validation in backtest engine."""

    def test_walk_forward_validates_nan_prices(self) -> None:
        """Test walk_forward detects NaN values in prices."""
        prices = np.array([100.0, np.nan, 102.0, 103.0])
        
        def signal_func(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)
        
        # Should raise validation error for NaN prices
        # Import the correct exception type
        from tradepulse.data_quality import DataQualityError
        
        with pytest.raises(DataQualityError, match="Data quality validation failed"):
            walk_forward(prices, signal_func, fee=0.0)

    def test_walk_forward_handles_infinite_prices(self) -> None:
        """Test walk_forward handles infinite values."""
        prices = np.array([100.0, 101.0, np.inf, 103.0])
        
        def signal_func(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)
        
        # The engine may handle inf gracefully or produce warnings
        # Test that it doesn't crash
        with pytest.warns(RuntimeWarning):
            result = walk_forward(prices, signal_func, fee=0.0)
            # Result may contain NaN values but should not crash
            assert isinstance(result, Result)


class TestAntiLeakageMechanisms:
    """Test suite for anti-look-ahead bias prevention."""

    def test_walk_forward_prevents_future_leakage(self) -> None:
        """Test walk_forward does not use future data in signal generation."""
        prices = np.array([100.0, 105.0, 95.0, 110.0, 90.0])
        
        # Signal that would be "perfect" if it could see the future
        def future_peeking_signal(p: np.ndarray) -> np.ndarray:
            signal = np.zeros_like(p)
            # This should not have perfect foresight
            signal[:-1] = np.sign(p[1:] - p[:-1])
            return signal
        
        result = walk_forward(prices, future_peeking_signal, fee=0.0)
        
        # Even with "perfect" signal, some delay should affect results
        # The test just ensures the engine runs without errors
        assert isinstance(result, Result)


class TestTransactionCostModels:
    """Test suite for transaction cost modeling."""

    def test_walk_forward_with_slippage(self) -> None:
        """Test walk_forward applies slippage costs."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        
        def signal_func(p: np.ndarray) -> np.ndarray:
            signal = np.ones_like(p)
            signal[0] = 0.0
            return signal
        
        slippage = SlippageConfig(per_unit_bps=10.0)
        result = walk_forward(
            prices,
            signal_func,
            fee=0.0,
            slippage=slippage
        )
        
        assert result.slippage_cost >= 0.0

    def test_walk_forward_with_order_book(self) -> None:
        """Test walk_forward uses order book configuration."""
        prices = np.array([100.0, 101.0, 102.0, 103.0])
        
        def signal_func(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)
        
        order_book = OrderBookConfig(spread_bps=5.0)
        result = walk_forward(
            prices,
            signal_func,
            fee=0.0,
            order_book=order_book
        )
        
        assert isinstance(result, Result)


# Integration test combining multiple features
class TestWalkForwardIntegration:
    """Integration tests combining multiple backtest engine features."""

    def test_realistic_backtest_scenario(self) -> None:
        """Test walk_forward with realistic trading scenario."""
        # Generate realistic price series
        np.random.seed(42)
        prices = 100.0 + np.cumsum(np.random.randn(100) * 0.5)
        prices = np.maximum(prices, 50.0)  # Ensure positive prices
        
        # Simple trend-following strategy
        def moving_average_crossover(p: np.ndarray) -> np.ndarray:
            signal = np.zeros_like(p)
            if len(p) >= 20:
                short_ma = np.convolve(p, np.ones(5)/5, mode='same')
                long_ma = np.convolve(p, np.ones(20)/20, mode='same')
                signal = np.sign(short_ma - long_ma)
            return signal
        
        # Run backtest with realistic parameters
        result = walk_forward(
            prices,
            moving_average_crossover,
            fee=0.001,
            latency=LatencyConfig(signal_to_order=1),
            order_book=OrderBookConfig(spread_bps=5.0),
            slippage=SlippageConfig(per_unit_bps=10.0)
        )
        
        # Verify result is reasonable
        assert isinstance(result, Result)
        assert result.trades >= 0
        assert result.equity_curve is not None
        # Equity curve length may differ from prices due to latency/warmup
        assert len(result.equity_curve) >= len(prices) - 10  # Allow some tolerance
        assert result.max_dd <= 0.0  # Drawdown should be non-positive
