from __future__ import annotations

import numpy as np
import pytest

from core.neuro.advanced.integrated import MultiscaleFractalAnalyzer, NeuroAdvancedConfig, NeuroRiskManager


@pytest.mark.asyncio
async def test_analyzer_returns_multiscale_dynamics() -> None:
    analyzer = MultiscaleFractalAnalyzer()
    rng = np.random.default_rng(123)
    prices = 100.0 + np.cumsum(rng.normal(0.0, 0.25, size=160))

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

    persistent_prices = 50.0 + np.cumsum(0.3 + rng.normal(0.0, 0.05, size=256))
    noise_prices = 50.0 + np.cumsum(rng.normal(0.0, 0.3, size=256))

    persistent_features = await analyzer.analyze(persistent_prices)
    noise_features = await analyzer.analyze(noise_prices)

    assert (
        persistent_features["dynamics"]["scaling_exponent"]
        > noise_features["dynamics"]["scaling_exponent"]
    )


@pytest.mark.asyncio
async def test_fractal_dynamics_adjust_risk_scaling() -> None:
    manager = NeuroRiskManager(NeuroAdvancedConfig())
    decision = {"position_size": 1.0, "risk_level": 0.6}
    neuro_context = {"overall_confidence": 0.8}
    base_market_context = {
        "volatility": 0.02,
        "fractal_scaling": 0.5,
        "fractal_stability": 0.8,
        "fractal_dim": 1.5,
    }

    base_adjusted = await manager.apply(decision, neuro_context, base_market_context)

    persistent_market_context = {
        **base_market_context,
        "fractal_scaling": 0.9,
        "fractal_stability": 0.95,
        "fractal_dim": 1.35,
    }
    persistent_adjusted = await manager.apply(decision, neuro_context, persistent_market_context)

    antipersistent_market_context = {
        **base_market_context,
        "fractal_scaling": 0.2,
        "fractal_stability": 0.4,
        "fractal_dim": 1.8,
    }
    antipersistent_adjusted = await manager.apply(decision, neuro_context, antipersistent_market_context)

    assert persistent_adjusted["position_size"] > base_adjusted["position_size"]
    assert antipersistent_adjusted["position_size"] < base_adjusted["position_size"]
    assert persistent_adjusted["risk_params"]["sl_dist"] == pytest.approx(base_adjusted["risk_params"]["sl_dist"])
    assert persistent_adjusted["risk_params"]["tp_dist"] == pytest.approx(base_adjusted["risk_params"]["tp_dist"])
