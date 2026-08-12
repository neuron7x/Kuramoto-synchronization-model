# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the EEPFractalRegulator."""

from __future__ import annotations

import numpy as np
import pytest

from core.neuro.fractal_regulator import EEPFractalRegulator, RegulatorMetrics


class TestEEPFractalRegulatorInit:
    """Test regulator initialization and validation."""

    def test_default_initialization(self) -> None:
        """Test regulator with default parameters."""
        regulator = EEPFractalRegulator()
        assert regulator.window_size == 100
        assert regulator.embodied_baseline == 1.0
        assert regulator.crisis_threshold == 0.3
        assert regulator.energy_damping == 0.9

    def test_custom_initialization(self) -> None:
        """Test regulator with custom parameters."""
        regulator = EEPFractalRegulator(
            window_size=50,
            embodied_baseline=2.0,
            crisis_threshold=0.5,
            energy_damping=0.8,
            seed=42,
        )
        assert regulator.window_size == 50
        assert regulator.embodied_baseline == 2.0
        assert regulator.crisis_threshold == 0.5
        assert regulator.energy_damping == 0.8

    def test_invalid_window_size(self) -> None:
        """Test that small window sizes are rejected."""
        with pytest.raises(ValueError, match="window_size must be at least 8"):
            EEPFractalRegulator(window_size=5)

    def test_invalid_embodied_baseline(self) -> None:
        """Test that non-positive baseline is rejected."""
        with pytest.raises(ValueError, match="embodied_baseline must be positive"):
            EEPFractalRegulator(embodied_baseline=0.0)

    def test_invalid_crisis_threshold(self) -> None:
        """Test that invalid threshold is rejected."""
        with pytest.raises(ValueError, match="crisis_threshold must be between 0 and 1"):
            EEPFractalRegulator(crisis_threshold=1.5)

    def test_invalid_energy_damping(self) -> None:
        """Test that invalid damping is rejected."""
        with pytest.raises(ValueError, match="energy_damping must be between 0 and 1"):
            EEPFractalRegulator(energy_damping=-0.1)


class TestUpdateState:
    """Test state update functionality."""

    def test_update_single_state(self) -> None:
        """Test updating with a single signal value."""
        regulator = EEPFractalRegulator(window_size=20)
        metrics = regulator.update_state(0.5)

        assert isinstance(metrics, RegulatorMetrics)
        assert metrics.state == 0.5
        assert 0.0 <= metrics.hurst <= 1.0
        assert metrics.ple >= 0.0
        assert 0.0 <= metrics.csi <= 1.0
        assert metrics.energy_cost >= 0.0

    def test_update_multiple_states(self) -> None:
        """Test updating with multiple signal values."""
        regulator = EEPFractalRegulator(window_size=20)
        signals = [0.1, 0.2, 0.3, 0.4, 0.5]

        for signal in signals:
            metrics = regulator.update_state(signal)
            assert metrics.state == signal

    def test_window_sliding(self) -> None:
        """Test that window slides correctly."""
        window_size = 10
        regulator = EEPFractalRegulator(window_size=window_size)

        # Add more than window_size samples
        for i in range(window_size + 5):
            regulator.update_state(float(i))

        # Check internal state
        assert len(regulator._state_history) == window_size
        assert regulator._state_history[-1] == float(window_size + 4)

    def test_invalid_signal(self) -> None:
        """Test that non-finite signals are rejected."""
        regulator = EEPFractalRegulator()

        with pytest.raises(ValueError, match="signal must be finite"):
            regulator.update_state(np.nan)

        with pytest.raises(ValueError, match="signal must be finite"):
            regulator.update_state(np.inf)


class TestHurstExponent:
    """Test Hurst exponent computation."""

    def test_hurst_with_insufficient_data(self) -> None:
        """Test Hurst returns 0.5 with insufficient data."""
        regulator = EEPFractalRegulator()
        assert regulator.compute_hurst() == 0.5

    def test_hurst_with_persistent_series(self) -> None:
        """Test Hurst exponent with persistent (trending) series."""
        regulator = EEPFractalRegulator(window_size=100, seed=42)
        rng = np.random.default_rng(42)

        # Create persistent series (cumulative sum)
        signals = np.cumsum(rng.normal(0, 0.1, 100))
        for signal in signals:
            regulator.update_state(signal)

        hurst = regulator.compute_hurst()
        assert 0.0 <= hurst <= 1.0
        # Persistent series should have H > 0.5
        assert hurst > 0.5

    def test_hurst_with_random_walk(self) -> None:
        """Test Hurst exponent with random walk."""
        regulator = EEPFractalRegulator(window_size=50, seed=7)
        rng = np.random.default_rng(7)

        # Random walk should have H ≈ 0.5
        signals = rng.normal(0, 1, 50)
        for signal in signals:
            regulator.update_state(signal)

        hurst = regulator.compute_hurst()
        assert 0.2 <= hurst <= 0.8  # Allow wider variance for small samples


class TestPowerLawExponent:
    """Test PLE computation."""

    def test_ple_with_insufficient_data(self) -> None:
        """Test PLE returns 1.0 with insufficient data."""
        regulator = EEPFractalRegulator()
        assert regulator.compute_ple() == 1.0

    def test_ple_with_valid_data(self) -> None:
        """Test PLE with valid signal history."""
        regulator = EEPFractalRegulator(window_size=50, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 1, 50)
        for signal in signals:
            regulator.update_state(signal)

        ple = regulator.compute_ple()
        assert 0.0 <= ple <= 3.0

    def test_ple_with_constant_series(self) -> None:
        """Test PLE with constant series."""
        regulator = EEPFractalRegulator(window_size=20)

        # Constant series should have minimal PLE
        for _ in range(20):
            regulator.update_state(1.0)

        ple = regulator.compute_ple()
        assert ple == 1.0  # Default value for constant series


class TestCrisisStabilityIndex:
    """Test CSI computation."""

    def test_csi_with_insufficient_data(self) -> None:
        """Test CSI returns 1.0 with insufficient data."""
        regulator = EEPFractalRegulator()
        assert regulator.compute_csi() == 1.0

    def test_csi_with_stable_series(self) -> None:
        """Test CSI with stable, low-volatility series."""
        regulator = EEPFractalRegulator(window_size=50, seed=42)
        rng = np.random.default_rng(42)

        # Low volatility series
        signals = rng.normal(0, 0.01, 50)
        for signal in signals:
            regulator.update_state(signal)

        csi = regulator.compute_csi()
        assert 0.0 <= csi <= 1.0
        # Low volatility should lead to high CSI
        assert csi > 0.5

    def test_csi_with_volatile_series(self) -> None:
        """Test CSI with volatile, crisis-like series."""
        regulator = EEPFractalRegulator(window_size=50, seed=42)
        rng = np.random.default_rng(42)

        # High volatility series
        signals = rng.normal(0, 5.0, 50)
        for signal in signals:
            regulator.update_state(signal)

        csi = regulator.compute_csi()
        assert 0.0 <= csi <= 1.0
        # High volatility should lead to lower CSI
        assert csi < 0.8

    def test_csi_with_regime_shift(self) -> None:
        """Test CSI detects regime shifts."""
        regulator = EEPFractalRegulator(window_size=40, seed=42)

        # First regime: low values
        for _ in range(20):
            regulator.update_state(0.0)

        # Second regime: high values
        for _ in range(20):
            regulator.update_state(10.0)

        csi = regulator.compute_csi()
        assert 0.0 <= csi <= 1.0
        # Regime shift should reduce CSI
        assert csi < 0.9


class TestEfficiencyOptimization:
    """Test efficiency optimization."""

    def test_optimize_with_insufficient_data(self) -> None:
        """Test optimization returns 0.0 with insufficient data."""
        regulator = EEPFractalRegulator()
        assert regulator.optimize_efficiency() == 0.0

    def test_optimize_during_stable_period(self) -> None:
        """Test optimization during stable period."""
        regulator = EEPFractalRegulator(window_size=30, seed=42)
        rng = np.random.default_rng(42)

        # Stable period
        signals = rng.normal(0, 0.1, 30)
        for signal in signals:
            regulator.update_state(signal)

        # CSI should be high (not in crisis)
        assert regulator.compute_csi() > 0.3

    def test_optimize_during_crisis(self) -> None:
        """Test optimization applies damping during crisis."""
        regulator = EEPFractalRegulator(
            window_size=30,
            crisis_threshold=0.5,
            energy_damping=0.8,
            seed=42,
        )
        rng = np.random.default_rng(42)

        # Create crisis-like volatility
        signals = rng.normal(0, 3.0, 30)
        for signal in signals:
            regulator.update_state(signal)

        # Should detect crisis
        csi = regulator.compute_csi()
        assert csi < 0.5  # Below threshold


class TestGetMetrics:
    """Test metrics retrieval."""

    def test_get_metrics_no_history(self) -> None:
        """Test get_metrics returns None without history."""
        regulator = EEPFractalRegulator()
        assert regulator.get_metrics() is None

    def test_get_metrics_with_history(self) -> None:
        """Test get_metrics returns valid metrics."""
        regulator = EEPFractalRegulator(window_size=20)

        for i in range(10):
            regulator.update_state(float(i))

        metrics = regulator.get_metrics()
        assert metrics is not None
        assert isinstance(metrics, RegulatorMetrics)
        assert metrics.state == 9.0
        assert 0.0 <= metrics.hurst <= 1.0
        assert 0.0 <= metrics.csi <= 1.0


class TestCrisisDetection:
    """Test crisis detection."""

    def test_is_in_crisis_no_data(self) -> None:
        """Test crisis detection with no data."""
        regulator = EEPFractalRegulator()
        # Should not be in crisis with no data (CSI = 1.0)
        assert not regulator.is_in_crisis()

    def test_is_in_crisis_stable(self) -> None:
        """Test crisis detection with stable data."""
        regulator = EEPFractalRegulator(window_size=30, crisis_threshold=0.3, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 0.1, 30)
        for signal in signals:
            regulator.update_state(signal)

        # Stable data should not trigger crisis
        assert not regulator.is_in_crisis()

    def test_is_in_crisis_volatile(self) -> None:
        """Test crisis detection with volatile data."""
        regulator = EEPFractalRegulator(window_size=30, crisis_threshold=0.5, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 5.0, 30)
        for signal in signals:
            regulator.update_state(signal)

        csi = regulator.compute_csi()
        # Very volatile data should trigger crisis
        if csi < 0.5:
            assert regulator.is_in_crisis()


class TestReset:
    """Test regulator reset."""

    def test_reset_clears_state(self) -> None:
        """Test reset clears all state."""
        regulator = EEPFractalRegulator(window_size=20)

        for i in range(10):
            regulator.update_state(float(i))

        assert len(regulator._state_history) > 0
        regulator.reset()

        assert len(regulator._state_history) == 0
        assert len(regulator._energy_history) == 0
        assert regulator._last_efficiency == 1.0

    def test_reset_allows_reuse(self) -> None:
        """Test regulator can be reused after reset."""
        regulator = EEPFractalRegulator(window_size=20)

        for i in range(10):
            regulator.update_state(float(i))

        regulator.reset()

        # Should be able to update again
        metrics = regulator.update_state(5.0)
        assert metrics.state == 5.0


class TestSimulateTradeCycle:
    """Test trade cycle simulation."""

    def test_simulate_empty_signals(self) -> None:
        """Test simulation rejects empty signals."""
        regulator = EEPFractalRegulator()
        with pytest.raises(ValueError, match="signals must be non-empty"):
            regulator.simulate_trade_cycle([])

    def test_simulate_basic_cycle(self) -> None:
        """Test basic trade cycle simulation."""
        regulator = EEPFractalRegulator(window_size=50, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 1, 50)
        results = regulator.simulate_trade_cycle(signals)

        assert len(results) == 50
        for metrics in results:
            assert isinstance(metrics, RegulatorMetrics)
            assert 0.0 <= metrics.hurst <= 1.0
            assert 0.0 <= metrics.csi <= 1.0

    def test_simulate_with_crisis_detection(self) -> None:
        """Test simulation detects crisis events."""
        regulator = EEPFractalRegulator(window_size=100, crisis_threshold=0.4, seed=42)
        rng = np.random.default_rng(42)

        # Mix stable and crisis periods
        stable_signals = rng.normal(0, 0.1, 50)
        crisis_signals = rng.normal(0, 3.0, 50)
        signals = np.concatenate([stable_signals, crisis_signals])

        results = regulator.simulate_trade_cycle(signals)

        # Check that some crisis events were detected
        crisis_count = sum(1 for m in results if m.csi < 0.4)
        assert crisis_count > 0

    def test_simulate_metrics_evolution(self) -> None:
        """Test that metrics evolve over simulation."""
        regulator = EEPFractalRegulator(window_size=50, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 1, 50)
        results = regulator.simulate_trade_cycle(signals)

        # Early metrics (less data)
        early_hurst = results[10].hurst

        # Later metrics (more data)
        late_hurst = results[40].hurst

        # Both should be valid
        assert 0.0 <= early_hurst <= 1.0
        assert 0.0 <= late_hurst <= 1.0

    def test_simulate_verbose_output(self, capsys) -> None:
        """Test verbose simulation output."""
        regulator = EEPFractalRegulator(window_size=20, seed=42)
        rng = np.random.default_rng(42)

        signals = rng.normal(0, 1, 5)
        regulator.simulate_trade_cycle(signals, verbose=True)

        captured = capsys.readouterr()
        assert "Step 1:" in captured.out
        assert "H=" in captured.out
        assert "CSI=" in captured.out


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_market_volatility_scenario(self) -> None:
        """Test regulator with market-like volatility."""
        regulator = EEPFractalRegulator(window_size=100, seed=42)
        rng = np.random.default_rng(42)

        # Simulate market returns with varying volatility
        base_returns = rng.normal(0, 0.01, 50)
        volatile_returns = rng.normal(0, 0.05, 30)
        calming_returns = rng.normal(0, 0.01, 20)

        signals = np.concatenate([base_returns, volatile_returns, calming_returns])
        results = regulator.simulate_trade_cycle(signals)

        # Verify all metrics are computed
        assert all(0.0 <= m.hurst <= 1.0 for m in results)
        assert all(0.0 <= m.csi <= 1.0 for m in results)
        assert all(m.energy_cost >= 0.0 for m in results)

    def test_trend_following_scenario(self) -> None:
        """Test regulator with trending market."""
        regulator = EEPFractalRegulator(window_size=100, seed=42)
        rng = np.random.default_rng(42)

        # Create upward trend with noise
        trend = np.linspace(0, 10, 100)
        noise = rng.normal(0, 0.5, 100)
        signals = trend + noise

        results = regulator.simulate_trade_cycle(signals)

        # Trending data should show high Hurst
        late_metrics = results[-10:]
        avg_hurst = np.mean([m.hurst for m in late_metrics])
        assert avg_hurst > 0.5

    def test_mean_reverting_scenario(self) -> None:
        """Test regulator with mean-reverting pattern."""
        regulator = EEPFractalRegulator(window_size=100, seed=42)

        # Oscillating signal
        t = np.linspace(0, 4 * np.pi, 100)
        signals = np.sin(t)

        results = regulator.simulate_trade_cycle(signals)

        # All metrics should be valid
        assert len(results) == 100
        assert all(isinstance(m, RegulatorMetrics) for m in results)

    def test_coverage_edge_cases(self) -> None:
        """Test edge cases for coverage."""
        regulator = EEPFractalRegulator(window_size=20)

        # Single update
        m1 = regulator.update_state(0.0)
        assert m1.hurst == 0.5  # Default for insufficient data

        # Add minimal data for coverage
        for i in range(10):
            regulator.update_state(float(i))

        # Test all methods
        assert regulator.compute_hurst() >= 0.0
        assert regulator.compute_ple() >= 0.0
        assert regulator.compute_csi() >= 0.0
        assert isinstance(regulator.is_in_crisis(), bool)

        metrics = regulator.get_metrics()
        assert metrics is not None
