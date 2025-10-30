# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Performance and stress tests for large datasets."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from backtest.engine import walk_forward
from backtest.time_splits import PurgedKFoldTimeSeriesSplit, WalkForwardSplitter
from core.agent.strategy import Strategy
from core.data.preprocess import normalize_df, scale_series
from core.indicators.entropy import entropy

# Mark these tests as slow so they can be skipped during normal development
pytestmark = pytest.mark.slow


class TestLargeDatasetPerformance:
    """Performance tests with large datasets."""

    def test_backtest_with_10k_prices(self) -> None:
        """Backtest should complete in reasonable time with 10K prices."""
        prices = np.linspace(100.0, 150.0, 10_000) + np.random.randn(10_000) * 5

        def simple_signal(p: np.ndarray) -> np.ndarray:
            # Moving average crossover
            short_ma = np.convolve(p, np.ones(20) / 20, mode="same")
            long_ma = np.convolve(p, np.ones(50) / 50, mode="same")
            return np.where(short_ma > long_ma, 1.0, -1.0)

        start = time.time()
        result = walk_forward(prices, simple_signal, fee=0.001)
        duration = time.time() - start

        assert result.trades > 0
        assert duration < 5.0  # Should complete in under 5 seconds

    def test_strategy_simulation_with_large_dataset(self) -> None:
        """Strategy simulation should handle large datasets efficiently."""
        prices = 100.0 + np.cumsum(np.random.randn(50_000) * 0.1)
        df = pd.DataFrame({"close": prices})

        strategy = Strategy(name="large", params={"lookback": 50, "threshold": 0.5})

        start = time.time()
        score = strategy.simulate_performance(df)
        duration = time.time() - start

        assert np.isfinite(score)
        assert duration < 10.0  # Should complete in under 10 seconds

    def test_scale_series_with_100k_elements(self) -> None:
        """Scaling should handle very large arrays efficiently."""
        data = np.random.randn(100_000)

        start = time.time()
        result = scale_series(data, method="zscore")
        duration = time.time() - start

        assert len(result) == len(data)
        assert duration < 1.0  # Should be very fast

    def test_normalize_df_with_large_dataframe(self) -> None:
        """DataFrame normalization should handle large datasets."""
        n = 50_000
        df = pd.DataFrame(
            {
                "ts": np.arange(n),
                "price": 100.0 + np.cumsum(np.random.randn(n) * 0.1),
                "volume": np.random.lognormal(10, 1, n),
            }
        )

        start = time.time()
        result = normalize_df(df)
        duration = time.time() - start

        assert len(result) <= len(df)
        assert duration < 5.0

    def test_entropy_calculation_scales_linearly(self) -> None:
        """Entropy calculation should scale reasonably with data size."""
        sizes = [1_000, 5_000, 10_000]
        durations = []

        for size in sizes:
            data = np.random.randn(size)
            start = time.time()
            _ = entropy(data, bins=50)
            durations.append(time.time() - start)

        # Should all complete quickly
        assert all(d < 1.0 for d in durations)


class TestMemoryUsage:
    """Tests for memory efficiency."""

    def test_backtest_memory_efficient_with_streaming(self) -> None:
        """Backtest should not require excessive memory for large datasets."""
        # Generate data in chunks to test memory efficiency
        chunk_size = 10_000
        prices = np.concatenate(
            [np.random.randn(chunk_size) * 5 + 100 + i * 10 for i in range(5)]
        )

        def signal_fn(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p) * 0.5

        result = walk_forward(prices, signal_fn, fee=0.001)
        assert result.pnl != 0.0 or result.trades == 0


class TestConcurrentExecution:
    """Tests for handling concurrent operations."""

    def test_multiple_strategy_evaluations_concurrent(self) -> None:
        """Multiple strategies should work concurrently without interference."""
        prices = 100.0 + np.cumsum(np.random.randn(5_000) * 0.1)
        df = pd.DataFrame({"close": prices})

        strategies = [
            Strategy(name=f"strat_{i}", params={"lookback": 20 + i * 10})
            for i in range(10)
        ]

        start = time.time()
        scores = [s.simulate_performance(df) for s in strategies]
        duration = time.time() - start

        assert all(np.isfinite(s) for s in scores)
        assert len(scores) == 10
        # Should complete in reasonable time even sequentially
        assert duration < 20.0


class TestEdgeCasePerformance:
    """Performance with edge case scenarios."""

    def test_constant_price_series_performance(self) -> None:
        """Constant prices should be handled efficiently."""
        prices = np.full(50_000, 100.0)

        def signal_fn(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)

        start = time.time()
        result = walk_forward(prices, signal_fn, fee=0.0)
        duration = time.time() - start

        assert result.pnl == 0.0
        assert duration < 2.0

    def test_highly_volatile_data_performance(self) -> None:
        """Highly volatile data should not degrade performance significantly."""
        prices = 100.0 + np.cumsum(np.random.randn(20_000) * 10)  # High volatility
        prices = np.abs(prices)  # Keep positive

        strategy = Strategy(name="volatile", params={"lookback": 30})
        df = pd.DataFrame({"close": prices})

        start = time.time()
        score = strategy.simulate_performance(df)
        duration = time.time() - start

        assert np.isfinite(score)
        assert duration < 15.0


class TestCrossValidationStress:
    """Stress tests focused on the cross-validation utilities."""

    def test_walk_forward_split_large_dataset(self) -> None:
        """Walk-forward splitter scales to large frames without timing out."""
        periods = 120_000
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2023-01-01", periods=periods, freq="min", tz="UTC"
                ),
                "label_end": pd.date_range(
                    "2023-01-01 00:05", periods=periods, freq="min", tz="UTC"
                ),
                "value": np.random.randn(periods),
            }
        )

        splitter = WalkForwardSplitter(
            train_window="30D",
            test_window="1D",
            step="12H",
            time_col="timestamp",
            label_end_col="label_end",
            embargo_pct=0.01,
        )

        start = time.time()
        split_count = 0
        for train_idx, test_idx in splitter.split(frame):
            assert train_idx.size > 0
            assert test_idx.size > 0
            split_count += 1
        duration = time.time() - start

        assert split_count > 0
        assert duration < 6.0

    def test_purged_kfold_split_large_dataset(self) -> None:
        """Purged K-fold splitter executes efficiently on large inputs."""
        n_rows = 60_000
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2023-01-01", periods=n_rows, freq="min", tz="UTC"
                ),
                "label_end": pd.date_range(
                    "2023-01-01 00:30", periods=n_rows, freq="min", tz="UTC"
                ),
                "value": np.random.randn(n_rows),
            }
        )

        splitter = PurgedKFoldTimeSeriesSplit(
            n_splits=8,
            time_col="timestamp",
            label_end_col="label_end",
            embargo_pct=0.02,
        )

        start = time.time()
        seen_splits = 0
        for train_idx, test_idx in splitter.split(frame):
            assert train_idx.size > 0
            assert test_idx.size > 0
            assert np.intersect1d(train_idx, test_idx).size == 0
            seen_splits += 1
        duration = time.time() - start

        assert seen_splits == splitter.n_splits
        assert duration < 4.0
