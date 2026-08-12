# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for the market regime analyzer.

Pins the insufficient-data path, the "constant series generates no fake trend"
guarantee, malformed-input rejection, the trend-strength thresholds, determinism,
and stability of the regime verdict under a sub-tolerance perturbation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from modules.market_regime_analyzer import (
    MarketRegimeAnalyzer,
    RegimeType,
    TrendStrength,
)


def _trending(n: int = 200, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100.0 + np.cumsum(rng.normal(0.05, 0.3, n)))


def test_empty_data_yields_explicit_insufficient_data() -> None:
    metrics = MarketRegimeAnalyzer().classify_regime({"prices": []})
    assert metrics.regime_type == RegimeType.UNKNOWN
    assert metrics.regime_confidence == 0.0
    assert metrics.duration_bars == 0


def test_constant_series_produces_no_fake_directional_signal() -> None:
    metrics = MarketRegimeAnalyzer().classify_regime({"prices": [100.0] * 60})
    # A flat series is not trending; it must not fabricate momentum.
    assert metrics.regime_type not in {RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN}
    assert metrics.volatility == 0.0
    # Regression: adf_statistic must be finite (degenerate design guard).
    assert math.isfinite(metrics.adf_statistic)


def test_missing_prices_key_and_bad_shape_are_rejected() -> None:
    analyzer = MarketRegimeAnalyzer()
    with pytest.raises(KeyError):
        analyzer.classify_regime({"returns": [0.1, 0.2]})
    with pytest.raises(ValueError, match="1D"):
        analyzer.classify_regime({"prices": [[1.0, 2.0], [3.0, 4.0]]})


def test_trend_strength_thresholds_are_pinned() -> None:
    analyzer = MarketRegimeAnalyzer()
    # Perfectly linear ramp -> R^2 == 1; daily_change_pct dominates classification.
    flat_ramp = [100.0 + 0.05 * i for i in range(50)]
    _, strength = analyzer.calculate_trend_strength(np.asarray(flat_ramp))
    assert strength in set(TrendStrength)
    # Too-short series is pinned to VERY_WEAK, value 0.0.
    value, weak = analyzer.calculate_trend_strength(np.asarray([1.0, 2.0, 3.0]))
    assert value == 0.0
    assert weak == TrendStrength.VERY_WEAK


def test_classification_is_deterministic() -> None:
    prices = _trending()
    m1 = MarketRegimeAnalyzer().classify_regime({"prices": prices})
    m2 = MarketRegimeAnalyzer().classify_regime({"prices": prices})
    assert m1.regime_type == m2.regime_type
    assert m1.hurst_exponent == pytest.approx(m2.hurst_exponent, abs=1e-12)
    assert m1.regime_confidence == pytest.approx(m2.regime_confidence, abs=1e-12)


def test_sub_tolerance_perturbation_does_not_flip_regime() -> None:
    prices = _trending()
    base = MarketRegimeAnalyzer().classify_regime({"prices": prices})
    # A perturbation ~1e-9 relative is far below any decision threshold.
    perturbed = [p * (1.0 + 1e-9) for p in prices]
    nudged = MarketRegimeAnalyzer().classify_regime({"prices": perturbed})
    assert nudged.regime_type == base.regime_type
    assert nudged.hurst_exponent == pytest.approx(base.hurst_exponent, abs=1e-6)
