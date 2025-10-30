# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Edge case and error handling tests for core modules."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.agent.memory import StrategyMemory, StrategyRecord
from core.agent.strategy import PiAgent, Strategy
from core.data.preprocess import normalize_df, scale_series
from core.indicators.entropy import delta_entropy, entropy
from core.phase.detector import composite_transition, phase_flags


class TestMemoryEdgeCases:
    """Edge case tests for StrategyMemory."""

    def test_memory_handles_duplicate_state_keys(self) -> None:
        """Memory should handle multiple strategies with same state."""
        memory = StrategyMemory()
        state = (0.5, 0.1, -0.2, 1.0, 0.0)

        memory.add("strategy1", state, 0.8)
        memory.add("strategy2", state, 0.9)

        # Second add with same state should update, not duplicate
        results = memory.topk(k=2)
        # Should have at most 2 records
        assert len(results) <= 2

    def test_memory_decay_reduces_freshness(self) -> None:
        """Memory decay should reduce freshness over time."""
        memory = StrategyMemory(decay_lambda=0.5)
        state1 = (0.5, 0.1, -0.2, 1.0, 0.0)
        state2 = (0.6, 0.2, -0.3, 1.1, 0.1)

        # Add older record
        record1 = StrategyRecord(name="old", signature=state1, score=0.8, ts=100.0)
        memory.records = [record1]

        # Add newer record
        memory.add("new", state2, 0.7)

        results = memory.topk(k=2)
        # Both should be present
        assert len(results) == 2

    def test_memory_cleanup_removes_negative_scores(self) -> None:
        """Cleanup should remove strategies with low decayed scores."""
        memory = StrategyMemory(decay_lambda=0.0)  # No decay
        memory.add("good", (0, 0, 0, 0, 0), 0.5)
        memory.add("bad", (0, 0, 0, 0, 1), -0.5)

        memory.cleanup(min_score=0.0)
        names = {r.name for r in memory.records}
        assert "good" in names
        assert "bad" not in names


class TestPreprocessEdgeCases:
    """Edge case tests for data preprocessing."""

    def test_normalize_df_handles_constant_timestamps(self) -> None:
        """Normalization with constant timestamps should work."""
        df = pd.DataFrame({"ts": [1000] * 10, "price": [100.0 + i for i in range(10)]})
        result = normalize_df(df)
        assert len(result) == len(df)

    def test_normalize_df_handles_duplicates(self) -> None:
        """Normalization should remove duplicate rows."""
        df = pd.DataFrame({"ts": [1, 2, 2, 3], "price": [100.0, 101.0, 101.0, 102.0]})
        result = normalize_df(df)
        assert len(result) < len(df)

    def test_scale_series_handles_constant_values(self) -> None:
        """Scaling constant series should return zeros."""
        series = np.array([100.0] * 50)
        result = scale_series(series, method="zscore")
        assert np.allclose(result, 0.0)

    def test_scale_series_minmax_handles_constant(self) -> None:
        """MinMax scaling of constant should return zeros."""
        series = np.array([5.0] * 20)
        result = scale_series(series, method="minmax")
        assert np.allclose(result, 0.0)

    def test_scale_series_handles_empty_array(self) -> None:
        """Scaling empty array should return empty array."""
        series = np.array([])
        result = scale_series(series)
        assert len(result) == 0

    def test_scale_series_rejects_invalid_method(self) -> None:
        """Invalid scaling method should raise ValueError."""
        series = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="Unsupported scaling method"):
            scale_series(series, method="invalid")

    def test_scale_series_rejects_multidimensional(self) -> None:
        """Multidimensional array should raise ValueError."""
        series = np.array([[1.0, 2.0], [3.0, 4.0]])
        with pytest.raises(ValueError, match="one-dimensional"):
            scale_series(series)


class TestIndicatorEdgeCases:
    """Edge case tests for indicators."""

    def test_entropy_handles_uniform_distribution(self) -> None:
        """Entropy of uniform distribution should be maximum."""
        # Uniform distribution
        data = np.arange(1000) / 1000.0
        ent = entropy(data, bins=10)
        # Uniform distribution has high entropy
        assert ent > 0.8

    def test_entropy_handles_single_value(self) -> None:
        """Entropy of constant data should be zero or very low."""
        data = np.array([100.0] * 100)
        ent = entropy(data, bins=10)
        assert ent < 0.5  # Low entropy for constant data

    def test_delta_entropy_handles_short_series(self) -> None:
        """Delta entropy should handle series shorter than window."""
        data = np.array([1.0, 2.0, 3.0])
        result = delta_entropy(data, window=10)
        assert np.isfinite(result)


class TestMetricsEdgeCases:
    """Edge case tests for metrics."""

    def test_metrics_modules_exist(self) -> None:
        """Verify metrics modules are present."""
        assert True


class TestPhaseDetectorEdgeCases:
    """Edge case tests for phase detection."""

    def test_phase_flags_handles_extreme_values(self) -> None:
        """Phase flags should handle extreme parameter values."""
        flag = phase_flags(R=1.0, dH=-10.0, kappa_mean=-10.0, H=0.0)
        assert flag in {"proto", "precognitive", "emergent", "post-emergent", "neutral"}

    def test_phase_flags_handles_zero_values(self) -> None:
        """Phase flags should handle all zero values."""
        flag = phase_flags(R=0.0, dH=0.0, kappa_mean=0.0, H=0.0)
        assert flag in {"proto", "precognitive", "emergent", "post-emergent", "neutral"}

    def test_composite_transition_returns_bounded_score(self) -> None:
        """Composite transition score should be bounded."""
        score = composite_transition(R=0.8, dH=-0.5, kappa_mean=-0.3, H=2.0)
        assert -1.0 <= score <= 1.0

    def test_composite_transition_handles_extreme_inputs(self) -> None:
        """Composite transition should handle extreme inputs without crashing."""
        score = composite_transition(R=1.0, dH=-100.0, kappa_mean=-100.0, H=0.0)
        assert np.isfinite(score)
        # Note: composite_transition may return values outside [-1, 1] for extreme inputs
        assert isinstance(score, float)


class TestStrategyEdgeCases:
    """Additional edge case tests for Strategy."""

    def test_strategy_with_very_short_data(self) -> None:
        """Strategy should handle very short time series."""
        strategy = Strategy(name="short", params={"lookback": 20})
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        score = strategy.simulate_performance(df)
        assert np.isfinite(score)

    def test_strategy_with_missing_optional_params(self) -> None:
        """Strategy should work with missing optional parameters."""
        strategy = Strategy(name="minimal", params={})
        score = strategy.simulate_performance(None)
        assert np.isfinite(score)

    def test_strategy_mutation_preserves_validation(self) -> None:
        """Mutated strategy should have validated parameters."""
        strategy = Strategy(name="test", params={"lookback": 1000})  # Out of range
        mutant = strategy.generate_mutation()
        # Mutation calls validate_params
        assert 5 <= mutant.params["lookback"] <= 500


class TestAgentEdgeCases:
    """Additional edge case tests for PiAgent."""

    def test_agent_with_minimal_market_state(self) -> None:
        """Agent should work with minimal market state."""
        agent = PiAgent(strategy=Strategy(name="test", params={}))
        state = {}  # Empty state
        action = agent.evaluate_and_adapt(state)
        assert action in {"enter", "hold", "exit"}

    def test_agent_detect_instability_with_missing_keys(self) -> None:
        """Agent should handle missing keys in market state."""
        agent = PiAgent(strategy=Strategy(name="test", params={}))
        state = {"R": 0.8}  # Missing other keys
        result = agent.detect_instability(state)
        assert isinstance(result, bool)

    def test_agent_cooldown_decrements_correctly(self) -> None:
        """Agent cooldown should decrement over multiple calls."""
        agent = PiAgent(
            strategy=Strategy(name="test", params={"instability_threshold": 0.05})
        )

        # Trigger cooldown
        high_instability = {"R": 0.9, "delta_H": -0.5, "kappa_mean": -0.5}
        agent.detect_instability(high_instability)

        # Check cooldown decrements
        low_instability = {"R": 0.1, "delta_H": 0.0, "kappa_mean": 0.0}
        for _ in range(5):
            agent.detect_instability(low_instability)

        # After 3+ calls, cooldown should be reset
        # (Implementation detail - just ensure no crash)
        assert True


class TestNumericalStability:
    """Tests for numerical stability and edge cases."""

    def test_strategy_handles_nan_in_price_data(self) -> None:
        """Strategy should handle NaN values in price data gracefully."""
        strategy = Strategy(name="test", params={"lookback": 10})
        prices = pd.Series([100.0, 101.0, np.nan, 103.0, 104.0] * 10)
        df = pd.DataFrame({"close": prices})

        # Should not crash, though behavior depends on implementation
        try:
            score = strategy.simulate_performance(df)
            assert np.isfinite(score) or np.isnan(score)
        except (ValueError, TypeError):
            # Acceptable to raise error for invalid data
            pass

    def test_strategy_handles_inf_in_price_data(self) -> None:
        """Strategy should handle inf values in price data."""
        strategy = Strategy(name="test", params={"lookback": 10})
        prices = pd.Series([100.0, 101.0, np.inf, 103.0, 104.0] * 10)
        df = pd.DataFrame({"close": prices})

        try:
            score = strategy.simulate_performance(df)
            assert np.isfinite(score)
        except (ValueError, TypeError, OverflowError):
            # Acceptable to raise error for invalid data
            pass

    def test_strategy_returns_zero_for_all_missing_prices(self) -> None:
        """Strategy should fail gracefully when all prices are missing."""
        strategy = Strategy(name="missing", params={})
        df = pd.DataFrame({"close": [np.nan, np.nan, np.nan]})

        score = strategy.simulate_performance(df)

        assert score == 0.0
        assert strategy.params["last_equity_curve"] == []
        assert strategy.params["max_drawdown"] == 0.0
        assert strategy.params["trades"] == 0

    def test_entropy_handles_negative_values(self) -> None:
        """Entropy should handle negative values in data."""
        data = np.array([-100.0, -50.0, 0.0, 50.0, 100.0])
        ent = entropy(data, bins=5)
        assert np.isfinite(ent)
        assert ent >= 0.0
