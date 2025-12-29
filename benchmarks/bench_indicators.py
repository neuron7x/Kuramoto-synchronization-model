# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Performance benchmarks for core indicator computations.

This module provides benchmarks for key geometric market indicators to track
performance regressions and validate optimization improvements. Run with:
    pytest benchmarks/bench_indicators.py --benchmark-only
"""
from __future__ import annotations

import numpy as np
import pytest

from core.indicators.entropy import entropy
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci
from utils.seed import set_global_seed


class TestKuramotoBenchmarks:
    """Benchmarks for Kuramoto order parameter calculations."""

    @pytest.fixture
    def small_signal(self) -> np.ndarray:
        """100-point test signal."""
        return np.sin(np.linspace(0, 4 * np.pi, 100))

    @pytest.fixture
    def medium_signal(self) -> np.ndarray:
        """1000-point test signal."""
        return np.sin(np.linspace(0, 4 * np.pi, 1000))

    @pytest.fixture
    def large_signal(self) -> np.ndarray:
        """10000-point test signal."""
        return np.sin(np.linspace(0, 4 * np.pi, 10000))

    def test_compute_phase_small(self, benchmark, small_signal):
        """Benchmark phase computation on small signal."""
        result = benchmark(compute_phase, small_signal)
        assert result.shape == small_signal.shape

    def test_compute_phase_medium(self, benchmark, medium_signal):
        """Benchmark phase computation on medium signal."""
        result = benchmark(compute_phase, medium_signal)
        assert result.shape == medium_signal.shape

    def test_compute_phase_large(self, benchmark, large_signal):
        """Benchmark phase computation on large signal."""
        result = benchmark(compute_phase, large_signal)
        assert result.shape == large_signal.shape

    def test_compute_phase_float32(self, benchmark, large_signal):
        """Benchmark phase computation with float32 optimization."""
        result = benchmark(compute_phase, large_signal, use_float32=True)
        assert result.shape == large_signal.shape

    def test_kuramoto_order_1d(self, benchmark, medium_signal):
        """Benchmark Kuramoto order for 1D phase array."""
        phases = compute_phase(medium_signal)
        result = benchmark(kuramoto_order, phases)
        assert isinstance(result, (float, np.floating))

    def test_kuramoto_order_2d(self, benchmark):
        """Benchmark Kuramoto order for 2D phase matrix."""
        # 50 oscillators x 200 timesteps
        set_global_seed()  # Fixed seed for reproducible benchmarks
        phases = np.random.uniform(-np.pi, np.pi, (50, 200))
        result = benchmark(kuramoto_order, phases)
        assert isinstance(result, np.ndarray)
        assert result.shape == (200,)


class TestRicciBenchmarks:
    """Benchmarks for Ricci curvature calculations."""

    @pytest.fixture
    def trending_prices(self) -> np.ndarray:
        """Trending price series."""
        return 100 * np.exp(np.linspace(0, 0.1, 500))

    @pytest.fixture
    def volatile_prices(self) -> np.ndarray:
        """Volatile price series."""
        set_global_seed()  # Fixed seed for reproducible benchmarks
        trend = 100 * np.exp(np.linspace(0, 0.1, 500))
        noise = np.random.normal(0, 2, 500)
        return trend + noise

    def test_build_price_graph_trending(self, benchmark, trending_prices):
        """Benchmark graph construction for trending prices."""
        graph = benchmark(build_price_graph, trending_prices, delta=0.01)
        assert graph.number_of_nodes() > 0

    def test_build_price_graph_volatile(self, benchmark, volatile_prices):
        """Benchmark graph construction for volatile prices."""
        graph = benchmark(build_price_graph, volatile_prices, delta=0.01)
        assert graph.number_of_nodes() > 0

    def test_mean_ricci_small_graph(self, benchmark, trending_prices):
        """Benchmark mean Ricci curvature on small graph."""
        # Use larger delta for fewer nodes/edges
        prices = trending_prices[:100]
        graph = build_price_graph(prices, delta=0.02)
        result = benchmark(mean_ricci, graph)
        assert isinstance(result, (float, np.floating))

    def test_mean_ricci_with_float32(self, benchmark, trending_prices):
        """Benchmark mean Ricci with float32 optimization."""
        prices = trending_prices[:200]
        graph = build_price_graph(prices, delta=0.01)
        result = benchmark(mean_ricci, graph, use_float32=True)
        assert isinstance(result, (float, np.floating))


class TestEntropyBenchmarks:
    """Benchmarks for entropy calculations."""

    @pytest.fixture
    def random_returns(self) -> np.ndarray:
        """Random return series."""
        set_global_seed()  # Fixed seed for reproducible benchmarks
        return np.random.normal(0, 0.02, 1000)

    @pytest.fixture
    def structured_returns(self) -> np.ndarray:
        """Structured return series with autocorrelation."""
        set_global_seed()  # Fixed seed for reproducible benchmarks
        noise = np.random.normal(0, 0.01, 1000)
        # Add autocorrelation
        structured = np.zeros(1000)
        structured[0] = noise[0]
        for i in range(1, 1000):
            structured[i] = 0.3 * structured[i - 1] + noise[i]
        return structured

    def test_entropy_random(self, benchmark, random_returns):
        """Benchmark entropy on random data."""
        result = benchmark(entropy, random_returns, bins=30)
        assert isinstance(result, (float, np.floating))
        assert result >= 0

    def test_entropy_structured(self, benchmark, structured_returns):
        """Benchmark entropy on structured data."""
        result = benchmark(entropy, structured_returns, bins=30)
        assert isinstance(result, (float, np.floating))
        assert result >= 0

    def test_entropy_with_float32(self, benchmark, random_returns):
        """Benchmark entropy with float32 optimization."""
        result = benchmark(entropy, random_returns, bins=30, use_float32=True)
        assert isinstance(result, (float, np.floating))

    def test_entropy_chunked(self, benchmark):
        """Benchmark chunked entropy for large dataset."""
        seed_numpy()  # Fixed seed for reproducible benchmarks
        large_data = np.random.normal(0, 0.02, 100000)
        result = benchmark(entropy, large_data, bins=50, chunk_size=10000)
        assert isinstance(result, (float, np.floating))


class TestEndToEndBenchmarks:
    """End-to-end benchmarks for typical workflows."""

    def test_full_indicator_pipeline(self, benchmark):
        """Benchmark complete indicator computation pipeline."""

        def compute_indicators():
            # Simulate typical workflow
            set_global_seed()  # Fixed seed for reproducible benchmarks
            prices = 100 * np.exp(np.cumsum(np.random.normal(0.0001, 0.02, 500)))

            # Phase analysis
            phases = compute_phase(prices)
            sync = kuramoto_order(phases)

            # Curvature analysis
            graph = build_price_graph(prices, delta=0.01)
            curvature = mean_ricci(graph)

            # Entropy analysis
            returns = np.diff(np.log(prices))
            ent = entropy(returns, bins=30)

            return {"sync": sync, "curvature": curvature, "entropy": ent}

        result = benchmark(compute_indicators)
        assert "sync" in result
        assert "curvature" in result
        assert "entropy" in result


if __name__ == "__main__":
    # Allow running benchmarks standalone
    pytest.main([__file__, "--benchmark-only", "-v"])
