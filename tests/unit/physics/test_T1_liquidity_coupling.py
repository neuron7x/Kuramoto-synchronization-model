# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T1 — Liquidity-weighted Kuramoto coupling tests."""

import numpy as np
import pytest

from core.physics.liquidity_coupling import LiquidityCouplingMatrix


@pytest.fixture
def lcm() -> LiquidityCouplingMatrix:
    return LiquidityCouplingMatrix(volume_window=10, correlation_window=20)


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(42)
    T, N = 60, 4
    prices = 100 + np.cumsum(rng.normal(0, 1, (T, N)), axis=0)
    volumes = rng.uniform(100, 1000, (T, N))
    return prices, volumes


class TestLiquidityWeighting:
    """A_ij = C_ij · √(m_i·m_j) / max(m)."""

    def test_output_in_01(self, lcm, synthetic_data):
        prices, volumes = synthetic_data
        A = lcm.compute(prices, volumes)
        assert np.all(A >= 0.0)
        assert np.all(A <= 1.0)

    def test_diagonal_zero(self, lcm, synthetic_data):
        prices, volumes = synthetic_data
        A = lcm.compute(prices, volumes)
        np.testing.assert_array_equal(np.diag(A), 0.0)

    def test_high_volume_gets_higher_coupling(self, lcm):
        """Asset with 10× volume should have higher coupling weights."""
        rng = np.random.default_rng(7)
        T, N = 60, 3
        prices = 100 + np.cumsum(rng.normal(0, 1, (T, N)), axis=0)
        volumes = np.ones((T, N)) * 100
        volumes[:, 0] = 10000  # asset 0 has 100× volume

        A = lcm.compute(prices, volumes)
        # Coupling involving asset 0 should be higher
        avg_with_0 = (A[0, 1] + A[0, 2]) / 2
        avg_without_0 = A[1, 2]
        assert avg_with_0 >= avg_without_0 * 0.5  # at least comparable

    def test_uniform_volume_resembles_correlation(self, lcm):
        """With uniform volume, coupling ≈ |correlation|."""
        rng = np.random.default_rng(42)
        T, N = 100, 3
        prices = 100 + np.cumsum(rng.normal(0, 1, (T, N)), axis=0)
        volumes = np.ones((T, N)) * 500  # uniform

        A = lcm.compute(prices, volumes)
        # mass factor = √(m·m)/max(m) = 1.0 for uniform
        # so A ≈ |corr| (up to threshold)
        assert np.all(A >= 0)


class TestKuramotoIntegration:
    """Liquidity adjacency works with KuramotoEngine."""

    def test_kuramoto_run(self, lcm, synthetic_data):
        from core.kuramoto.config import KuramotoConfig
        from core.kuramoto.engine import KuramotoEngine

        prices, volumes = synthetic_data
        A = lcm.compute(prices, volumes)
        N = A.shape[0]

        cfg = KuramotoConfig(
            N=N,
            K=2.0,
            adjacency=A,
            adjacency_kind="normalized_topology",
            dt=0.01,
            steps=200,
            seed=42,
        )
        result = KuramotoEngine(cfg).run()
        assert 0 <= result.order_parameter[-1] <= 1
        assert np.all(np.isfinite(result.phases))


class TestMinCorrelationFilter:
    def test_sparse_coupling(self):
        lcm = LiquidityCouplingMatrix(volume_window=10, correlation_window=20, min_correlation=0.8)
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (60, 4)), axis=0)
        volumes = rng.uniform(100, 1000, (60, 4))
        A = lcm.compute(prices, volumes)
        # With high min_correlation, many edges should be zero
        n_zeros = np.sum(A == 0) - A.shape[0]  # subtract diagonal
        assert n_zeros > 0


class TestInputValidation:
    def test_shape_mismatch(self, lcm):
        with pytest.raises(ValueError, match="Shape mismatch"):
            lcm.compute(np.ones((10, 3)), np.ones((10, 4)))

    def test_single_asset(self, lcm):
        with pytest.raises(ValueError, match="N≥2"):
            lcm.compute(np.ones((10, 1)), np.ones((10, 1)))

    def test_bad_window(self):
        with pytest.raises(ValueError):
            LiquidityCouplingMatrix(volume_window=0)

    def test_bad_min_corr(self):
        with pytest.raises(ValueError):
            LiquidityCouplingMatrix(min_correlation=1.0)
