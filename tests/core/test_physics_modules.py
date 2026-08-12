# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.physics modules."""

from __future__ import annotations

import numpy as np
import pytest

try:
    from core.physics.engine import GeoSyncPhysicsEngine, PhysicsEngineResult
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

try:
    from core.physics.diffusion_predictor import (
        DiffusionVolatilityPredictor,
        VolatilityFrontPrediction,
    )
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

pytestmark = pytest.mark.skipif(
    GeoSyncPhysicsEngine is None and DiffusionVolatilityPredictor is None,
    reason="physics modules not importable",
)


def _prices(T=50, N=4, seed=7):
    rng = np.random.default_rng(seed)
    return 100 + np.cumsum(rng.normal(0, 0.5, (T, N)), axis=0)


def _volumes(T=50, N=4, seed=8):
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(1e6, 1e5, (T, N)))


class TestGeoSyncPhysicsEngine:
    pytestmark = pytest.mark.skipif(GeoSyncPhysicsEngine is None, reason="engine not importable")

    def test_default_init(self):
        e = GeoSyncPhysicsEngine()
        assert e.gravitational is not None

    def test_run_basic(self):
        e = GeoSyncPhysicsEngine()
        N = 4
        p = _prices(50, N)
        v = _volumes(50, N)
        pos = np.ones(N)
        er = np.array([0.01, -0.005, 0.02, 0.0])
        result = e.run(p, v, pos, er)
        assert isinstance(result, PhysicsEngineResult)
        assert result.adjacency.shape == (N, N)
        assert result.energy_conserved is True

    def test_run_with_ofi(self):
        e = GeoSyncPhysicsEngine()
        N = 3
        p = _prices(50, N)
        v = _volumes(50, N)
        ofi = np.random.default_rng(9).normal(0, 100, (50, N))
        result = e.run(p, v, np.ones(N), np.zeros(N), ofi=ofi)
        assert result.accelerations.shape == (N,)

    def test_run_risk_gate_bool(self):
        e = GeoSyncPhysicsEngine()
        N = 4
        result = e.run(_prices(50, N), _volumes(50, N), np.ones(N), np.zeros(N))
        assert isinstance(result.risk_gate_allowed, bool)

    def test_run_volatility_front_list(self):
        e = GeoSyncPhysicsEngine()
        N = 4
        result = e.run(_prices(50, N), _volumes(50, N), np.ones(N), np.zeros(N))
        assert isinstance(result.volatility_front, list)

    def test_run_landauer_positive(self):
        e = GeoSyncPhysicsEngine()
        N = 3
        result = e.run(_prices(50, N), _volumes(50, N), np.ones(N), np.zeros(N))
        assert result.landauer_efficiency >= 0

    def test_diffusion_density_sums_to_one(self):
        e = GeoSyncPhysicsEngine()
        N = 4
        result = e.run(_prices(50, N), _volumes(50, N), np.ones(N), np.zeros(N))
        assert abs(result.diffusion_density.sum() - 1.0) < 0.01

    def test_custom_params(self):
        e = GeoSyncPhysicsEngine(coupling_window=20, tsallis_q=1.3, T_base=0.5)
        N = 3
        result = e.run(_prices(50, N), _volumes(50, N), np.ones(N), np.zeros(N))
        assert result.adjacency.shape == (N, N)

    @pytest.mark.parametrize("n_assets", [2, 5, 8])
    def test_various_asset_counts(self, n_assets):
        e = GeoSyncPhysicsEngine()
        result = e.run(
            _prices(50, n_assets),
            _volumes(50, n_assets),
            np.ones(n_assets),
            np.zeros(n_assets),
        )
        assert result.adjacency.shape == (n_assets, n_assets)


class TestDiffusionVolatilityPredictor:
    pytestmark = pytest.mark.skipif(
        DiffusionVolatilityPredictor is None, reason="predictor not importable"
    )

    def test_default_init(self):
        p = DiffusionVolatilityPredictor()
        assert p._D_0 == 1.0

    def test_invalid_D0(self):
        with pytest.raises(ValueError):
            DiffusionVolatilityPredictor(D_0=-1)

    def test_invalid_quantile(self):
        with pytest.raises(ValueError):
            DiffusionVolatilityPredictor(threshold_quantile=1.5)

    def test_predict_basic(self):
        p = DiffusionVolatilityPredictor()
        N = 5
        vol = np.abs(np.random.default_rng(1).normal(0.02, 0.01, N))
        adj = np.abs(np.random.default_rng(2).normal(0, 1, (N, N)))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        result = p.predict(vol, adj)
        assert isinstance(result, VolatilityFrontPrediction)
        assert result.density_t1.shape == (N,)
        assert abs(result.density_t1.sum() - 1.0) < 0.01

    def test_predict_front_subset(self):
        p = DiffusionVolatilityPredictor()
        N = 10
        vol = np.abs(np.random.default_rng(3).normal(0.02, 0.01, N))
        adj = np.eye(N) * 0.0
        adj[0, 1] = adj[1, 0] = 1.0
        result = p.predict(vol, adj)
        assert len(result.predicted_front) <= N

    def test_predict_zero_vol(self):
        p = DiffusionVolatilityPredictor()
        N = 4
        vol = np.zeros(N)
        adj = np.ones((N, N)) * 0.5
        np.fill_diagonal(adj, 0)
        result = p.predict(vol, adj)
        assert abs(result.initial_density.sum() - 1.0) < 0.01
