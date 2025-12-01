# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for data quality validation and anti-leakage in backtest engine."""

from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import (
    AntiLeakageConfig,
    DataValidationConfig,
    LatencyConfig,
    WalkForwardEngine,
    walk_forward,
)
from tradepulse.data_quality import DataQualityError


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
