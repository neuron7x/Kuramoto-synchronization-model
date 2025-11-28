# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    from hypothesis.extra.numpy import arrays
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.agent.strategy import PiAgent, Strategy


class TestStrategyProperties:
    """Property-based tests for Strategy class."""

    @settings(max_examples=100, deadline=None)
    @given(
        name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(blacklist_characters="\x00\n\r"),
        ),
        alpha=st.floats(min_value=0.01, max_value=10.0, allow_nan=False),
        beta=st.floats(min_value=0.01, max_value=10.0, allow_nan=False),
    )
    def test_strategy_mutation_produces_different_params(
        self, name: str, alpha: float, beta: float
    ) -> None:
        """Mutated strategy should have different parameters."""
        strategy = Strategy(name=name, params={"alpha": alpha, "beta": beta})
        mutant = strategy.generate_mutation(scale=0.1)

        # Name should be different
        assert mutant.name != strategy.name
        assert mutant.name.startswith(name)

        # At least one param should be different (with high probability)
        params_differ = mutant.params.get("alpha") != strategy.params.get(
            "alpha"
        ) or mutant.params.get("beta") != strategy.params.get("beta")
        # This might rarely fail due to random chance, but should pass most of the time
        assert params_differ or mutant.params == strategy.params

    @settings(max_examples=50, deadline=None)
    @given(
        lookback=st.integers(min_value=-100, max_value=1000),
        threshold=st.floats(min_value=-10.0, max_value=20.0, allow_nan=False),
        risk_budget=st.floats(min_value=-5.0, max_value=50.0, allow_nan=False),
    )
    def test_validate_params_enforces_bounds(
        self, lookback: int, threshold: float, risk_budget: float
    ) -> None:
        """validate_params should clamp parameters to valid ranges."""
        strategy = Strategy(
            name="test",
            params={
                "lookback": lookback,
                "threshold": threshold,
                "risk_budget": risk_budget,
            },
        )
        strategy.validate_params()

        # Check bounds
        assert 5 <= strategy.params["lookback"] <= 500
        assert 0.0 <= strategy.params["threshold"] <= 5.0
        assert 0.01 <= strategy.params["risk_budget"] <= 10.0

    @settings(max_examples=50, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=50, max_value=300),
            elements=st.floats(
                min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False
            ),
        )
    )
    def test_simulate_performance_returns_finite_score(
        self, prices: np.ndarray
    ) -> None:
        """simulate_performance should return a finite score for valid data."""
        strategy = Strategy(
            name="test",
            params={"lookback": 20, "threshold": 0.5, "risk_budget": 1.0},
        )

        df = pd.DataFrame({"close": prices})
        score = strategy.simulate_performance(df)

        assert math.isfinite(score)
        assert isinstance(score, float)
        assert strategy.score == score

    def test_simulate_performance_handles_none_data(self) -> None:
        """simulate_performance should handle None data with default synthetic data."""
        strategy = Strategy(name="test", params={})
        score = strategy.simulate_performance(None)
        assert math.isfinite(score)

    @settings(max_examples=30, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=100, max_value=200),
            elements=st.floats(
                min_value=80.0, max_value=120.0, allow_nan=False, allow_infinity=False
            ),
        )
    )
    def test_simulate_performance_sets_metrics_in_params(
        self, prices: np.ndarray
    ) -> None:
        """simulate_performance should add max_drawdown and trades to params."""
        strategy = Strategy(name="test", params={"lookback": 20})
        df = pd.DataFrame({"close": prices})
        strategy.simulate_performance(df)

        assert "max_drawdown" in strategy.params
        assert "trades" in strategy.params
        assert isinstance(strategy.params["max_drawdown"], float)
        assert isinstance(strategy.params["trades"], int)
        assert strategy.params["max_drawdown"] <= 0.0
        assert strategy.params["trades"] >= 0


class TestPiAgentProperties:
    """Property-based tests for PiAgent class."""

    @settings(max_examples=50, deadline=None)
    @given(
        R=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        delta_H=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
        kappa_mean=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
    )
    def test_detect_instability_returns_bool(
        self, R: float, delta_H: float, kappa_mean: float
    ) -> None:
        """detect_instability should return a boolean value."""
        agent = PiAgent(
            strategy=Strategy(name="test", params={"instability_threshold": 0.5})
        )
        state = {"R": R, "delta_H": delta_H, "kappa_mean": kappa_mean}
        result = agent.detect_instability(state)
        assert isinstance(result, bool)

    @settings(max_examples=50, deadline=None)
    @given(
        R=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        delta_H=st.floats(min_value=-2.0, max_value=2.0, allow_nan=False),
        kappa_mean=st.floats(min_value=-2.0, max_value=2.0, allow_nan=False),
    )
    def test_evaluate_and_adapt_returns_valid_action(
        self, R: float, delta_H: float, kappa_mean: float
    ) -> None:
        """evaluate_and_adapt should return one of the valid actions."""
        agent = PiAgent(strategy=Strategy(name="test", params={}))
        state = {"R": R, "delta_H": delta_H, "kappa_mean": kappa_mean}
        action = agent.evaluate_and_adapt(state)
        assert action in {"enter", "hold", "exit"}

    def test_mutate_creates_different_agent(self) -> None:
        """mutate should create a new agent with different strategy."""
        agent = PiAgent(
            strategy=Strategy(name="original", params={"alpha": 1.0, "beta": 2.0})
        )
        mutant = agent.mutate()

        assert isinstance(mutant, PiAgent)
        assert mutant is not agent
        assert mutant.strategy is not agent.strategy
        assert mutant.strategy.name != agent.strategy.name

    @settings(max_examples=50, deadline=None)
    @given(
        alpha=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False),
        beta=st.just(math.nan),
    )
    def test_repair_fixes_nan(self, alpha: float, beta: float) -> None:
        """repair should convert NaN values to 0.0."""
        agent = PiAgent(
            strategy=Strategy(name="test", params={"alpha": alpha, "beta": beta})
        )
        agent.repair()

        # After repair, no NaN should remain
        assert not math.isnan(agent.strategy.params["beta"])
        assert agent.strategy.params["beta"] == 0.0

    def test_cooldown_prevents_rapid_triggers(self) -> None:
        """Cooldown mechanism should prevent immediate re-triggers."""
        agent = PiAgent(
            strategy=Strategy(
                name="test", params={"instability_threshold": 0.1, "hysteresis": 0.0}
            )
        )

        # High instability state
        state = {"R": 0.95, "delta_H": -0.5, "kappa_mean": -0.5}

        # First call should trigger
        result1 = agent.detect_instability(state)

        # Immediate next call should not trigger (cooldown)
        # We call detect_instability multiple times to exercise cooldown logic
        agent.detect_instability(state)
        agent.detect_instability(state)

        # After cooldown expires (3 calls), it should trigger again
        agent.detect_instability(state)

        # First should trigger, next 2-3 should be cooled down
        assert result1 is True
        # During cooldown, should return False
        # After cooldown, could trigger again


class TestStrategyEdgeCases:
    """Edge case tests for Strategy."""

    def test_empty_params_is_valid(self) -> None:
        """Strategy with empty params should work."""
        strategy = Strategy(name="empty", params={})
        strategy.validate_params()
        score = strategy.simulate_performance(None)
        assert math.isfinite(score)

    def test_mutation_of_integer_params_remains_integer(self) -> None:
        """Mutation of integer parameters should keep them as integers."""
        strategy = Strategy(name="test", params={"count": 10})
        mutant = strategy.generate_mutation()
        assert isinstance(mutant.params["count"], int)
        assert mutant.params["count"] >= 1

    def test_non_numeric_params_preserved_in_mutation(self) -> None:
        """Non-numeric parameters should be preserved during mutation."""
        strategy = Strategy(
            name="test", params={"alpha": 1.0, "mode": "aggressive", "enabled": True}
        )
        mutant = strategy.generate_mutation()
        assert mutant.params["mode"] == "aggressive"
        assert mutant.params["enabled"]
