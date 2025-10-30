# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for performance optimization features.

This module tests the optional performance optimization parameters (use_float32, chunk_size)
that have been added to various indicator features including:
- EntropyFeature: Shannon entropy calculation with optional float32 and chunking
- HurstFeature: Hurst exponent estimation with optional float32
- MeanRicciFeature: Ricci curvature with optional float32 and chunking
- KuramotoOrderFeature: Kuramoto order parameter with optional float32

The tests verify:
1. Float32 precision support reduces memory usage while preserving accuracy
2. Chunked processing handles large datasets efficiently
3. Feature classes correctly report optimization parameters in metadata
4. GPU acceleration (when available) produces equivalent results to CPU
5. Edge cases are handled properly (empty arrays, constant values, etc.)
6. Backward compatibility is maintained (original API still works)

Key testing principles:
- Optimization parameters should only appear in metadata when explicitly enabled
- Float32 results should be close to float64 (within reasonable tolerance)
- Chunked processing should produce results similar to non-chunked
- All optimizations should preserve the core algorithm behavior
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.data.preprocess import normalize_df, scale_series
from core.indicators.entropy import EntropyFeature, entropy
from core.indicators.hurst import HurstFeature, hurst_exponent
from core.indicators.kuramoto import (
    KuramotoOrderFeature,
    compute_phase,
    compute_phase_gpu,
)
from core.indicators.ricci import MeanRicciFeature, build_price_graph, mean_ricci


class TestFloat32Support:
    """Test float32 precision support for memory optimization."""

    def test_entropy_float32(self):
        """Test entropy with float32 precision."""
        data = np.random.randn(1000)

        # float64 (default)
        h64 = entropy(data, bins=30)

        # float32
        h32 = entropy(data, bins=30, use_float32=True)

        # Should be close but not identical
        assert isinstance(h64, float)
        assert isinstance(h32, float)
        assert abs(h64 - h32) < 0.1  # Small difference acceptable

    def test_hurst_float32(self):
        """Test Hurst exponent with float32 precision."""
        data = np.random.randn(1000)

        h64 = hurst_exponent(data)
        h32 = hurst_exponent(data, use_float32=True)

        assert isinstance(h64, float)
        assert isinstance(h32, float)
        # Hurst is more sensitive, allow larger tolerance
        assert abs(h64 - h32) < 0.2

    def test_compute_phase_float32(self):
        """Test phase computation with float32."""
        data = np.random.randn(100)

        phase64 = compute_phase(data)
        phase32 = compute_phase(data, use_float32=True)

        assert phase64.dtype in (np.float64, np.complex128)
        assert phase32.dtype in (np.float32, np.complex64, np.float64)
        assert phase64.shape == phase32.shape
        # Phase should be very similar
        assert np.allclose(phase64, phase32, atol=0.01)

    def test_scale_series_float32(self):
        """Test series scaling with float32."""
        data = np.random.randn(1000)

        scaled64 = scale_series(data, method="zscore")
        scaled32 = scale_series(data, method="zscore", use_float32=True)

        assert scaled64.dtype == np.float64
        assert scaled32.dtype == np.float32
        assert np.allclose(scaled64, scaled32, atol=1e-5)

    def test_normalize_df_float32(self):
        """Test DataFrame normalization with float32."""
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=100, freq="1h"),
                "price": np.random.randn(100) * 10 + 100,
                "volume": np.random.randint(100, 1000, 100),
            }
        )

        df64 = normalize_df(df)
        df32 = normalize_df(df, use_float32=True)

        assert df64["price"].dtype == np.float64
        assert df32["price"].dtype == np.float32
        assert np.allclose(df64["price"], df32["price"], atol=1e-5)

    def test_ricci_float32(self):
        """Test Ricci curvature with float32."""
        prices = np.random.randn(100) + 100
        G = build_price_graph(prices)

        r64 = mean_ricci(G)
        r32 = mean_ricci(G, use_float32=True)

        assert isinstance(r64, float)
        assert isinstance(r32, float)
        # Allow reasonable tolerance
        if G.number_of_edges() > 0:
            assert abs(r64 - r32) < 0.5


class TestChunkedProcessing:
    """Test chunked processing for large datasets."""

    def test_entropy_chunked(self):
        """Test entropy with chunked processing."""
        # Large dataset
        data = np.random.randn(10000)

        # Without chunking
        h_full = entropy(data, bins=30)

        # With chunking
        h_chunked = entropy(data, bins=30, chunk_size=1000)

        # Should be reasonably close
        assert isinstance(h_full, float)
        assert isinstance(h_chunked, float)
        # Chunked may differ slightly due to weighted averaging
        assert abs(h_full - h_chunked) < 1.0

    def test_entropy_chunked_small_data(self):
        """Test that chunking works with small data."""
        data = np.random.randn(100)

        # Chunk size larger than data
        h = entropy(data, bins=10, chunk_size=1000)

        assert isinstance(h, float)
        assert h >= 0

    def test_ricci_chunked(self):
        """Test Ricci curvature with chunked processing."""
        prices = np.random.randn(200) + 100
        G = build_price_graph(prices)

        if G.number_of_edges() == 0:
            pytest.skip("Graph has no edges")

        # Without chunking
        r_full = mean_ricci(G)

        # With chunking
        r_chunked = mean_ricci(G, chunk_size=10)

        # Should be identical (just different processing order)
        assert isinstance(r_full, float)
        assert isinstance(r_chunked, float)
        assert abs(r_full - r_chunked) < 0.01

    def test_entropy_combined_optimizations(self):
        """Test entropy with both float32 and chunking."""
        data = np.random.randn(5000)

        h = entropy(data, bins=50, use_float32=True, chunk_size=500)

        assert isinstance(h, float)
        assert h >= 0
        assert not np.isnan(h)


class TestFeatureClassOptimizations:
    """Test optimized feature classes with metrics."""

    def test_entropy_feature_float32(self):
        """Test EntropyFeature with float32."""
        data = np.random.randn(1000)

        feat = EntropyFeature(bins=30, use_float32=True)
        result = feat.transform(data)

        assert result.name == "entropy"
        assert isinstance(result.value, float)
        assert result.metadata["use_float32"] is True
        assert result.metadata["bins"] == 30

    def test_entropy_feature_chunked(self):
        """Test EntropyFeature with chunking."""
        data = np.random.randn(5000)

        feat = EntropyFeature(bins=30, chunk_size=1000, use_float32=True)
        result = feat.transform(data)

        assert isinstance(result.value, float)
        assert result.metadata["chunk_size"] == 1000
        assert result.metadata["use_float32"] is True

    def test_hurst_feature_float32(self):
        """Test HurstFeature with float32."""
        data = np.random.randn(1000)

        feat = HurstFeature(use_float32=True)
        result = feat.transform(data)

        assert result.name == "hurst_exponent"
        assert isinstance(result.value, float)
        assert result.metadata["use_float32"] is True

    def test_ricci_feature_optimizations(self):
        """Test MeanRicciFeature with optimizations."""
        data = np.random.randn(200) + 100

        feat = MeanRicciFeature(delta=0.005, chunk_size=10, use_float32=True)
        result = feat.transform(data)

        assert result.name == "mean_ricci"
        assert isinstance(result.value, float)
        assert result.metadata["chunk_size"] == 10
        assert result.metadata["use_float32"] is True
        assert "edges" in result.metadata

    def test_kuramoto_feature_float32(self):
        """Test KuramotoOrderFeature with float32."""
        phases = np.random.uniform(-np.pi, np.pi, 100)

        feat = KuramotoOrderFeature(use_float32=True)
        result = feat.transform(phases)

        assert isinstance(result.value, float)
        assert 0 <= result.value <= 1
        assert result.metadata["use_float32"] is True


class TestGPUAcceleration:
    """Test GPU acceleration features."""

    def test_compute_phase_gpu_fallback(self):
        """Test that GPU phase falls back to CPU gracefully."""
        data = np.random.randn(100)

        # Should work regardless of CuPy availability
        phases = compute_phase_gpu(data)

        assert isinstance(phases, np.ndarray)
        assert phases.shape == data.shape
        assert not np.any(np.isnan(phases))

    def test_compute_phase_gpu_equivalence(self):
        """Test that GPU and CPU give equivalent results."""
        data = np.random.randn(100)

        phases_cpu = compute_phase(data)
        phases_gpu = compute_phase_gpu(data)

        # Should be very close (may differ due to float32 on GPU)
        assert np.allclose(phases_cpu, phases_gpu, atol=0.1)


class TestEdgeCases:
    """Test edge cases for optimized functions."""

    def test_entropy_empty_array(self):
        """Test entropy with empty array."""
        data = np.array([])

        h = entropy(data, use_float32=True, chunk_size=10)
        assert h == 0.0

    def test_entropy_constant_values(self):
        """Test entropy with constant values."""
        data = np.ones(100)

        h = entropy(data, bins=10, use_float32=True)
        assert h == 0.0  # No entropy in constant data

    def test_hurst_insufficient_data(self):
        """Test Hurst with insufficient data."""
        data = np.random.randn(50)

        # Should return default value
        h = hurst_exponent(data, max_lag=100, use_float32=True)
        assert h == 0.5

    def test_scale_series_zero_std(self):
        """Test scaling with zero standard deviation."""
        data = np.ones(100)

        scaled = scale_series(data, method="zscore", use_float32=True)
        assert np.all(scaled == 0)

    def test_ricci_empty_graph(self):
        """Test Ricci with graph with no edges."""
        import networkx as nx

        G = nx.Graph()
        G.add_nodes_from([1, 2, 3])

        r = mean_ricci(G, chunk_size=10, use_float32=True)
        assert r == 0.0


class TestBackwardCompatibility:
    """Test that optimizations don't break existing API."""

    def test_entropy_without_params(self):
        """Test entropy works without new parameters."""
        data = np.random.randn(1000)
        h = entropy(data, bins=30)
        assert isinstance(h, float)

    def test_hurst_without_params(self):
        """Test Hurst works without new parameters."""
        data = np.random.randn(1000)
        h = hurst_exponent(data, min_lag=2, max_lag=50)
        assert isinstance(h, float)

    def test_scale_series_without_params(self):
        """Test scale_series works without new parameters."""
        data = np.random.randn(100)
        scaled = scale_series(data, method="zscore")
        assert isinstance(scaled, np.ndarray)

    def test_normalize_df_without_params(self):
        """Test normalize_df works without new parameters."""
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=100),
                "price": np.random.randn(100) * 10 + 100,
            }
        )
        normalized = normalize_df(df)
        assert isinstance(normalized, pd.DataFrame)

    def test_feature_classes_without_params(self):
        """Test feature classes work without new parameters."""
        data = np.random.randn(1000)

        # Should work with original API
        entropy_feat = EntropyFeature(bins=30)
        result = entropy_feat.transform(data)
        assert isinstance(result.value, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
