# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_detect_trending_high_vol_and_liquid():
    module = importlib.import_module("analytics.regime.src.core.main")
    RegimeDetector = module.RegimeDetector
    TrendRegime = module.TrendRegime
    LiquidityRegime = module.LiquidityRegime

    index = pd.date_range("2024-01-01", periods=200, freq="h")
    base = np.linspace(100, 150, 200)
    noise = np.sin(np.linspace(0, 16 * np.pi, 200)) * 4.0
    prices = pd.DataFrame(
        {
            "asset_a": base + noise,
            "asset_b": base * 0.97 + noise * 0.8,
        },
        index=index,
    )
    volumes = pd.DataFrame(
        {
            "asset_a": np.linspace(1_200, 1_800, 200),
            "asset_b": np.linspace(1_150, 1_750, 200),
        },
        index=index,
    )
    spreads = pd.DataFrame(
        {
            "asset_a": np.linspace(0.01, 0.02, 200),
            "asset_b": np.linspace(0.012, 0.018, 200),
        },
        index=index,
    )

    detector = RegimeDetector()
    snapshot = detector.detect(prices, volumes=volumes, spreads=spreads)

    assert snapshot.trend is TrendRegime.TRENDING
    assert snapshot.liquidity in {LiquidityRegime.MODERATE, LiquidityRegime.HIGH}
    assert "trend" in snapshot.adjustments.notes.lower()
    assert "trend_signal_sensitivity" in snapshot.adjustments.parameter_overrides


def test_detect_mean_reverting_low_liquidity():
    module = importlib.import_module("analytics.regime.src.core.main")
    RegimeDetector = module.RegimeDetector
    TrendRegime = module.TrendRegime
    LiquidityRegime = module.LiquidityRegime
    VolatilityRegime = module.VolatilityRegime

    index = pd.date_range("2024-02-01", periods=160, freq="h")
    pattern = np.array([100.0, 101.2, 100.2, 99.6])
    prices = pd.DataFrame(
        {
            "asset_a": np.tile(pattern, 40),
        },
        index=index,
    )
    volumes = pd.DataFrame(
        {
            "asset_a": np.linspace(200, 150, 160),
        },
        index=index,
    )
    spreads = pd.DataFrame(
        {
            "asset_a": np.linspace(0.05, 0.06, 160),
        },
        index=index,
    )

    detector = RegimeDetector()
    snapshot = detector.detect(prices, volumes=volumes, spreads=spreads)

    assert snapshot.trend is TrendRegime.MEAN_REVERTING
    assert snapshot.volatility is VolatilityRegime.LOW
    assert snapshot.liquidity is LiquidityRegime.LOW
    assert snapshot.adjustments.execution_style == "passive"
    assert snapshot.adjustments.position_scale < 1.0


def test_correlation_decoupled_triggers_diversification():
    module = importlib.import_module("analytics.regime.src.core.main")
    RegimeDetector = module.RegimeDetector
    CorrelationRegime = module.CorrelationRegime

    index = pd.date_range("2024-03-01", periods=180, freq="h")
    rng = np.random.default_rng(42)
    matrix = rng.standard_normal((180, 3))
    q, _ = np.linalg.qr(matrix)
    returns = pd.DataFrame(q * 0.01, columns=["asset_a", "asset_b", "asset_c"], index=index)
    prices = 100 * (1 + returns).cumprod()

    volumes = pd.DataFrame(
        {
            "asset_a": np.linspace(800, 900, 180),
            "asset_b": np.linspace(820, 880, 180),
            "asset_c": np.linspace(780, 860, 180),
        },
        index=index,
    )

    detector = RegimeDetector()
    snapshot = detector.detect(prices, volumes=volumes)

    assert snapshot.correlation is CorrelationRegime.DECOUPLED
    assert snapshot.adjustments.parameter_overrides["max_gross_exposure"] > 1.0
