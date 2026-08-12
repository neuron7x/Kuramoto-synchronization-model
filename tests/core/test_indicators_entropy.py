# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.indicators.entropy module."""

from __future__ import annotations

import numpy as np
import pytest

from core.indicators.entropy import entropy


class TestEntropy:
    def test_constant_signal_zero_entropy(self):
        x = np.ones(100)
        h = entropy(x, bins=10)
        assert h == pytest.approx(0.0, abs=1e-10)

    def test_uniform_distribution_max_entropy(self):
        # Uniform data should give near-maximum entropy
        x = np.linspace(-1, 1, 10000)
        h = entropy(x, bins=30)
        max_h = np.log(30)
        assert h > 0.8 * max_h  # Should be close to max

    def test_empty_array(self):
        assert entropy(np.array([]), bins=10) == 0.0

    def test_single_element(self):
        h = entropy(np.array([42.0]), bins=10)
        assert h == pytest.approx(0.0, abs=1e-10)

    def test_nan_filtered(self):
        x = np.array([1.0, 2.0, np.nan, 3.0, np.nan, 4.0])
        h = entropy(x, bins=10)
        assert np.isfinite(h)

    def test_all_nan_returns_zero(self):
        x = np.array([np.nan, np.nan, np.nan])
        assert entropy(x, bins=10) == 0.0

    def test_inf_filtered(self):
        x = np.array([1.0, 2.0, np.inf, -np.inf, 3.0])
        h = entropy(x, bins=10)
        assert np.isfinite(h)

    def test_positive_entropy(self):
        rng = np.random.default_rng(42)
        x = rng.standard_normal(1000)
        h = entropy(x, bins=30)
        assert h > 0.0

    def test_float32(self):
        x = np.random.default_rng(42).standard_normal(500)
        h = entropy(x, bins=20, use_float32=True)
        assert np.isfinite(h)

    @pytest.mark.parametrize("bins", [5, 10, 20, 50, 100])
    def test_various_bins(self, bins):
        x = np.random.default_rng(42).standard_normal(1000)
        h = entropy(x, bins=bins)
        assert h >= 0.0
        assert np.isfinite(h)

    def test_chunked_processing(self):
        x = np.random.default_rng(42).standard_normal(5000)
        h_normal = entropy(x, bins=30)
        h_chunked = entropy(x, bins=30, chunk_size=500)
        # Should give similar results
        assert abs(h_normal - h_chunked) < 1.0  # Relaxed tolerance for chunked

    @pytest.mark.parametrize("n", [50, 100, 500, 1000, 5000])
    def test_various_sizes(self, n):
        x = np.random.default_rng(42).standard_normal(n)
        h = entropy(x, bins=30)
        assert 0.0 <= h <= np.log(30) + 0.1  # Bounded by max entropy

    def test_deterministic(self):
        x = np.random.default_rng(42).standard_normal(500)
        h1 = entropy(x, bins=20)
        h2 = entropy(x, bins=20)
        assert h1 == h2
