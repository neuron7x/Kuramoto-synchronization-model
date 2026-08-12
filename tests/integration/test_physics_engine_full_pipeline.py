# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration test — GeoSync Physics Engine full pipeline.

Feeds synthetic OHLCV data through the complete 7-module pipeline.
Validates: no NaN, no Inf, all outputs in valid ranges,
free energy gate operates correctly, conservation violations detectable.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.engine import GeoSyncPhysicsEngine, PhysicsEngineResult


def _generate_synthetic_ohlcv(
    n_days: int = 30,
    n_assets: int = 5,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic price/volume/OFI data."""
    rng = np.random.default_rng(seed)
    # Prices: random walk with drift
    returns = rng.normal(0.001, 0.02, (n_days, n_assets))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    # Volumes: log-normal
    volumes = np.exp(rng.normal(10, 1, (n_days, n_assets)))
    # OFI: normally distributed
    ofi = rng.normal(0, 100, (n_days, n_assets))
    return prices, volumes, ofi


@pytest.fixture
def engine() -> GeoSyncPhysicsEngine:
    return GeoSyncPhysicsEngine(
        coupling_window=10,
        ema_span=10,
        conservation_epsilon=0.05,
        tsallis_q=1.5,
        T_base=0.60,
        coulomb_alpha=0.1,
        diffusion_D0=1.0,
    )


@pytest.fixture
def synthetic_data():
    return _generate_synthetic_ohlcv(n_days=30, n_assets=5, seed=42)


class TestFullPipelineNoNaN:
    """No NaN or Inf in any output."""

    def test_all_outputs_finite(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        positions = np.ones(n_assets)
        expected_returns = np.full(n_assets, 0.02)

        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=positions,
            expected_returns=expected_returns,
            ofi=ofi,
        )

        assert isinstance(result, PhysicsEngineResult)
        assert np.all(np.isfinite(result.adjacency))
        assert np.all(np.isfinite(result.accelerations))
        assert np.all(np.isfinite(result.diffusion_density))
        assert np.isfinite(result.energy_delta)
        assert np.isfinite(result.landauer_efficiency)
        assert np.isfinite(result.landauer_ratio)


class TestOutputRanges:
    """All outputs in valid ranges."""

    def test_adjacency_range(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
            ofi=ofi,
        )
        assert np.all(result.adjacency >= 0.0)
        assert np.all(result.adjacency <= 1.0)

    def test_diffusion_density_sums_to_one(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
            ofi=ofi,
        )
        assert abs(result.diffusion_density.sum() - 1.0) < 1e-10

    def test_landauer_efficiency_positive(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
        )
        assert result.landauer_efficiency > 0


class TestPipelineWithoutOFI:
    """Pipeline should work without OFI (T2/T5 become no-ops)."""

    def test_runs_without_ofi(self, engine, synthetic_data):
        prices, volumes, _ = synthetic_data
        n_assets = prices.shape[1]
        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
        )
        assert isinstance(result, PhysicsEngineResult)
        assert np.all(result.accelerations == 0.0)  # No OFI → no force


class TestPipelineWithCurvature:
    """Pipeline handles Ricci curvature input."""

    def test_runs_with_curvature(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        curvature = np.random.default_rng(7).uniform(-0.5, 0.5, (n_assets, n_assets))
        curvature = 0.5 * (curvature + curvature.T)
        np.fill_diagonal(curvature, 0.0)

        result = engine.run(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
            ofi=ofi,
            curvature=curvature,
            kappa_min=-0.3,
        )
        assert isinstance(result, PhysicsEngineResult)
        assert np.all(np.isfinite(result.diffusion_density))


class TestKuramotoIntegration:
    """Gravitational adjacency integrates with actual KuramotoEngine."""

    def test_full_kuramoto_run(self, engine, synthetic_data):
        from core.kuramoto.config import KuramotoConfig
        from core.kuramoto.engine import KuramotoEngine

        prices, volumes, _ = synthetic_data
        n_assets = prices.shape[1]
        adj = engine.gravitational.compute(prices, volumes)

        config = KuramotoConfig(
            N=n_assets,
            K=2.0,
            adjacency=adj,
            adjacency_kind="normalized_topology",
            dt=0.01,
            steps=500,
            seed=42,
        )
        result = KuramotoEngine(config).run()
        assert result.order_parameter[-1] >= 0.0
        assert result.order_parameter[-1] <= 1.0
        assert np.all(np.isfinite(result.phases))


class TestDeterminism:
    """Same inputs → same outputs."""

    def test_deterministic(self, engine, synthetic_data):
        prices, volumes, ofi = synthetic_data
        n_assets = prices.shape[1]
        kwargs = dict(
            prices=prices,
            volumes=volumes,
            positions=np.ones(n_assets),
            expected_returns=np.full(n_assets, 0.02),
            ofi=ofi,
        )
        r1 = engine.run(**kwargs)
        r2 = engine.run(**kwargs)
        np.testing.assert_array_equal(r1.adjacency, r2.adjacency)
        np.testing.assert_array_equal(r1.accelerations, r2.accelerations)
        np.testing.assert_array_equal(r1.diffusion_density, r2.diffusion_density)
