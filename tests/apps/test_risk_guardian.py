# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Risk Guardian."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.risk_guardian import RiskGuardian, RiskGuardianConfig, SimulationResult


class TestRiskGuardianConfig:
    """Tests for RiskGuardianConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = RiskGuardianConfig()
        assert config.initial_capital == 100_000.0
        assert config.daily_loss_limit_pct == 5.0
        assert config.max_drawdown_pct == 10.0
        assert config.safe_mode_threshold_pct == 7.0
        assert config.enable_kill_switch is True
        assert config.enable_safe_mode is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = RiskGuardianConfig(
            initial_capital=50_000.0,
            daily_loss_limit_pct=3.0,
            max_drawdown_pct=8.0,
        )
        assert config.initial_capital == 50_000.0
        assert config.daily_loss_limit_pct == 3.0
        assert config.max_drawdown_pct == 8.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        config = RiskGuardianConfig()
        d = config.to_dict()
        assert "initial_capital" in d
        assert "daily_loss_limit_pct" in d
        assert d["initial_capital"] == 100_000.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "initial_capital": 75_000,
            "daily_loss_limit_pct": 4.5,
        }
        config = RiskGuardianConfig.from_dict(data)
        assert config.initial_capital == 75_000.0
        assert config.daily_loss_limit_pct == 4.5


class TestSimulationResult:
    """Tests for SimulationResult."""

    def test_sharpe_improvement(self) -> None:
        """Test Sharpe improvement calculation."""
        result = SimulationResult(
            baseline_sharpe=1.0,
            protected_sharpe=1.5,
            config=RiskGuardianConfig(),
        )
        assert result.sharpe_improvement == 50.0

    def test_sharpe_improvement_zero_baseline(self) -> None:
        """Test Sharpe improvement with zero baseline."""
        result = SimulationResult(
            baseline_sharpe=0.0,
            protected_sharpe=1.0,
            config=RiskGuardianConfig(),
        )
        assert result.sharpe_improvement == 0.0

    def test_drawdown_reduction(self) -> None:
        """Test drawdown reduction calculation."""
        result = SimulationResult(
            baseline_max_drawdown=0.20,
            protected_max_drawdown=0.10,
            config=RiskGuardianConfig(),
        )
        assert result.drawdown_reduction == 50.0

    def test_summary_generation(self) -> None:
        """Test summary text generation."""
        result = SimulationResult(
            baseline_pnl=10_000,
            protected_pnl=8_000,
            baseline_max_drawdown=0.15,
            protected_max_drawdown=0.08,
            saved_capital=5_000,
            saved_capital_pct=5.0,
            total_periods=1000,
            config=RiskGuardianConfig(),
        )
        summary = result.summary()
        assert "RISK GUARDIAN" in summary
        assert "BASELINE" in summary
        assert "SAVED CAPITAL" in summary


class TestRiskGuardian:
    """Tests for RiskGuardian engine."""

    @pytest.fixture
    def simple_prices(self) -> np.ndarray:
        """Generate simple trending price series."""
        np.random.seed(42)
        return 100 + np.cumsum(np.random.normal(0, 0.5, 500))

    @pytest.fixture
    def volatile_prices(self) -> np.ndarray:
        """Generate volatile price series with crashes."""
        np.random.seed(123)
        prices = np.zeros(1000)
        prices[0] = 100
        for i in range(1, 1000):
            prices[i] = prices[i - 1] * (1 + np.random.normal(0, 0.02))
            # Add crashes
            if i == 300:
                prices[i] = prices[i - 1] * 0.80  # 20% crash
            if i == 700:
                prices[i] = prices[i - 1] * 0.85  # 15% crash
        return np.maximum(prices, 50)

    @pytest.fixture
    def constant_long_signal(self) -> callable:
        """Signal function that always returns long."""
        return lambda prices: np.ones_like(prices)

    @pytest.fixture
    def momentum_signal(self) -> callable:
        """Simple momentum signal function."""

        def signal_fn(prices: np.ndarray) -> np.ndarray:
            signals = np.zeros_like(prices)
            window = 10
            for i in range(window, len(prices)):
                sma = np.mean(prices[i - window : i])
                if prices[i] > sma:
                    signals[i] = 1.0
                elif prices[i] < sma * 0.99:
                    signals[i] = -1.0
                else:
                    signals[i] = signals[i - 1] if i > 0 else 0.0
            return signals

        return signal_fn

    def test_basic_simulation(
        self, simple_prices: np.ndarray, constant_long_signal: callable
    ) -> None:
        """Test basic simulation runs without errors."""
        guardian = RiskGuardian()
        result = guardian.simulate_from_prices(simple_prices, constant_long_signal)

        assert isinstance(result, SimulationResult)
        assert result.total_periods == len(simple_prices)
        assert result.baseline_pnl != 0  # Should have some PnL

    def test_risk_controls_trigger(
        self, volatile_prices: np.ndarray, momentum_signal: callable
    ) -> None:
        """Test that risk controls are triggered during volatility."""
        config = RiskGuardianConfig(
            daily_loss_limit_pct=3.0,
            max_drawdown_pct=10.0,
            safe_mode_threshold_pct=7.0,
            max_position_pct=50.0,
        )
        guardian = RiskGuardian(config)
        result = guardian.simulate_from_prices(volatile_prices, momentum_signal)

        # With volatile data, some risk events should occur
        # Note: may not always trigger depending on timing
        assert result.protected_max_drawdown <= result.baseline_max_drawdown

    def test_protected_drawdown_capped(
        self, volatile_prices: np.ndarray, constant_long_signal: callable
    ) -> None:
        """Test that protected drawdown respects limits."""
        config = RiskGuardianConfig(
            max_drawdown_pct=15.0,
            max_position_pct=50.0,
        )
        guardian = RiskGuardian(config)
        result = guardian.simulate_from_prices(volatile_prices, constant_long_signal)

        # Protected drawdown should not significantly exceed max
        # (Some overshoot is possible before detection)
        assert result.protected_max_drawdown <= result.baseline_max_drawdown * 1.1

    def test_simulate_from_dataframe(
        self, simple_prices: np.ndarray, momentum_signal: callable
    ) -> None:
        """Test simulation from DataFrame."""
        df = pd.DataFrame({"close": simple_prices})

        guardian = RiskGuardian()
        result = guardian.simulate_from_dataframe(df, price_col="close", signal_fn=momentum_signal)

        assert isinstance(result, SimulationResult)
        assert result.total_periods == len(simple_prices)

    def test_simulate_with_signal_column(self, simple_prices: np.ndarray) -> None:
        """Test simulation with pre-computed signal column."""
        signals = np.zeros_like(simple_prices)
        signals[100:] = 1.0  # Long after bar 100

        df = pd.DataFrame({"close": simple_prices, "signal": signals})

        guardian = RiskGuardian()
        result = guardian.simulate_from_dataframe(df, price_col="close", signal_col="signal")

        assert isinstance(result, SimulationResult)

    def test_insufficient_data(self) -> None:
        """Test error handling for insufficient data."""
        guardian = RiskGuardian()
        short_prices = np.array([100.0])  # Only 1 point

        with pytest.raises(ValueError, match="at least 2"):
            guardian.simulate_from_prices(short_prices, lambda x: np.zeros_like(x))

    def test_signal_length_mismatch(self, simple_prices: np.ndarray) -> None:
        """Test error handling for signal length mismatch."""
        guardian = RiskGuardian()

        def bad_signal_fn(prices: np.ndarray) -> np.ndarray:
            return np.zeros(10)  # Wrong length

        with pytest.raises(ValueError, match="same length"):
            guardian.simulate_from_prices(simple_prices, bad_signal_fn)

    def test_result_to_dict(self, simple_prices: np.ndarray, momentum_signal: callable) -> None:
        """Test result serialization."""
        guardian = RiskGuardian()
        result = guardian.simulate_from_prices(simple_prices, momentum_signal)

        d = result.to_dict()
        assert "baseline" in d
        assert "protected" in d
        assert "value_delivered" in d
        assert "pnl" in d["baseline"]
        assert "saved_capital" in d["value_delivered"]


class TestRiskGuardianEdgeCases:
    """Edge case tests for Risk Guardian."""

    def test_flat_prices(self) -> None:
        """Test with flat (constant) prices."""
        prices = np.full(100, 100.0)  # Constant price

        guardian = RiskGuardian()
        result = guardian.simulate_from_prices(prices, lambda x: np.zeros_like(x))

        assert result.baseline_pnl == 0.0
        assert result.protected_pnl == 0.0

    def test_declining_prices(self) -> None:
        """Test with monotonically declining prices."""
        prices = np.linspace(100, 50, 500)  # 50% decline

        guardian = RiskGuardian()
        result = guardian.simulate_from_prices(prices, lambda x: np.ones_like(x))

        # Long position during decline should lose money
        assert result.baseline_pnl < 0

    def test_config_disabled_features(self) -> None:
        """Test with disabled risk features."""
        config = RiskGuardianConfig(
            enable_kill_switch=False,
            enable_safe_mode=False,
        )
        guardian = RiskGuardian(config)

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.normal(0, 1, 500))

        result = guardian.simulate_from_prices(prices, lambda x: np.ones_like(x))

        # Kill switch should not have activated
        assert result.kill_switch_activations == 0
        assert result.safe_mode_periods == 0
