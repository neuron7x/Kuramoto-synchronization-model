# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pytest

from core.neuro.advanced.integrated import (
    CandidateGenerator,
    MultiscaleFractalAnalyzer,
    NeuroAdvancedConfig,
    NeuroRiskManager,
)


@pytest.mark.asyncio
async def test_analyzer_returns_multiscale_dynamics() -> None:
    analyzer = MultiscaleFractalAnalyzer()
    rng = np.random.default_rng(123)
    prices = np.maximum(1.0, 100.0 + np.cumsum(rng.normal(0.0, 0.25, size=160)))

    features = await analyzer.analyze(prices)
    dynamics = features["dynamics"]

    assert len(dynamics["scales"]) == len(dynamics["volatility_by_scale"])
    assert len(dynamics["scales"]) >= 2
    assert 0.0 <= dynamics["stability"] <= 1.0
    assert -0.2 <= dynamics["scaling_exponent"] <= 1.2


@pytest.mark.asyncio
async def test_scaling_exponent_detects_persistence() -> None:
    analyzer = MultiscaleFractalAnalyzer()
    rng = np.random.default_rng(321)

    persistent_prices = np.maximum(1.0, 50.0 + np.cumsum(0.3 + rng.normal(0.0, 0.05, size=256)))
    noise_prices = np.maximum(1.0, 50.0 + np.cumsum(rng.normal(0.0, 0.3, size=256)))

    persistent_features = await analyzer.analyze(persistent_prices)
    noise_features = await analyzer.analyze(noise_prices)

    assert (
        persistent_features["dynamics"]["scaling_exponent"]
        > noise_features["dynamics"]["scaling_exponent"]
    )


@pytest.mark.asyncio
async def test_analyzer_aggregates_multiple_assets() -> None:
    analyzer = MultiscaleFractalAnalyzer()
    rng = np.random.default_rng(111)
    series = {
        "EURUSD": np.maximum(1.0, 100.0 + np.cumsum(rng.normal(0.02, 0.2, size=180))),
        "GBPUSD": np.maximum(1.0, 120.0 + np.cumsum(rng.normal(-0.01, 0.3, size=220))),
    }

    per_asset, aggregated = await analyzer.analyze_assets(series)

    assert aggregated["asset_count"] == len(series)
    assert set(per_asset.keys()) == set(series.keys())
    assert aggregated["regime"] in aggregated["regime_distribution"]
    assert aggregated["volatility"] >= min(f["volatility"] for f in per_asset.values())
    assert aggregated["volatility"] <= max(f["volatility"] for f in per_asset.values())
    assert 0.0 <= aggregated["persistence_index"] <= 1.0


def test_candidate_generator_uses_asset_features() -> None:
    generator = CandidateGenerator()
    aggregated = {
        "trend_strength": 0.2,
        "volatility": 0.015,
        "fractal_scaling": 0.6,
        "fractal_stability": 0.7,
        "regime": "normal",
    }
    asset_features = {
        "EURUSD": {
            "trend_strength": 0.9,
            "volatility": 0.01,
            "dynamics": {"scaling_exponent": 0.8, "stability": 0.9},
            "regime": "trending",
        },
        "GBPUSD": {
            "trend_strength": -0.5,
            "volatility": 0.025,
            "dynamics": {"scaling_exponent": 0.3, "stability": 0.4},
            "regime": "choppy",
        },
    }

    candidates = generator.generate(asset_features, aggregated)

    assert {c["asset"] for c in candidates} == set(asset_features.keys())
    eur_momentum = next(
        c for c in candidates if c["asset"] == "EURUSD" and c["strategy"] == "fractal_momentum"
    )
    gbp_mean_rev = next(
        c
        for c in candidates
        if c["asset"] == "GBPUSD" and c["strategy"] == "fractal_mean_reversion"
    )

    assert eur_momentum["expected_edge"] > gbp_mean_rev["expected_edge"]
    assert gbp_mean_rev["fractal_features"]["regime"] == "choppy"


@pytest.mark.asyncio
async def test_fractal_dynamics_adjust_risk_scaling() -> None:
    manager = NeuroRiskManager(NeuroAdvancedConfig())
    decision = {"position_size": 1.0, "risk_level": 0.6, "asset": "EURUSD"}
    neuro_context = {"overall_confidence": 0.8}
    base_market_context = {
        "volatility": 0.02,
        "fractal_scaling": 0.5,
        "fractal_stability": 0.8,
        "fractal_dim": 1.5,
        "asset_contexts": {
            "EURUSD": {
                "fractal_scaling": 0.5,
                "fractal_stability": 0.8,
                "fractal_dim": 1.5,
            }
        },
    }

    base_adjusted = await manager.apply(decision, neuro_context, base_market_context)

    persistent_market_context = {
        **base_market_context,
        "asset_contexts": {
            "EURUSD": {
                "fractal_scaling": 0.9,
                "fractal_stability": 0.95,
                "fractal_dim": 1.35,
            }
        },
    }
    persistent_adjusted = await manager.apply(decision, neuro_context, persistent_market_context)

    antipersistent_market_context = {
        **base_market_context,
        "asset_contexts": {
            "EURUSD": {
                "fractal_scaling": 0.2,
                "fractal_stability": 0.4,
                "fractal_dim": 1.8,
            }
        },
    }
    antipersistent_adjusted = await manager.apply(
        decision, neuro_context, antipersistent_market_context
    )

    assert persistent_adjusted["position_size"] > base_adjusted["position_size"]
    assert antipersistent_adjusted["position_size"] < base_adjusted["position_size"]
    assert persistent_adjusted["risk_params"]["sl_dist"] == pytest.approx(
        base_adjusted["risk_params"]["sl_dist"]
    )
    assert persistent_adjusted["risk_params"]["tp_dist"] == pytest.approx(
        base_adjusted["risk_params"]["tp_dist"]
    )
