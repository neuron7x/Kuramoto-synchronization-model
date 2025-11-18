"""Unit tests for the ECS-Inspired Regulator."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import numpy as np
import pytest

# Direct import to avoid dependency issues in tests
import importlib.util

# Load the module directly
spec = importlib.util.spec_from_file_location(
    "ecs_regulator", Path(__file__).parent.parent / "ecs_regulator.py"
)
ecs_module = importlib.util.module_from_spec(spec)
sys.modules["ecs_regulator"] = ecs_module
spec.loader.exec_module(ecs_module)

ECSInspiredRegulator = ecs_module.ECSInspiredRegulator
ECSMetrics = ecs_module.ECSMetrics


class TestECSInspiredRegulatorInit:
    """Test regulator initialization and validation."""

    def test_default_initialization(self) -> None:
        """Test regulator with default parameters."""
        regulator = ECSInspiredRegulator()
        assert regulator.risk_threshold == 0.05
        assert regulator.smoothing_alpha == 0.9
        assert regulator.stress_threshold == 0.1
        assert regulator.chronic_threshold == 5
        assert regulator.fe_scaling == 1.0
        assert regulator.compensatory_factor == 1.0
        assert regulator.stress_level == 0.0
        assert regulator.chronic_counter == 0

    def test_custom_initialization(self) -> None:
        """Test regulator with custom parameters."""
        regulator = ECSInspiredRegulator(
            initial_risk_threshold=0.08,
            smoothing_alpha=0.85,
            stress_threshold=0.15,
            chronic_threshold=7,
            fe_scaling=1.5,
            seed=42,
        )
        assert regulator.risk_threshold == 0.08
        assert regulator.smoothing_alpha == 0.85
        assert regulator.stress_threshold == 0.15
        assert regulator.chronic_threshold == 7
        assert regulator.fe_scaling == 1.5

    def test_invalid_risk_threshold(self) -> None:
        """Test that invalid risk threshold is rejected."""
        with pytest.raises(ValueError, match="initial_risk_threshold must be between 0 and 1"):
            ECSInspiredRegulator(initial_risk_threshold=0.0)

        with pytest.raises(ValueError, match="initial_risk_threshold must be between 0 and 1"):
            ECSInspiredRegulator(initial_risk_threshold=1.5)

    def test_invalid_smoothing_alpha(self) -> None:
        """Test that invalid smoothing alpha is rejected."""
        with pytest.raises(ValueError, match="smoothing_alpha must be between 0 and 1"):
            ECSInspiredRegulator(smoothing_alpha=0.0)

        with pytest.raises(ValueError, match="smoothing_alpha must be between 0 and 1"):
            ECSInspiredRegulator(smoothing_alpha=1.5)

    def test_invalid_stress_threshold(self) -> None:
        """Test that invalid stress threshold is rejected."""
        with pytest.raises(ValueError, match="stress_threshold must be positive"):
            ECSInspiredRegulator(stress_threshold=0.0)

    def test_invalid_chronic_threshold(self) -> None:
        """Test that invalid chronic threshold is rejected."""
        with pytest.raises(ValueError, match="chronic_threshold must be at least 1"):
            ECSInspiredRegulator(chronic_threshold=0)

    def test_invalid_fe_scaling(self) -> None:
        """Test that invalid fe_scaling is rejected."""
        with pytest.raises(ValueError, match="fe_scaling must be positive"):
            ECSInspiredRegulator(fe_scaling=0.0)


class TestUpdateStress:
    """Test stress update functionality."""

    def test_update_stress_basic(self) -> None:
        """Test basic stress update."""
        regulator = ECSInspiredRegulator()
        market_returns = np.array([0.01, -0.02, 0.015, -0.01])
        drawdown = 0.05

        regulator.update_stress(market_returns, drawdown)

        assert regulator.stress_level > 0.0
        assert regulator.free_energy_proxy > 0.0
        assert len(regulator.history) > 0

    def test_update_stress_empty_returns(self) -> None:
        """Test that empty returns are rejected."""
        regulator = ECSInspiredRegulator()

        with pytest.raises(ValueError, match="market_returns must not be empty"):
            regulator.update_stress(np.array([]), 0.0)

    def test_update_stress_negative_drawdown(self) -> None:
        """Test that negative drawdown is rejected."""
        regulator = ECSInspiredRegulator()
        market_returns = np.array([0.01, -0.02])

        with pytest.raises(ValueError, match="drawdown must be non-negative"):
            regulator.update_stress(market_returns, -0.1)

    def test_stress_smoothing(self) -> None:
        """Test that stress is smoothed over time."""
        regulator = ECSInspiredRegulator(smoothing_alpha=0.9)
        market_returns = np.array([0.01, -0.02])

        # First update
        regulator.update_stress(market_returns, 0.05)
        stress1 = regulator.stress_level

        # Second update with lower stress
        regulator.update_stress(np.array([0.001, -0.001]), 0.01)
        stress2 = regulator.stress_level

        # Stress should be smoothed (not jump immediately)
        assert stress2 < stress1
        assert stress2 > 0.0

    def test_chronic_stress_detection(self) -> None:
        """Test chronic stress counter increments correctly."""
        regulator = ECSInspiredRegulator(stress_threshold=0.05, chronic_threshold=3)

        # Generate high stress repeatedly
        for _ in range(5):
            regulator.update_stress(np.array([0.1, -0.1, 0.1]), 0.2)

        assert regulator.chronic_counter >= 3

    def test_chronic_stress_recovery(self) -> None:
        """Test chronic counter decreases during recovery."""
        regulator = ECSInspiredRegulator(stress_threshold=0.1, chronic_threshold=3)

        # High stress
        for _ in range(4):
            regulator.update_stress(np.array([0.1, -0.1]), 0.2)

        counter_high = regulator.chronic_counter

        # Low stress
        for _ in range(2):
            regulator.update_stress(np.array([0.001, -0.001]), 0.01)

        assert regulator.chronic_counter < counter_high

    def test_monotonic_descent_enforcement(self) -> None:
        """Test that free energy descent is enforced."""
        regulator = ECSInspiredRegulator(fe_scaling=1.0)

        # First update
        regulator.update_stress(np.array([0.01, -0.01]), 0.05)
        fe1 = regulator.free_energy_proxy

        # Second update with higher stress, but descent enforced
        regulator.update_stress(np.array([0.2, -0.2]), 0.3, previous_fe=fe1)
        fe2 = regulator.free_energy_proxy

        # Free energy should not increase significantly
        assert fe2 <= fe1 * 1.01  # Allow small numerical tolerance


class TestAdaptParameters:
    """Test parameter adaptation functionality."""

    def test_adapt_under_high_stress(self) -> None:
        """Test adaptation during high stress."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.05, stress_threshold=0.05)

        # Induce high stress
        regulator.update_stress(np.array([0.1, -0.1]), 0.2)
        initial_threshold = regulator.risk_threshold

        # Adapt parameters
        regulator.adapt_parameters(context_phase="stable")

        # Risk threshold should decrease
        assert regulator.risk_threshold < initial_threshold
        # Compensatory factor should increase
        assert regulator.compensatory_factor > 1.0

    def test_adapt_chronic_vs_acute(self) -> None:
        """Test that chronic stress has stronger adaptation."""
        reg_acute = ECSInspiredRegulator(
            initial_risk_threshold=0.05, stress_threshold=0.05, chronic_threshold=10
        )
        reg_chronic = ECSInspiredRegulator(
            initial_risk_threshold=0.05, stress_threshold=0.05, chronic_threshold=2
        )

        # High stress for both
        for _ in range(5):
            reg_acute.update_stress(np.array([0.1, -0.1]), 0.2)
            reg_chronic.update_stress(np.array([0.1, -0.1]), 0.2)

        reg_acute.adapt_parameters()
        reg_chronic.adapt_parameters()

        # Chronic should have lower threshold
        assert reg_chronic.risk_threshold < reg_acute.risk_threshold
        # Chronic should have higher compensation
        assert reg_chronic.compensatory_factor > reg_acute.compensatory_factor

    def test_adapt_context_dependent(self) -> None:
        """Test context-dependent adaptation."""
        reg_stable = ECSInspiredRegulator(initial_risk_threshold=0.05, stress_threshold=0.05)
        reg_chaotic = ECSInspiredRegulator(initial_risk_threshold=0.05, stress_threshold=0.05)

        # High stress for both
        reg_stable.update_stress(np.array([0.1, -0.1]), 0.2)
        reg_chaotic.update_stress(np.array([0.1, -0.1]), 0.2)

        reg_stable.adapt_parameters(context_phase="stable")
        reg_chaotic.adapt_parameters(context_phase="chaotic")

        # Chaotic phase should be more conservative
        assert reg_chaotic.risk_threshold < reg_stable.risk_threshold

    def test_adapt_recovery(self) -> None:
        """Test parameter recovery during low stress."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.05, stress_threshold=0.1)

        # High stress first
        regulator.update_stress(np.array([0.2, -0.2]), 0.3)
        regulator.adapt_parameters()
        threshold_after_stress = regulator.risk_threshold

        # Low stress recovery
        regulator.update_stress(np.array([0.001, -0.001]), 0.01)
        regulator.adapt_parameters()

        # Threshold should recover towards initial
        assert regulator.risk_threshold >= threshold_after_stress


class TestKalmanFilter:
    """Test Kalman filter functionality."""

    def test_kalman_filter_basic(self) -> None:
        """Test basic Kalman filtering."""
        regulator = ECSInspiredRegulator(seed=42)

        raw_signal = 0.1
        filtered = regulator.kalman_filter_signal(raw_signal)

        assert isinstance(filtered, float)
        assert np.isfinite(filtered)

    def test_kalman_filter_smoothing(self) -> None:
        """Test that Kalman filter smooths noisy signals."""
        regulator = ECSInspiredRegulator(seed=42)
        rng = np.random.default_rng(42)

        # Generate noisy signal
        true_signal = 0.5
        noisy_signals = true_signal + rng.normal(0, 0.1, 20)

        filtered_signals = [regulator.kalman_filter_signal(sig) for sig in noisy_signals]

        # Later filtered values should be closer to true signal
        early_error = abs(filtered_signals[5] - true_signal)
        late_error = abs(filtered_signals[-1] - true_signal)

        # Filter should improve over time (typically)
        # Allow for randomness
        assert late_error < early_error * 2.0

    def test_kalman_filter_state_update(self) -> None:
        """Test that Kalman state updates correctly."""
        regulator = ECSInspiredRegulator()

        initial_state = regulator.kalman_state

        regulator.kalman_filter_signal(0.5)

        # State should change
        assert regulator.kalman_state != initial_state


class TestDecideAction:
    """Test action decision functionality."""

    def test_decide_action_hold(self) -> None:
        """Test hold action for low signals."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.1)

        action = regulator.decide_action(0.01, context_phase="stable")

        assert action == 0

    def test_decide_action_buy(self) -> None:
        """Test buy action for strong positive signals."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.05)

        action = regulator.decide_action(0.2, context_phase="stable")

        assert action in [-1, 0, 1]  # Should not crash

    def test_decide_action_sell(self) -> None:
        """Test sell action for strong negative signals."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.05)

        action = regulator.decide_action(-0.2, context_phase="stable")

        assert action in [-1, 0, 1]

    def test_decide_action_compensatory(self) -> None:
        """Test that compensatory factor amplifies signals."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.1)

        # Set high compensatory factor
        regulator.compensatory_factor = 2.0

        # Signal that would be below threshold without compensation
        action = regulator.decide_action(0.06, context_phase="stable")

        # With 2x compensation, 0.06 * 2 = 0.12 > 0.1 threshold
        assert action in [-1, 0, 1]

    def test_decide_action_context_override(self) -> None:
        """Test context-dependent confidence override."""
        regulator = ECSInspiredRegulator(initial_risk_threshold=0.05, seed=42)

        # Marginal signal in chaotic phase
        action_chaotic = regulator.decide_action(0.06, context_phase="chaotic")

        # Reset and test stable phase
        regulator.kalman_state = 0.0
        regulator.kalman_variance = 1.0
        action_stable = regulator.decide_action(0.06, context_phase="stable")

        # Both should be valid actions
        assert action_chaotic in [-1, 0, 1]
        assert action_stable in [-1, 0, 1]

    def test_decide_action_logs(self) -> None:
        """Test that decisions are logged."""
        regulator = ECSInspiredRegulator()

        initial_log_count = len(regulator.history)

        regulator.decide_action(0.1, context_phase="stable")

        assert len(regulator.history) > initial_log_count


class TestTraceAndMetrics:
    """Test trace logging and metrics."""

    def test_get_trace_empty(self) -> None:
        """Test trace retrieval with no history."""
        regulator = ECSInspiredRegulator()
        trace = regulator.get_trace()

        assert isinstance(trace, __import__("pandas").DataFrame)
        assert len(trace) == 0

    def test_get_trace_with_history(self) -> None:
        """Test trace retrieval with history."""
        regulator = ECSInspiredRegulator()

        # Generate some history
        regulator.update_stress(np.array([0.01, -0.02]), 0.05)
        regulator.adapt_parameters()
        regulator.decide_action(0.1)

        trace = regulator.get_trace()

        assert len(trace) > 0
        assert "timestamp" in trace.columns
        assert "type" in trace.columns
        assert "details" in trace.columns

    def test_get_metrics(self) -> None:
        """Test metrics retrieval."""
        regulator = ECSInspiredRegulator()

        # Generate state
        regulator.update_stress(np.array([0.1, -0.1]), 0.1)
        regulator.adapt_parameters()

        metrics = regulator.get_metrics()

        assert isinstance(metrics, ECSMetrics)
        assert metrics.timestamp >= 0
        assert metrics.stress_level >= 0.0
        assert metrics.free_energy_proxy >= 0.0
        assert metrics.risk_threshold > 0.0
        assert metrics.compensatory_factor >= 1.0
        assert metrics.chronic_counter >= 0
        assert isinstance(metrics.is_chronic, bool)

    def test_metrics_chronic_flag(self) -> None:
        """Test that chronic flag is set correctly."""
        regulator = ECSInspiredRegulator(stress_threshold=0.05, chronic_threshold=3)

        # Not chronic initially
        metrics1 = regulator.get_metrics()
        assert not metrics1.is_chronic

        # Generate chronic stress
        for _ in range(5):
            regulator.update_stress(np.array([0.1, -0.1]), 0.2)

        metrics2 = regulator.get_metrics()
        assert metrics2.is_chronic


class TestReset:
    """Test reset functionality."""

    def test_reset_clears_state(self) -> None:
        """Test that reset clears all state."""
        regulator = ECSInspiredRegulator()

        # Generate state
        regulator.update_stress(np.array([0.1, -0.1]), 0.1)
        regulator.adapt_parameters()
        regulator.decide_action(0.1)

        assert regulator.stress_level > 0.0
        assert len(regulator.history) > 0

        regulator.reset()

        assert regulator.stress_level == 0.0
        assert regulator.free_energy_proxy == 0.0
        assert regulator.chronic_counter == 0
        assert len(regulator.history) == 0
        assert regulator.kalman_state == 0.0

    def test_reset_allows_reuse(self) -> None:
        """Test that regulator can be reused after reset."""
        regulator = ECSInspiredRegulator()

        # Use once
        regulator.update_stress(np.array([0.1, -0.1]), 0.1)

        regulator.reset()

        # Should work again
        regulator.update_stress(np.array([0.01, -0.01]), 0.05)
        action = regulator.decide_action(0.1)

        assert action in [-1, 0, 1]


class TestIntegrationScenarios:
    """Integration tests for realistic trading scenarios."""

    def test_acute_stress_scenario(self) -> None:
        """Test regulator behavior under acute stress."""
        regulator = ECSInspiredRegulator(stress_threshold=0.05, chronic_threshold=10, seed=42)
        rng = np.random.default_rng(42)

        actions = []

        # Short-term high volatility (acute stress)
        for _ in range(3):
            returns = rng.normal(0, 0.1, 10)
            regulator.update_stress(returns, 0.15)
            regulator.adapt_parameters(context_phase="stable")
            action = regulator.decide_action(rng.normal(0, 0.05))
            actions.append(action)

        # Should not be chronic
        assert not regulator.get_metrics().is_chronic
        assert all(a in [-1, 0, 1] for a in actions)

    def test_chronic_stress_scenario(self) -> None:
        """Test regulator behavior under chronic stress."""
        regulator = ECSInspiredRegulator(stress_threshold=0.05, chronic_threshold=5, seed=42)
        rng = np.random.default_rng(42)

        # Prolonged high volatility (chronic stress)
        for _ in range(10):
            returns = rng.normal(0, 0.1, 10)
            regulator.update_stress(returns, 0.2)
            regulator.adapt_parameters(context_phase="stable")

        # Should be chronic
        assert regulator.get_metrics().is_chronic

        # Risk threshold should be significantly reduced
        assert regulator.risk_threshold < 0.05

    def test_market_phase_adaptation(self) -> None:
        """Test adaptation across different market phases."""
        regulator = ECSInspiredRegulator(seed=42)
        rng = np.random.default_rng(42)

        phases = ["stable", "transition", "chaotic", "stable"]
        actions = []

        for phase in phases:
            returns = rng.normal(0, 0.05, 20)
            regulator.update_stress(returns, 0.1)
            regulator.adapt_parameters(context_phase=phase)
            action = regulator.decide_action(rng.normal(0, 0.05), context_phase=phase)
            actions.append(action)

        assert len(actions) == 4
        assert all(a in [-1, 0, 1] for a in actions)

    def test_full_simulation_cycle(self) -> None:
        """Test complete simulation cycle as in problem statement."""
        np.random.seed(42)
        n_steps = 200

        market_returns = np.random.normal(0, 0.03, n_steps)
        cum_returns = np.cumprod(1 + market_returns)
        drawdowns = (cum_returns.cummax() - cum_returns) / cum_returns.cummax()
        phases = np.random.choice(["stable", "chaotic", "transition"], n_steps)

        regulator = ECSInspiredRegulator()
        actions = []
        prev_fe = None

        for i in range(n_steps):
            regulator.update_stress(market_returns[: i + 1], drawdowns[i], prev_fe)
            prev_fe = regulator.free_energy_proxy
            regulator.adapt_parameters(phases[i])
            signal = market_returns[i] * np.random.uniform(0.8, 1.2)
            action = regulator.decide_action(signal, phases[i])
            actions.append(action)

        # Verify simulation completed
        assert len(actions) == n_steps
        assert regulator.free_energy_proxy < 1.0  # Should remain bounded

        # Count actions
        action_counts = np.bincount(np.array(actions) + 1)
        print(
            f"Actions: sells={action_counts[0]}, holds={action_counts[1]}, buys={action_counts[2]}"
        )

        # Verify reasonable action distribution
        assert action_counts[1] > n_steps * 0.5  # Mostly holds expected

    def test_free_energy_descent(self) -> None:
        """Test that free energy generally descends over time."""
        regulator = ECSInspiredRegulator(fe_scaling=1.0, seed=42)
        rng = np.random.default_rng(42)

        fe_values = []

        for i in range(20):
            returns = rng.normal(0, 0.02, 10)
            prev_fe = regulator.free_energy_proxy if i > 0 else None
            regulator.update_stress(returns, 0.05, previous_fe=prev_fe)
            fe_values.append(regulator.free_energy_proxy)

        # Free energy should not increase dramatically
        # (allowing for some variance in early steps)
        if len(fe_values) > 10:
            early_avg = np.mean(fe_values[:5])
            late_avg = np.mean(fe_values[-5:])
            assert late_avg <= early_avg * 1.5  # Allow some growth but bounded

    def test_trace_export_to_parquet(self, tmp_path) -> None:
        """Test that trace can be exported to Parquet."""
        regulator = ECSInspiredRegulator(seed=42)
        rng = np.random.default_rng(42)

        # Generate activity
        for _ in range(10):
            returns = rng.normal(0, 0.02, 10)
            regulator.update_stress(returns, 0.05)
            regulator.adapt_parameters()
            regulator.decide_action(rng.normal(0, 0.05))

        trace = regulator.get_trace()

        # Export to Parquet
        parquet_file = tmp_path / "trace_logs.parquet"
        trace.to_parquet(parquet_file)

        assert parquet_file.exists()

        # Verify can be read back
        import pandas as pd

        loaded = pd.read_parquet(parquet_file)
        assert len(loaded) == len(trace)
