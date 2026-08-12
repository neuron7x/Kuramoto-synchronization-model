# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.neuro.advanced.integrated module."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import numpy as np
import pytest

try:
    from core.neuro.advanced.integrated import (
        CandidateGenerator,
        MultiscaleFractalAnalyzer,
        NeuroDecisionIntegrator,
        NeuroRiskManager,
    )
except ImportError:
    pytest.skip("core.neuro.advanced.integrated not importable", allow_module_level=True)


def _random_prices(n: int = 100, base: float = 100.0, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return base + np.cumsum(rng.normal(0, 0.5, n))


def _make_features(regime: str = "normal") -> Dict[str, Any]:
    return {
        "volatility": 0.015,
        "trend_strength": 0.2,
        "hurst": 0.55,
        "fractal_dim": 1.45,
        "regime": regime,
        "n": 100,
        "dynamics": {
            "scaling_exponent": 0.52,
            "stability": 0.7,
            "scales": [1.0, 2.0],
            "volatility_by_scale": [0.01, 0.02],
        },
        "persistence_index": 0.55,
    }


class TestMultiscaleFractalAnalyzer:
    def setup_method(self):
        self.analyzer = MultiscaleFractalAnalyzer()

    @pytest.mark.asyncio
    async def test_analyze_returns_expected_keys(self):
        prices = _random_prices(100)
        result = await self.analyzer.analyze(prices)
        for key in (
            "volatility",
            "trend_strength",
            "hurst",
            "fractal_dim",
            "regime",
            "n",
            "dynamics",
            "persistence_index",
        ):
            assert key in result

    @pytest.mark.asyncio
    async def test_analyze_short_array_raises(self):
        with pytest.raises(ValueError, match="at least 20"):
            await self.analyzer.analyze(np.arange(1, 10, dtype=float))

    @pytest.mark.asyncio
    async def test_analyze_negative_prices_raises(self):
        prices = np.linspace(-5, 5, 50)
        with pytest.raises(ValueError, match="strictly positive"):
            await self.analyzer.analyze(prices)

    @pytest.mark.asyncio
    async def test_analyze_2d_raises(self):
        with pytest.raises(ValueError, match="1D"):
            await self.analyzer.analyze(np.ones((20, 2)))

    @pytest.mark.asyncio
    async def test_hurst_bounded(self):
        prices = _random_prices(200)
        result = await self.analyzer.analyze(prices)
        assert 0.0 <= result["hurst"] <= 1.0

    @pytest.mark.asyncio
    async def test_fractal_dim_bounded(self):
        prices = _random_prices(200)
        result = await self.analyzer.analyze(prices)
        assert 1.0 <= result["fractal_dim"] <= 2.0

    @pytest.mark.asyncio
    async def test_persistence_index_bounded(self):
        prices = _random_prices(200)
        result = await self.analyzer.analyze(prices)
        assert 0.0 <= result["persistence_index"] <= 1.0

    @pytest.mark.asyncio
    async def test_regime_values(self):
        prices = _random_prices(200)
        result = await self.analyzer.analyze(prices)
        assert result["regime"] in {"trending", "choppy", "normal"}

    @pytest.mark.asyncio
    async def test_analyze_assets(self):
        series = {"A": _random_prices(100), "B": _random_prices(100, base=50)}
        per_asset, aggregated = await self.analyzer.analyze_assets(series)
        assert "A" in per_asset and "B" in per_asset
        assert aggregated["asset_count"] == 2

    @pytest.mark.asyncio
    async def test_analyze_assets_empty_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            await self.analyzer.analyze_assets({})

    def test_classify_regime_trending(self):
        assert self.analyzer._classify_regime(0.6, 0.5, 0.01) == "trending"

    def test_classify_regime_choppy(self):
        assert self.analyzer._classify_regime(0.4, 0.1, 0.02) == "choppy"

    def test_classify_regime_normal(self):
        assert self.analyzer._classify_regime(0.5, 0.1, 0.005) == "normal"

    def test_approx_hurst_short_returns(self):
        assert self.analyzer._approx_hurst_rs(np.array([0.01, 0.02])) == 0.5

    @pytest.mark.asyncio
    async def test_dynamics_has_scaling_exponent(self):
        result = await self.analyzer.analyze(_random_prices(200))
        assert "scaling_exponent" in result["dynamics"]

    def test_aggregate_features(self):
        features = {"A": _make_features(), "B": _make_features("trending")}
        agg = self.analyzer._aggregate_features(features)
        assert "regime_distribution" in agg
        assert "volatility_dispersion" in agg


class TestCandidateGenerator:
    def setup_method(self):
        self.gen = CandidateGenerator()

    def test_generate_default_strategies(self):
        agg = _make_features()
        agg["fractal_scaling"] = 0.52
        agg["fractal_stability"] = 0.7
        candidates = self.gen.generate({"AAPL": _make_features()}, agg)
        assert len(candidates) == 2
        assert {c["strategy"] for c in candidates} == {
            "fractal_momentum",
            "fractal_mean_reversion",
        }

    def test_generate_single_strategy(self):
        agg = _make_features()
        agg["fractal_scaling"] = 0.5
        agg["fractal_stability"] = 0.5
        cands = self.gen.generate(
            {"BTC": _make_features()}, agg, base_strategies=["fractal_momentum"]
        )
        assert len(cands) == 1

    def test_positive_trend_long(self):
        feat = _make_features()
        feat["trend_strength"] = 0.5
        cands = self.gen.generate({"X": feat}, _make_features())
        mom = [c for c in cands if c["strategy"] == "fractal_momentum"][0]
        assert mom["side"] == "long"

    def test_negative_trend_short(self):
        feat = _make_features()
        feat["trend_strength"] = -0.5
        cands = self.gen.generate({"X": feat}, _make_features())
        mom = [c for c in cands if c["strategy"] == "fractal_momentum"][0]
        assert mom["side"] == "short"

    def test_choppy_position_size(self):
        feat = _make_features("choppy")
        agg = _make_features("choppy")
        agg["fractal_scaling"] = 0.5
        agg["fractal_stability"] = 0.5
        cands = self.gen.generate({"Y": feat}, agg)
        mr = [c for c in cands if c["strategy"] == "fractal_mean_reversion"][0]
        assert mr["position_size"] == 0.9


class TestNeuroRiskManager:
    @pytest.fixture
    def mock_config(self):
        cfg = MagicMock()
        cfg.slo_gate_confidence_min = 0.5
        cfg.slo_gate_max_volatility = 0.03
        cfg.slo_emergency_downscale = 0.3
        bounds = MagicMock()
        bounds.min_position = 0.01
        bounds.max_position = 5.0
        bounds.min_risk = 0.1
        bounds.max_risk = 3.0
        cfg.policy_bounds = bounds
        return cfg

    @pytest.mark.asyncio
    async def test_apply_reduces_position(self, mock_config):
        mgr = NeuroRiskManager(mock_config)
        result = await mgr.apply(
            {"position_size": 2.0, "risk_level": 1.0, "asset": "AAPL"},
            {"overall_confidence": 0.8},
            {"volatility": 0.02},
        )
        assert result["position_size"] <= 2.0

    @pytest.mark.asyncio
    async def test_apply_sets_sl_tp(self, mock_config):
        mgr = NeuroRiskManager(mock_config)
        result = await mgr.apply(
            {"position_size": 1.0, "risk_level": 1.0},
            {"overall_confidence": 0.7},
            {"volatility": 0.01},
        )
        assert "sl_dist" in result["risk_params"]
        assert "tp_dist" in result["risk_params"]

    @pytest.mark.asyncio
    async def test_apply_emergency_downscale(self, mock_config):
        mgr = NeuroRiskManager(mock_config)
        result = await mgr.apply(
            {"position_size": 2.0, "risk_level": 1.0},
            {"overall_confidence": 0.3},
            {"volatility": 0.05},
        )
        assert result["position_size"] < 1.0

    @pytest.mark.asyncio
    async def test_apply_clamps_risk(self, mock_config):
        mgr = NeuroRiskManager(mock_config)
        result = await mgr.apply(
            {"position_size": 1.0, "risk_level": 10.0},
            {"overall_confidence": 0.7},
            {"volatility": 0.01},
        )
        assert result["risk_level"] <= 3.0


class TestNeuroDecisionIntegrator:
    @pytest.fixture
    def integrator(self):
        cfg = MagicMock()
        w = MagicMock()
        w.edge = 1.0
        w.size = 0.5
        w.inverse_risk = 0.3
        w.confidence = 0.8
        w.context_preference = 0.2
        cfg.decision_weights = w
        nre = MagicMock()
        nre.context_preference.return_value = 0.5
        return NeuroDecisionIntegrator(cfg, nre)

    @pytest.mark.asyncio
    async def test_integrate_selects_best(self, integrator):
        decisions = [
            {
                "strategy": "a",
                "expected_edge": 0.01,
                "position_size": 1.0,
                "risk_level": 1.0,
                "confidence": 0.6,
            },
            {
                "strategy": "b",
                "expected_edge": 0.05,
                "position_size": 1.0,
                "risk_level": 1.0,
                "confidence": 0.9,
            },
        ]
        result = await integrator.integrate(decisions, {}, {})
        assert result["strategy"] == "b"
        assert "selection_score" in result

    @pytest.mark.asyncio
    async def test_integrate_empty_returns_empty(self, integrator):
        result = await integrator.integrate([], {}, {})
        assert result == {}
