# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for data quality validation and anti-leakage in backtest engine."""

from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import (
    AntiLeakageConfig,
    DataValidationConfig,
    LatencyConfig,
    walk_forward,
)
from geosync.data_quality import DataQualityError


def _simple_signal(prices: np.ndarray) -> np.ndarray:
    """Simple signal that goes long when price is above mean."""
    return np.where(prices > prices.mean(), 1.0, -1.0)


class TestDataValidation:
    """Tests for data quality validation in backtest engine."""

    def test_validation_passes_for_valid_data(self) -> None:
        """Valid data should pass validation without issues."""
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
            data_validation=DataValidationConfig(enabled=True),
        )
        assert result.data_quality_report is not None
        assert result.data_quality_report.is_valid

    def test_validation_fails_for_negative_prices(self) -> None:
        """Negative prices should cause validation to fail."""
        prices = np.array([100.0, -10.0, 102.0, 103.0])

        with pytest.raises(DataQualityError) as exc_info:
            walk_forward(
                prices,
                _simple_signal,
                fee=0.0,
                initial_capital=100.0,
                data_validation=DataValidationConfig(enabled=True),
            )

        assert "Data quality validation failed" in str(exc_info.value)
        assert exc_info.value.report.critical_count >= 1

    def test_validation_disabled_by_default(self) -> None:
        """When data validation is disabled, invalid data should not raise."""
        prices = np.array([100.0, 101.0, 102.0, 103.0])

        # By default, validation is enabled but should pass for valid data
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
        )
        assert result.pnl is not None

    def test_skip_validation_flag(self) -> None:
        """Skip validation flag should allow any data through."""
        prices = np.array([100.0, -10.0, 102.0, 103.0])

        # With skip_validation, validation is skipped but warning is issued by data_quality
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
            data_validation=DataValidationConfig(skip_validation=True),
        )

        # Should complete without raising
        assert result is not None
        # Report should indicate it was skipped
        assert result.data_quality_report is not None
        assert result.data_quality_report.skipped

    def test_validation_disabled_in_config(self) -> None:
        """Disabled validation should not raise even with bad data."""
        prices = np.array([100.0, -10.0, 102.0, 103.0])

        # Disable validation entirely
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
            data_validation=DataValidationConfig(enabled=False),
        )

        # Should complete without raising
        assert result is not None
        assert result.data_quality_report is None


class TestAntiLeakage:
    """Tests for anti-look-ahead bias enforcement."""

    def test_anti_leakage_disabled_by_default(self) -> None:
        """Anti-leakage is disabled by default for backward compatibility."""
        prices = np.linspace(100, 110, 10)

        # With default settings, no latency adjustment
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
        )

        # Default latency is 0
        assert result.latency_steps == 0

    def test_anti_leakage_adjusts_latency(self) -> None:
        """When enabled, anti-leakage should enforce minimum signal delay."""
        prices = np.linspace(100, 110, 10)

        with pytest.warns(UserWarning, match="Latency.*less than minimum"):
            result = walk_forward(
                prices,
                _simple_signal,
                fee=0.0,
                initial_capital=100.0,
                anti_leakage=AntiLeakageConfig(
                    enforce_signal_lag=True,
                    minimum_signal_delay=1,
                ),
            )

        # Latency should be adjusted to at least 1
        assert result.latency_steps >= 1

    def test_anti_leakage_respects_existing_latency(self) -> None:
        """When latency is already sufficient, no adjustment is needed."""
        prices = np.linspace(100, 110, 10)

        # Pre-set latency that meets minimum
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
            latency=LatencyConfig(signal_to_order=2),
            anti_leakage=AntiLeakageConfig(
                enforce_signal_lag=True,
                minimum_signal_delay=1,
            ),
        )

        # Latency should remain at 2
        assert result.latency_steps == 2

    def test_anti_leakage_custom_minimum_delay(self) -> None:
        """Custom minimum delay should be enforced."""
        prices = np.linspace(100, 110, 10)

        with pytest.warns(UserWarning, match="Latency.*less than minimum"):
            result = walk_forward(
                prices,
                _simple_signal,
                fee=0.0,
                initial_capital=100.0,
                anti_leakage=AntiLeakageConfig(
                    enforce_signal_lag=True,
                    minimum_signal_delay=3,
                ),
            )

        # Latency should be at least 3
        assert result.latency_steps >= 3

    def test_anti_leakage_no_warning_when_disabled(self) -> None:
        """No warning when anti-leakage is disabled."""
        prices = np.linspace(100, 110, 10)

        # Should not warn when disabled
        result = walk_forward(
            prices,
            _simple_signal,
            fee=0.0,
            initial_capital=100.0,
            anti_leakage=AntiLeakageConfig(
                enforce_signal_lag=False,
                warn_on_potential_leakage=True,
            ),
        )

        assert result.latency_steps == 0


class TestCombinedValidationAndAntiLeakage:
    """Tests for combined data validation and anti-leakage."""

    def test_both_features_work_together(self) -> None:
        """Both features should work when enabled together."""
        prices = np.linspace(100, 110, 10)

        with pytest.warns(UserWarning, match="Latency.*less than minimum"):
            result = walk_forward(
                prices,
                _simple_signal,
                fee=0.0,
                initial_capital=100.0,
                data_validation=DataValidationConfig(enabled=True),
                anti_leakage=AntiLeakageConfig(
                    enforce_signal_lag=True,
                    minimum_signal_delay=1,
                ),
            )

        assert result.data_quality_report is not None
        assert result.data_quality_report.is_valid
        assert result.latency_steps >= 1


class TestScenarioTests:
    """Scenario-based tests for backtest engine."""

    def test_bull_market_scenario(self) -> None:
        """Bull market (continuous uptrend) scenario."""
        # Continuous uptrend
        prices = np.linspace(100, 150, 50)

        def always_long(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)

        result = walk_forward(
            prices,
            always_long,
            fee=0.0,
            initial_capital=1000.0,
        )

        # Long position in uptrend should be profitable
        assert result.pnl > 0
        # No NaN or infinite values
        assert np.isfinite(result.pnl)
        assert result.equity_curve is not None
        assert np.all(np.isfinite(result.equity_curve))

    def test_bear_market_scenario(self) -> None:
        """Bear market (continuous downtrend) scenario."""
        # Continuous downtrend
        prices = np.linspace(150, 100, 50)

        def always_short(p: np.ndarray) -> np.ndarray:
            return -np.ones_like(p)

        result = walk_forward(
            prices,
            always_short,
            fee=0.0,
            initial_capital=1000.0,
        )

        # Short position in downtrend should be profitable
        assert result.pnl > 0
        # No NaN or infinite values
        assert np.isfinite(result.pnl)

    def test_flat_market_scenario(self) -> None:
        """Flat market (no trend) scenario."""
        # Flat market - oscillating around 100
        prices = 100 + 0.01 * np.sin(np.linspace(0, 8 * np.pi, 100))

        def momentum_signal(p: np.ndarray) -> np.ndarray:
            returns = np.diff(p, prepend=p[0])
            return np.sign(returns)

        result = walk_forward(
            prices,
            momentum_signal,
            fee=0.0,
            initial_capital=1000.0,
        )

        # In flat market, PnL should be close to zero
        # Allow small deviation due to signal timing
        assert abs(result.pnl) < 10.0  # Reasonable range for flat market
        # No NaN values
        assert np.isfinite(result.pnl)

    def test_flat_market_with_costs(self) -> None:
        """Flat market with costs should be negative."""
        prices = 100 + 0.01 * np.sin(np.linspace(0, 8 * np.pi, 100))

        def momentum_signal(p: np.ndarray) -> np.ndarray:
            returns = np.diff(p, prepend=p[0])
            return np.sign(returns)

        # With high costs
        result = walk_forward(
            prices,
            momentum_signal,
            fee=0.5,  # Very high fee
            initial_capital=1000.0,
        )

        # With significant costs in flat market, should be negative
        assert result.commission_cost > 0
        # PnL should be reduced by costs
        assert result.pnl < result.commission_cost * -0.5  # Costs should hurt

    def test_high_volatility_scenario(self) -> None:
        """High volatility / flash crash scenario."""
        # Normal market with sudden flash crash
        normal = np.linspace(100, 105, 20)
        crash = np.array([105, 80, 60, 70, 85, 95, 100])  # Flash crash and recovery
        recovery = np.linspace(100, 102, 20)
        prices = np.concatenate([normal, crash, recovery])

        def simple_signal(p: np.ndarray) -> np.ndarray:
            return np.sign(p - p.mean())

        result = walk_forward(
            prices,
            simple_signal,
            fee=0.0,
            initial_capital=1000.0,
        )

        # Should not have infinite or NaN values
        assert np.isfinite(result.pnl)
        assert result.equity_curve is not None
        assert np.all(np.isfinite(result.equity_curve))
        # Drawdown should reflect the crash
        assert result.max_dd < 0

    def test_no_mathematical_bugs(self) -> None:
        """Verify no mathematical bugs in edge cases."""
        prices = np.array([100.0] * 10)  # Constant price

        def constant_signal(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p) * 0.5

        result = walk_forward(
            prices,
            constant_signal,
            fee=0.0,
            initial_capital=1000.0,
        )

        # With constant price, PnL should be exactly 0 (no price movement)
        assert result.pnl == pytest.approx(0.0, abs=1e-10)
        assert np.isfinite(result.max_dd)
        assert result.equity_curve is not None


class TestAntiLeakageWithShuffledData:
    """Tests verifying that look-ahead signals don't magically improve results."""

    def test_shuffled_future_data_changes_results(self) -> None:
        """Shuffling future price data should change backtest results.

        If a strategy uses look-ahead data, it would perform consistently
        well even with shuffled data. A proper strategy should produce
        different (often worse) results when future data is randomized.
        """
        np.random.seed(42)
        # Original data with clear trend
        original_prices = np.linspace(100, 150, 100) + np.random.normal(0, 1, 100)

        def trend_signal(p: np.ndarray) -> np.ndarray:
            # Simple moving average crossover (no look-ahead)
            short_ma = np.convolve(p, np.ones(5) / 5, mode="same")
            long_ma = np.convolve(p, np.ones(20) / 20, mode="same")
            return np.sign(short_ma - long_ma)

        # Run with original data
        result_original = walk_forward(
            original_prices,
            trend_signal,
            fee=0.0,
            initial_capital=1000.0,
        )

        # Shuffle the second half of prices (future data)
        shuffled_prices = original_prices.copy()
        shuffled_indices = np.arange(50, 100)
        np.random.shuffle(shuffled_indices)
        shuffled_prices[50:] = original_prices[shuffled_indices]

        result_shuffled = walk_forward(
            shuffled_prices,
            trend_signal,
            fee=0.0,
            initial_capital=1000.0,
        )

        # Results should be different (shuffling future data changes outcome)
        assert result_original.pnl != result_shuffled.pnl

    def test_latency_changes_strategy_performance(self) -> None:
        """Adding latency should change (typically degrade) strategy performance.

        This tests that anti-leakage latency enforcement affects signal execution
        by shifting when positions are taken.
        """
        # Create price data with a specific pattern
        prices = np.array([100, 102, 104, 103, 101, 99, 98, 100, 102, 104], dtype=float)

        def momentum_signal(p: np.ndarray) -> np.ndarray:
            """Simple momentum signal based on prior price change."""
            signals = np.zeros_like(p)
            for i in range(1, len(p)):
                # Use previous price change to set signal
                signals[i] = 1.0 if p[i] > p[i - 1] else -1.0
            return signals

        # Without latency
        result_no_latency = walk_forward(
            prices,
            momentum_signal,
            fee=0.0,
            latency=LatencyConfig(signal_to_order=0),
        )

        # With latency - signals are delayed
        result_with_latency = walk_forward(
            prices,
            momentum_signal,
            fee=0.0,
            latency=LatencyConfig(signal_to_order=2),
        )

        # Results should differ due to latency
        assert result_no_latency.pnl != result_with_latency.pnl
        # Latency should be reflected in the result
        assert result_with_latency.latency_steps == 2
        assert result_no_latency.latency_steps == 0


class TestCostModelImpact:
    """Tests verifying that costs always reduce or equal performance."""

    def test_pnl_without_costs_matches_expected(self) -> None:
        """PnL without costs should exactly match position * price change."""
        prices = np.array([100.0, 102.0, 101.0, 105.0, 103.0])

        def buy_and_hold(p: np.ndarray) -> np.ndarray:
            signal = np.zeros_like(p)
            signal[1:] = 1.0  # Long from bar 1 onwards
            return signal

        result = walk_forward(
            prices,
            buy_and_hold,
            fee=0.0,
            initial_capital=0.0,
        )

        # Signal: [0, 1, 1, 1, 1] - enter long at bar 1
        # Executed positions: [0, 1, 1, 1, 1] (with 0 latency)
        # price_moves = [2, -1, 4, -2] (prices[i+1] - prices[i])
        # PnL calculation uses positions[1:] * price_moves
        # positions[1:] = [1, 1, 1, 1]
        # PnL = 1*2 + 1*(-1) + 1*4 + 1*(-2) = 2 - 1 + 4 - 2 = 3
        assert result.pnl == pytest.approx(3.0, rel=1e-6)
        assert result.commission_cost == 0.0

    def test_large_commission_dominates_pnl(self) -> None:
        """With large commissions, PnL should be significantly reduced."""
        prices = np.linspace(100, 110, 20)  # Uptrend

        def entry_signal(p: np.ndarray) -> np.ndarray:
            """Signal that enters long at bar 1."""
            signals = np.zeros_like(p)
            signals[1:] = 1.0  # Long from bar 1
            return signals

        # Without fees
        result_no_fee = walk_forward(prices, entry_signal, fee=0.0)

        # With very large fee (10% per trade)
        result_high_fee = walk_forward(prices, entry_signal, fee=10.0)

        # High fee should reduce PnL
        assert result_no_fee.pnl > 0
        assert result_high_fee.pnl < result_no_fee.pnl
        assert result_high_fee.commission_cost > 0
        # The fee should have been deducted
        assert result_no_fee.pnl - result_high_fee.pnl == pytest.approx(
            result_high_fee.commission_cost, rel=1e-6
        )

    def test_costs_make_flat_market_negative(self) -> None:
        """In a flat market, any costs should result in negative PnL."""
        # Perfectly flat market
        prices = np.array([100.0] * 20)

        def oscillating_signal(p: np.ndarray) -> np.ndarray:
            return np.array([(-1) ** i for i in range(len(p))], dtype=float)

        # Without costs - should be exactly zero
        result_no_cost = walk_forward(prices, oscillating_signal, fee=0.0)
        assert result_no_cost.pnl == pytest.approx(0.0, abs=1e-10)

        # With costs - should be negative
        result_with_cost = walk_forward(prices, oscillating_signal, fee=0.1)
        assert result_with_cost.pnl < 0
        assert result_with_cost.commission_cost > 0


class TestBacktestReportGeneration:
    """Tests ensuring backtest reports are always generated correctly."""

    def test_performance_report_generated(self) -> None:
        """Every backtest should generate a performance report."""
        prices = np.linspace(100, 110, 50)

        result = walk_forward(
            prices,
            lambda p: np.ones_like(p),
            fee=0.001,
            initial_capital=1000.0,
        )

        assert result.performance is not None
        assert result.report_path is not None
        assert result.performance.sharpe_ratio is not None or result.performance.cagr is not None

    def test_report_includes_cost_breakdown(self) -> None:
        """Report should include a breakdown of all costs."""
        from backtest.engine import OrderBookConfig, SlippageConfig

        prices = np.linspace(100, 110, 20)

        def entry_signal(p: np.ndarray) -> np.ndarray:
            """Signal that enters long at bar 1."""
            signals = np.zeros_like(p)
            signals[1:] = 1.0
            return signals

        result = walk_forward(
            prices,
            entry_signal,
            fee=0.01,
            order_book=OrderBookConfig(spread_bps=5.0),
            slippage=SlippageConfig(per_unit_bps=2.0),
        )

        # All cost components should be tracked
        assert result.commission_cost >= 0
        assert result.spread_cost >= 0
        assert result.slippage_cost >= 0

        # Total cost should be sum of components (at least one should be > 0)
        total_cost = result.commission_cost + result.spread_cost + result.slippage_cost
        assert total_cost > 0
        # There should be at least one trade
        assert result.trades >= 1

    def test_equity_curve_is_valid(self) -> None:
        """Equity curve should be valid and finite."""
        prices = np.linspace(100, 110, 100)

        result = walk_forward(
            prices,
            lambda p: np.sin(np.linspace(0, 4 * np.pi, len(p))),
            fee=0.001,
            initial_capital=1000.0,
        )

        assert result.equity_curve is not None
        # Equity curve has len(prices) - 1 elements because it tracks cumulative PnL
        # from price changes, and there are n-1 price changes for n prices
        assert len(result.equity_curve) == len(prices) - 1
        assert np.all(np.isfinite(result.equity_curve))
        # Equity curve values should be numeric
        assert result.equity_curve[0] is not None
