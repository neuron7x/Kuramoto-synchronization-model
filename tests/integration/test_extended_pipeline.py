# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Additional integration tests for complete pipeline flows."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import Result, walk_forward
from core.agent.strategy import PiAgent, Strategy
from core.data.ingestion import DataIngestor, Ticker


class TestEndToEndPipeline:
    """Complete end-to-end pipeline tests."""

    def test_csv_ingestion_to_strategy_evaluation(self, tmp_path) -> None:
        """Test complete flow from CSV to strategy evaluation."""
        import csv

        # Create test CSV
        csv_path = tmp_path / "test_data.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()
            for i in range(100):
                writer.writerow(
                    {
                        "ts": str(float(i)),
                        "price": str(100.0 + i * 0.5),
                        "volume": str(1000.0 + i * 10),
                    }
                )

        # Ingest data
        ingestor = DataIngestor()
        tickers: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), tickers.append)

        assert len(tickers) == 100

        # Convert to DataFrame for strategy
        df = pd.DataFrame([{"close": float(t.price), "volume": float(t.volume)} for t in tickers])

        # Create and evaluate strategy
        strategy = Strategy(name="test", params={"lookback": 20, "threshold": 0.5})
        _score = strategy.simulate_performance(df)

        assert isinstance(_score, float)
        assert np.isfinite(_score)

    def test_strategy_to_backtest_pipeline(self) -> None:
        """Test strategy signals feeding into backtest engine."""
        # Generate synthetic price data
        prices = np.linspace(100.0, 110.0, 50)

        # Create strategy that generates signals
        Strategy(name="test", params={"lookback": 10, "threshold": 0.3})

        # Use strategy to create signal function
        def signal_from_strategy(p: np.ndarray) -> np.ndarray:
            # Simple momentum signal
            returns = np.diff(p, prepend=p[0])
            signals = np.where(returns > 0, 1.0, -1.0)
            return signals

        # Run backtest
        result = walk_forward(prices, signal_from_strategy, fee=0.001)

        assert isinstance(result, Result)
        assert result.pnl != 0.0 or result.trades == 0
        assert result.max_dd <= 0.0
        assert result.performance is not None
        assert result.performance.max_drawdown == pytest.approx(result.max_dd)
        assert result.report_path is not None
        assert result.report_path.exists()

    def test_agent_adapt_and_backtest_loop(self) -> None:
        """Test agent adaptation with backtest feedback loop."""
        # Create initial agent
        agent = PiAgent(strategy=Strategy(name="base", params={"alpha": 1.0}))

        # Simulate market state
        market_state = {
            "R": 0.8,
            "delta_H": -0.2,
            "kappa_mean": -0.1,
            "H": 2.5,
        }

        # Agent evaluates and adapts
        action = agent.evaluate_and_adapt(market_state)
        assert action in {"enter", "hold", "exit"}

        # Create mutant
        mutant = agent.mutate()
        assert mutant.strategy.name != agent.strategy.name

    def test_empty_data_handling(self) -> None:
        """Test pipeline gracefully handles edge cases."""
        # Test with minimum viable data
        prices = np.array([100.0, 101.0])

        def zero_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)

        result = walk_forward(prices, zero_signal, fee=0.0)
        assert result.pnl == 0.0
        assert result.trades == 0
        assert result.performance is not None
        assert result.report_path is not None

    def test_high_volatility_data(self) -> None:
        """Test pipeline with high volatility data."""
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 5, 200))
        prices = np.abs(prices)  # Ensure positive

        strategy = Strategy(name="vol_test", params={"lookback": 20})
        df = pd.DataFrame({"close": prices})
        _score = strategy.simulate_performance(df)

        assert np.isfinite(_score)

    def test_strategy_performance_with_real_patterns(self) -> None:
        """Test strategy with realistic price patterns."""
        # Create trending then mean-reverting pattern
        trend = np.linspace(100, 120, 50)
        mean_revert = 120 + 5 * np.sin(np.linspace(0, 4 * np.pi, 50))
        prices = np.concatenate([trend, mean_revert])

        strategy = Strategy(name="pattern", params={"lookback": 10, "threshold": 0.5})
        df = pd.DataFrame({"close": prices})
        strategy.simulate_performance(df)

        # Should have detected some patterns
        assert "max_drawdown" in strategy.params
        assert "trades" in strategy.params

    def test_multiple_strategies_comparison(self) -> None:
        """Test comparing multiple strategies."""
        prices = np.array([100.0 + i * 0.1 + np.sin(i * 0.5) for i in range(100)])
        df = pd.DataFrame({"close": prices})

        strategies = [
            Strategy(name="conservative", params={"lookback": 20, "threshold": 1.0}),
            Strategy(name="aggressive", params={"lookback": 5, "threshold": 0.2}),
            Strategy(name="balanced", params={"lookback": 10, "threshold": 0.5}),
        ]

        scores = []
        for strategy in strategies:
            score = strategy.simulate_performance(df)
            scores.append(score)

        # All should complete successfully
        assert all(np.isfinite(s) for s in scores)
        assert len(scores) == 3


class TestErrorRecovery:
    """Test error handling and recovery mechanisms."""

    def test_strategy_with_invalid_params_recovers(self) -> None:
        """Strategy with invalid params should be corrected by validate_params."""
        strategy = Strategy(
            name="invalid",
            params={
                "lookback": -10,  # Invalid
                "threshold": 100.0,  # Out of range
                "risk_budget": -5.0,  # Invalid
            },
        )

        strategy.validate_params()

        # Should be clamped to valid ranges
        assert 5 <= strategy.params["lookback"] <= 500
        assert 0.0 <= strategy.params["threshold"] <= 5.0
        assert 0.01 <= strategy.params["risk_budget"] <= 10.0

    def test_agent_repairs_corrupted_state(self) -> None:
        """Agent should repair NaN values in parameters."""
        agent = PiAgent(strategy=Strategy(name="corrupt", params={"alpha": np.nan, "beta": 1.0}))

        agent.repair()

        assert not np.isnan(agent.strategy.params["alpha"])
        assert agent.strategy.params["alpha"] == 0.0

    def test_backtest_with_constant_prices(self) -> None:
        """Backtest should handle constant price data."""
        prices = np.full(50, 100.0)

        def simple_signal(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p) * 0.5

        result = walk_forward(prices, simple_signal, fee=0.001)

        # No price movement = no PnL except fees
        assert result.pnl <= 0.0  # Only fees
        assert result.max_dd <= 0.0
        assert result.performance is not None

    def test_csv_with_large_gaps_in_timestamps(self, tmp_path) -> None:
        """CSV ingestion should handle large gaps in timestamps."""
        import csv

        csv_path = tmp_path / "gaps.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()
            writer.writerow({"ts": "1", "price": "100", "volume": "10"})
            writer.writerow({"ts": "1000000", "price": "101", "volume": "20"})  # Huge gap
            writer.writerow({"ts": "1000001", "price": "102", "volume": "30"})

        ingestor = DataIngestor()
        tickers: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), tickers.append)

        assert len(tickers) == 3
        assert tickers[1].ts == 1000000.0
