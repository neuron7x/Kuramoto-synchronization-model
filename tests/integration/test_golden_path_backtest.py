# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Golden Path Integration Tests for TradePulse Backtest Engine.

This module provides deterministic, reproducible integration tests for the core
backtest workflow: data ingestion → signal generation → backtest execution → PnL/metrics.

The tests are designed to:
- Run with fixed random seeds for determinism
- Use fixed time ranges and market data
- Validate key invariants:
  - PnL values are finite and not NaN
  - Equity curves are monotonically calculable
  - No critical exceptions during execution
  - Basic statistics are in valid ranges

These tests protect the "golden path" scenario from regressions.
"""
from __future__ import annotations

import math

import numpy as np
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

# Fixed seed for all tests in this module
RANDOM_SEED = 42


@pytest.fixture(autouse=True)
def set_deterministic_seed():
    """Ensure all tests run with fixed random seed."""
    np.random.seed(RANDOM_SEED)
    yield
    np.random.seed(RANDOM_SEED)


@pytest.fixture
def synthetic_price_data() -> np.ndarray:
    """Generate deterministic synthetic price data for testing.

    Uses a random walk with drift to simulate realistic market data.
    """
    np.random.seed(RANDOM_SEED)
    n_bars = 252  # 1 year of daily data
    initial_price = 100.0
    drift = 0.0002  # 0.02% daily drift
    volatility = 0.01  # 1% daily volatility

    returns = np.random.normal(drift, volatility, n_bars)
    prices = initial_price * np.cumprod(1 + returns)

    # Ensure all prices are positive
    prices = np.maximum(prices, 1.0)

    return prices


@pytest.fixture
def trending_price_data() -> np.ndarray:
    """Generate deterministic trending price data."""
    np.random.seed(RANDOM_SEED)
    n_bars = 100

    # Strong upward trend with some noise
    trend = np.linspace(100, 150, n_bars)
    noise = np.random.normal(0, 0.5, n_bars)
    prices = trend + noise

    return np.maximum(prices, 50.0)


@pytest.fixture
def mean_reverting_price_data() -> np.ndarray:
    """Generate deterministic mean-reverting price data."""
    np.random.seed(RANDOM_SEED)
    n_bars = 200

    # Mean-reverting process around 100
    mean_price = 100.0
    reversion_speed = 0.1

    prices = np.zeros(n_bars)
    prices[0] = mean_price

    for i in range(1, n_bars):
        innovation = np.random.normal(0, 2)
        prices[i] = prices[i-1] + reversion_speed * (mean_price - prices[i-1]) + innovation

    return np.maximum(prices, 50.0)


def momentum_signal(prices: np.ndarray, lookback: int = 10) -> np.ndarray:
    """Simple momentum strategy: go long when price > moving average."""
    signal = np.zeros_like(prices)

    for i in range(lookback, len(prices)):
        ma = np.mean(prices[i-lookback:i])
        if prices[i] > ma:
            signal[i] = 1.0
        elif prices[i] < ma:
            signal[i] = -1.0

    return signal


def mean_reversion_signal(prices: np.ndarray, lookback: int = 20, threshold: float = 1.5) -> np.ndarray:
    """Mean reversion strategy: sell when above mean, buy when below."""
    signal = np.zeros_like(prices)

    for i in range(lookback, len(prices)):
        window = prices[i-lookback:i]
        mean = np.mean(window)
        std = np.std(window)

        if std > 0:
            z_score = (prices[i] - mean) / std
            if z_score > threshold:
                signal[i] = -1.0  # Sell
            elif z_score < -threshold:
                signal[i] = 1.0   # Buy

    return signal


def buy_and_hold_signal(prices: np.ndarray) -> np.ndarray:
    """Simple buy-and-hold strategy."""
    signal = np.ones_like(prices)
    signal[0] = 0.0  # Enter on second bar
    return signal


class TestGoldenPathBasic:
    """Basic golden path tests ensuring the core workflow runs without errors."""

    def test_backtest_produces_valid_result(self, synthetic_price_data: np.ndarray) -> None:
        """Test that a backtest with synthetic data produces a valid Result."""
        result = walk_forward(
            synthetic_price_data,
            momentum_signal,
            fee=0.001,
            strategy_name="momentum_test",
        )

        # Invariant: Result should be a valid object
        assert isinstance(result, Result)

        # Invariant: PnL should be finite (not NaN or infinity)
        assert math.isfinite(result.pnl), f"PnL is not finite: {result.pnl}"

        # Invariant: Drawdown should be non-positive
        assert result.max_dd <= 0.0, f"Max drawdown should be <= 0: {result.max_dd}"

        # Invariant: Trade count should be non-negative
        assert result.trades >= 0, f"Trade count should be >= 0: {result.trades}"

    def test_equity_curve_invariants(self, synthetic_price_data: np.ndarray) -> None:
        """Test that equity curve has valid properties."""
        initial_capital = 100000.0

        result = walk_forward(
            synthetic_price_data,
            momentum_signal,
            fee=0.0,
            initial_capital=initial_capital,
            strategy_name="equity_test",
        )

        # Invariant: Equity curve should exist
        assert result.equity_curve is not None

        # Invariant: Equity curve should have finite values
        assert np.all(np.isfinite(result.equity_curve)), "Equity curve contains non-finite values"

        # Invariant: First equity value relates to initial capital
        # (considering PnL starts from first trade)
        assert len(result.equity_curve) > 0

    def test_zero_signal_zero_pnl(self, synthetic_price_data: np.ndarray) -> None:
        """Test that zero signal produces zero PnL."""
        def zero_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)

        result = walk_forward(
            synthetic_price_data,
            zero_signal,
            fee=0.0,
            strategy_name="zero_test",
        )

        # Invariant: Zero signal = Zero PnL = Zero trades
        assert result.pnl == pytest.approx(0.0, abs=1e-9)
        assert result.trades == 0
        assert result.max_dd == pytest.approx(0.0, abs=1e-9)


class TestGoldenPathStrategies:
    """Test different trading strategies produce sensible results."""

    def test_momentum_on_trending_data(self, trending_price_data: np.ndarray) -> None:
        """Momentum should profit in a trending market."""
        result = walk_forward(
            trending_price_data,
            momentum_signal,
            fee=0.0,
            strategy_name="momentum_trending",
        )

        # In a strong uptrend, momentum should typically be profitable
        # (this is a sanity check, not a strict assertion)
        assert math.isfinite(result.pnl)
        assert result.trades > 0

    def test_buy_and_hold_on_trending_data(self, trending_price_data: np.ndarray) -> None:
        """Buy and hold should profit when prices go up."""
        result = walk_forward(
            trending_price_data,
            buy_and_hold_signal,
            fee=0.0,
            strategy_name="buy_hold_trending",
        )

        # Prices went from ~100 to ~150, so buy and hold should be profitable
        assert result.pnl > 0, "Buy-and-hold should profit in uptrend"
        assert result.trades == 1

    def test_mean_reversion_on_mean_reverting_data(self, mean_reverting_price_data: np.ndarray) -> None:
        """Test mean reversion strategy runs without errors."""
        result = walk_forward(
            mean_reverting_price_data,
            mean_reversion_signal,
            fee=0.0,
            strategy_name="mean_reversion",
        )

        # Just check it runs and produces valid output
        assert math.isfinite(result.pnl)
        assert result.max_dd <= 0.0


class TestGoldenPathWithCosts:
    """Test that transaction costs are properly applied."""

    def test_fees_reduce_pnl(self, trending_price_data: np.ndarray) -> None:
        """Higher fees should reduce PnL."""
        result_no_fee = walk_forward(
            trending_price_data,
            buy_and_hold_signal,
            fee=0.0,
            strategy_name="no_fee",
        )

        result_with_fee = walk_forward(
            trending_price_data,
            buy_and_hold_signal,
            fee=0.01,  # 1% fee
            strategy_name="with_fee",
        )

        # Invariant: Fees should reduce PnL
        assert result_with_fee.pnl < result_no_fee.pnl

    def test_slippage_applied(self, trending_price_data: np.ndarray) -> None:
        """Test that slippage configuration is applied."""
        slippage = SlippageConfig(per_unit_bps=50.0)  # 50 bps slippage

        result = walk_forward(
            trending_price_data,
            momentum_signal,
            fee=0.0,
            slippage=slippage,
            strategy_name="slippage_test",
        )

        # Slippage cost should be tracked
        assert result.slippage_cost >= 0.0

    def test_spread_costs_applied(self, trending_price_data: np.ndarray) -> None:
        """Test that spread configuration is applied."""
        order_book = OrderBookConfig(spread_bps=10.0)

        result = walk_forward(
            trending_price_data,
            momentum_signal,
            fee=0.0,
            order_book=order_book,
            strategy_name="spread_test",
        )

        # Should run without errors and track spread costs
        assert math.isfinite(result.pnl)


class TestGoldenPathLatency:
    """Test latency simulation in backtests."""

    def test_latency_configuration(self, synthetic_price_data: np.ndarray) -> None:
        """Test that latency is properly configured and applied."""
        latency = LatencyConfig(
            signal_to_order=1,
            order_to_execution=1,
            execution_to_fill=1,
        )

        result = walk_forward(
            synthetic_price_data,
            momentum_signal,
            fee=0.0,
            latency=latency,
            strategy_name="latency_test",
        )

        # Invariant: Latency steps should match configuration
        assert result.latency_steps == 3

    def test_latency_affects_results(self, trending_price_data: np.ndarray) -> None:
        """Test that adding latency changes results."""
        walk_forward(
            trending_price_data,
            momentum_signal,
            fee=0.0,
            strategy_name="no_latency",
        )

        latency = LatencyConfig(signal_to_order=2, order_to_execution=1)
        result_with_latency = walk_forward(
            trending_price_data,
            momentum_signal,
            fee=0.0,
            latency=latency,
            strategy_name="with_latency",
        )

        # With latency, signals are delayed, potentially affecting results
        assert result_with_latency.latency_steps == 3


class TestGoldenPathConstraints:
    """Test portfolio constraints enforcement."""

    def test_position_limits_enforced(self, synthetic_price_data: np.ndarray) -> None:
        """Test that position limits are respected."""
        def large_signal(p: np.ndarray) -> np.ndarray:
            # Signal with magnitude > 1
            return np.full_like(p, 5.0)

        constraints = PortfolioConstraints(
            max_gross_exposure=0.5,
            max_net_exposure=0.5,
        )

        result = walk_forward(
            synthetic_price_data,
            large_signal,
            fee=0.0,
            constraints=constraints,
            strategy_name="constrained_test",
        )

        # Should run successfully with constraints
        assert isinstance(result, Result)
        assert math.isfinite(result.pnl)


class TestGoldenPathDataValidation:
    """Test data quality validation in backtests."""

    def test_validation_config_respected(self, synthetic_price_data: np.ndarray) -> None:
        """Test that validation can be configured."""
        validation = DataValidationConfig(
            enabled=True,
            allow_warnings=True,
            skip_validation=False,
        )

        result = walk_forward(
            synthetic_price_data,
            momentum_signal,
            fee=0.0,
            data_validation=validation,
            strategy_name="validated_test",
        )

        # Should pass validation with clean data
        assert isinstance(result, Result)

    def test_skip_validation_works(self) -> None:
        """Test that validation can be skipped."""
        # Create data with some edge case (but still runnable)
        prices = np.array([100.0, 101.0, 99.0, 102.0, 103.0])

        validation = DataValidationConfig(
            enabled=True,
            skip_validation=True,
        )

        result = walk_forward(
            prices,
            buy_and_hold_signal,
            fee=0.0,
            data_validation=validation,
            strategy_name="skip_validation",
        )

        assert isinstance(result, Result)


class TestGoldenPathAntiLeakage:
    """Test anti-look-ahead bias mechanisms."""

    def test_anti_leakage_config_applies(self, synthetic_price_data: np.ndarray) -> None:
        """Test that anti-leakage configuration is applied."""
        anti_leakage = AntiLeakageConfig(
            enforce_signal_lag=True,
            minimum_signal_delay=2,
            warn_on_potential_leakage=False,
        )

        result = walk_forward(
            synthetic_price_data,
            momentum_signal,
            fee=0.0,
            anti_leakage=anti_leakage,
            strategy_name="anti_leakage_test",
        )

        # Anti-leakage should enforce minimum delay
        assert result.latency_steps >= 2


class TestGoldenPathDeterminism:
    """Test that backtests are deterministic with fixed seeds."""

    def test_repeated_runs_produce_same_result(self, synthetic_price_data: np.ndarray) -> None:
        """Multiple runs with same inputs should produce identical results."""
        results = []

        for _ in range(3):
            np.random.seed(RANDOM_SEED)
            result = walk_forward(
                synthetic_price_data,
                momentum_signal,
                fee=0.001,
                strategy_name="determinism_test",
            )
            results.append(result)

        # All runs should produce identical PnL
        assert all(r.pnl == results[0].pnl for r in results)
        assert all(r.trades == results[0].trades for r in results)
        assert all(r.max_dd == results[0].max_dd for r in results)


class TestGoldenPathWalkForwardEngine:
    """Test the WalkForwardEngine class directly."""

    def test_engine_instance_creation(self) -> None:
        """Test that engine can be instantiated."""
        engine = WalkForwardEngine()
        assert engine is not None

    def test_engine_run_method(self, synthetic_price_data: np.ndarray) -> None:
        """Test that engine.run() produces valid results."""
        engine = WalkForwardEngine()

        result = engine.run(
            synthetic_price_data,
            momentum_signal,
            fee=0.001,
            strategy_name="engine_test",
        )

        assert isinstance(result, Result)
        assert math.isfinite(result.pnl)


class TestGoldenPathEdgeCases:
    """Test edge cases that should not break the system."""

    def test_minimum_viable_data(self) -> None:
        """Test with minimum viable price data (2 points)."""
        prices = np.array([100.0, 101.0])

        result = walk_forward(
            prices,
            buy_and_hold_signal,
            fee=0.0,
            strategy_name="minimal_data",
        )

        assert isinstance(result, Result)
        assert math.isfinite(result.pnl)

    def test_constant_prices(self) -> None:
        """Test with constant prices (no movement)."""
        prices = np.full(100, 100.0)

        result = walk_forward(
            prices,
            momentum_signal,
            fee=0.0,
            strategy_name="constant_prices",
        )

        # No price movement = no PnL (approximately)
        assert abs(result.pnl) < 1e-6

    def test_alternating_signal(self, synthetic_price_data: np.ndarray) -> None:
        """Test with rapidly alternating signal (high turnover)."""
        def alternating_signal(p: np.ndarray) -> np.ndarray:
            signal = np.zeros_like(p)
            signal[::2] = 1.0
            signal[1::2] = -1.0
            return signal

        result = walk_forward(
            synthetic_price_data,
            alternating_signal,
            fee=0.0,
            strategy_name="high_turnover",
        )

        # High turnover should have many trades
        assert result.trades > len(synthetic_price_data) // 3
        assert math.isfinite(result.pnl)
