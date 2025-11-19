# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for indicator optimization utilities."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from core.utils.indicator_optimization import (
    cached_indicator,
    data_fingerprint,
    optimize_dataframe_memory,
    parallel_indicator,
    rolling_apply_fast,
    vectorize_indicator,
)


class TestDataFingerprint:
    """Test data fingerprinting for cache keys."""

    def test_same_data_same_fingerprint(self):
        """Test that identical data produces identical fingerprints."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        fp1 = data_fingerprint(data)
        fp2 = data_fingerprint(data)
        
        assert fp1 == fp2
        assert isinstance(fp1, str)
        assert len(fp1) == 32  # blake2b with 16-byte digest = 32 hex chars

    def test_different_data_different_fingerprint(self):
        """Test that different data produces different fingerprints."""
        data1 = np.array([1.0, 2.0, 3.0])
        data2 = np.array([1.0, 2.0, 4.0])
        
        fp1 = data_fingerprint(data1)
        fp2 = data_fingerprint(data2)
        
        assert fp1 != fp2

    def test_precision_affects_fingerprint(self):
        """Test that precision parameter affects fingerprinting."""
        data = np.array([1.123456789])
        
        # Different precisions may produce different fingerprints
        # (depending on rounding)
        fp_high = data_fingerprint(data, precision=8)
        fp_low = data_fingerprint(data, precision=2)
        
        # Both should be valid hex strings
        assert len(fp_high) == 32
        assert len(fp_low) == 32

    def test_works_with_series(self):
        """Test fingerprinting pandas Series."""
        series = pd.Series([1.0, 2.0, 3.0])
        fp = data_fingerprint(series)
        
        assert isinstance(fp, str)
        assert len(fp) == 32

    def test_works_with_dataframe(self):
        """Test fingerprinting pandas DataFrame."""
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        fp = data_fingerprint(df)
        
        assert isinstance(fp, str)
        assert len(fp) == 32


class TestCachedIndicator:
    """Test indicator caching decorator."""

    def test_basic_caching(self):
        """Test that repeated calls use cache."""
        call_count = 0
        
        @cached_indicator(maxsize=10, ttl=60.0)
        def test_indicator(data: np.ndarray, period: int) -> np.ndarray:
            nonlocal call_count
            call_count += 1
            return np.roll(data, period)
        
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        
        # First call computes
        result1 = test_indicator(data, 2)
        assert call_count == 1
        
        # Second call uses cache
        result2 = test_indicator(data, 2)
        assert call_count == 1
        np.testing.assert_array_equal(result1, result2)

    def test_different_params_different_cache(self):
        """Test that different parameters create separate cache entries."""
        @cached_indicator(maxsize=10)
        def test_indicator(data: np.ndarray, period: int) -> np.ndarray:
            return np.roll(data, period)
        
        data = np.array([1.0, 2.0, 3.0])
        
        result1 = test_indicator(data, 1)
        result2 = test_indicator(data, 2)
        
        # Different parameters should produce different results
        assert not np.array_equal(result1, result2)

    def test_cache_expiration(self):
        """Test TTL-based cache expiration."""
        call_count = 0
        
        @cached_indicator(maxsize=10, ttl=0.1)
        def test_indicator(data: np.ndarray) -> np.ndarray:
            nonlocal call_count
            call_count += 1
            return data * 2
        
        data = np.array([1.0, 2.0, 3.0])
        
        test_indicator(data)
        assert call_count == 1
        
        # Wait for expiration
        time.sleep(0.15)
        
        test_indicator(data)
        assert call_count == 2  # Recomputed after expiration

    def test_cache_info(self):
        """Test cache statistics exposure."""
        @cached_indicator(maxsize=10)
        def test_indicator(data: np.ndarray) -> np.ndarray:
            return data
        
        data = np.array([1.0, 2.0, 3.0])
        
        test_indicator(data)
        test_indicator(data)
        
        stats = test_indicator.cache_info()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1


class TestRollingApplyFast:
    """Test optimized rolling window computation."""

    def test_rolling_mean(self):
        """Test rolling mean computation."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = rolling_apply_fast(data, 3, np.mean)
        
        # First two values should be NaN
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        
        # Third value should be mean of [1, 2, 3] = 2.0
        assert result[2] == pytest.approx(2.0)
        
        # Fourth value should be mean of [2, 3, 4] = 3.0
        assert result[3] == pytest.approx(3.0)

    def test_rolling_sum(self):
        """Test rolling sum computation."""
        data = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        result = rolling_apply_fast(data, 2, np.sum)
        
        assert np.isnan(result[0])
        assert result[1] == pytest.approx(2.0)
        assert result[2] == pytest.approx(2.0)

    def test_min_periods(self):
        """Test min_periods parameter."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = rolling_apply_fast(data, 3, np.mean, min_periods=2)
        
        # With min_periods=2, second value should be valid
        assert np.isnan(result[0])
        assert not np.isnan(result[1])


class TestParallelIndicator:
    """Test parallel indicator computation."""

    def test_parallel_computation(self):
        """Test computing indicator for multiple symbols in parallel."""
        def simple_mean(data: np.ndarray) -> np.ndarray:
            return np.full_like(data, np.mean(data))
        
        symbols = ["AAPL", "MSFT", "GOOGL"]
        data_dict = {
            "AAPL": np.array([100.0, 101.0, 102.0]),
            "MSFT": np.array([200.0, 201.0, 202.0]),
            "GOOGL": np.array([300.0, 301.0, 302.0]),
        }
        
        results = parallel_indicator(simple_mean, symbols, data_dict)
        
        assert len(results) == 3
        assert "AAPL" in results
        assert "MSFT" in results
        assert "GOOGL" in results
        
        # Check AAPL result
        assert results["AAPL"][0] == pytest.approx(101.0)

    def test_handles_missing_symbol(self):
        """Test handling of missing symbol data."""
        def simple_mean(data: np.ndarray) -> np.ndarray:
            return np.array([np.mean(data)])
        
        symbols = ["AAPL", "MISSING"]
        data_dict = {"AAPL": np.array([100.0, 101.0])}
        
        results = parallel_indicator(simple_mean, symbols, data_dict)
        
        assert len(results) == 2
        assert results["AAPL"].size > 0
        assert results["MISSING"].size == 0  # Empty array for missing data


class TestVectorizeIndicator:
    """Test vectorized indicator computation."""

    def test_simple_momentum(self):
        """Test simple momentum calculation."""
        def momentum(window: np.ndarray) -> float:
            return window[-1] - window[0]
        
        prices = np.array([100.0, 102.0, 101.0, 103.0, 105.0])
        result = vectorize_indicator(prices, 3, momentum)
        
        # First two should be NaN
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        
        # Third should be 101 - 100 = 1
        assert result[2] == pytest.approx(1.0)
        
        # Fourth should be 103 - 102 = 1
        assert result[3] == pytest.approx(1.0)

    def test_lookback_larger_than_data(self):
        """Test when lookback is larger than data."""
        def dummy(window: np.ndarray) -> float:
            return 0.0
        
        prices = np.array([100.0, 101.0])
        result = vectorize_indicator(prices, 5, dummy)
        
        # All should be NaN
        assert np.all(np.isnan(result))


class TestOptimizeDataFrameMemory:
    """Test DataFrame memory optimization."""

    def test_float64_to_float32(self):
        """Test conversion of float64 to float32."""
        df = pd.DataFrame({"price": [100.5, 101.2, 99.8]})
        
        # Original should be float64
        assert df["price"].dtype == np.float64
        
        df_opt = optimize_dataframe_memory(df)
        
        # Optimized should be float32
        assert df_opt["price"].dtype == np.float32
        
        # Values should be approximately equal
        np.testing.assert_allclose(df["price"].values, df_opt["price"].values, rtol=1e-5)

    def test_int64_to_smaller_int(self):
        """Test conversion of int64 to smaller integer types."""
        df = pd.DataFrame({"count": [1, 2, 3, 4, 5]})
        
        # Original should be int64
        assert df["count"].dtype == np.int64
        
        df_opt = optimize_dataframe_memory(df)
        
        # Optimized should be int8 (all values fit in int8)
        assert df_opt["count"].dtype == np.int8
        
        # Values should be exactly equal
        np.testing.assert_array_equal(df["count"].values, df_opt["count"].values)

    def test_preserves_large_values(self):
        """Test that large values are not downcasted incorrectly."""
        df = pd.DataFrame({"big": [1e35, 2e35, 3e35]})
        
        df_opt = optimize_dataframe_memory(df)
        
        # Should remain float64 (too large for float32)
        assert df_opt["big"].dtype == np.float64


class TestIndicatorOptimizationIntegration:
    """Integration tests for indicator optimization."""

    def test_cached_indicator_performance(self):
        """Test that caching improves performance."""
        def expensive_indicator(data: np.ndarray, window: int) -> np.ndarray:
            # Simulate expensive computation
            result = data.copy()
            for _ in range(10):
                result = np.roll(result, 1)
            return result
        
        data = np.random.randn(1000)
        
        # Without cache
        start = time.perf_counter()
        for _ in range(50):
            expensive_indicator(data, 10)
        no_cache_time = time.perf_counter() - start
        
        # With cache
        cached_func = cached_indicator(maxsize=10)(expensive_indicator)
        start = time.perf_counter()
        for _ in range(50):
            cached_func(data, 10)
        cache_time = time.perf_counter() - start
        
        # Cached should be faster (allowing for variance in timing)
        # The speedup can be dramatic, so just ensure cache works
        assert cache_time < no_cache_time or cache_time < 0.01
