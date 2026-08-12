# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for advanced regime analytics modules."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from analytics.regime.src.core import (
    CausalGuard,
    CausalGuardConfig,
    EarlyWarningSignal,
    EWSConfig,
    FKDetector,
    FKDetectorConfig,
    RegimeDetector,
    RicciFlowConfig,
    RicciFlowRebalancer,
    TopoSentinel,
    TopoSentinelConfig,
)
from analytics.regime.src.core.causal_guard import CausalGuardResult
from analytics.regime.src.core.fk_detector import FKDetectorResult
from analytics.regime.src.core.ricci_flow import RicciFlowResult
from analytics.regime.src.core.topo_sentinel import TopoSentinelResult


def _synthetic_prices(periods: int, assets: int) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=periods, freq="5min")
    base = np.linspace(100, 120, periods)
    rng = np.random.default_rng(42)
    prices = {}
    for i in range(assets):
        noise = rng.normal(scale=0.2, size=periods).cumsum()
        prices[f"asset_{i}"] = base + noise + i
    return pd.DataFrame(prices, index=index)


def test_fk_detector_triggers_on_strong_synchronisation():
    prices = _synthetic_prices(200, 4)
    detector = FKDetector(
        config=FKDetectorConfig(window=120, kuramoto_lag=2, minimum_series_length=64)
    )

    calibration_returns = np.log(prices).diff().dropna().iloc[:120]
    calibration = detector.calibrate_from_window(calibration_returns)
    detector = FKDetector(config=detector.config, calibration=calibration)

    result = detector.compute(prices.tail(150))

    assert isinstance(result, FKDetectorResult)
    assert math.isfinite(result.fk_index)
    assert math.isfinite(result.r_value)
    assert result.trigger_threshold == calibration.trigger_threshold


def test_regime_detector_calibration_updates_thresholds():
    prices = _synthetic_prices(240, 3)
    volume_base = np.linspace(800.0, 1_200.0, len(prices))
    volumes = pd.DataFrame(
        {column: volume_base + i * 25.0 for i, column in enumerate(prices.columns)},
        index=prices.index,
    )
    spread_base = np.linspace(0.04, 0.02, len(prices))
    spreads = pd.DataFrame(
        {column: spread_base + i * 0.002 for i, column in enumerate(prices.columns)},
        index=prices.index,
    )

    detector = RegimeDetector()
    original = detector.config

    calibrated = detector.calibrate(
        prices,
        volumes=volumes,
        spreads=spreads,
        trending_quantile=0.8,
        liquidity_high_quantile=0.75,
        liquidity_low_quantile=0.25,
        correlation_high_quantile=0.8,
        correlation_low_quantile=0.2,
    )

    assert calibrated is detector.config
    assert any(
        [
            calibrated.trending_zscore != original.trending_zscore,
            calibrated.mean_reverting_autocorr_threshold
            != original.mean_reverting_autocorr_threshold,
            calibrated.liquidity_score_high != original.liquidity_score_high,
            calibrated.liquidity_score_low != original.liquidity_score_low,
            calibrated.correlation_high_threshold != original.correlation_high_threshold,
            calibrated.correlation_low_threshold != original.correlation_low_threshold,
        ]
    )
    assert calibrated.liquidity_score_high > calibrated.liquidity_score_low
    assert (
        0.0 <= calibrated.correlation_low_threshold <= calibrated.correlation_high_threshold <= 1.0
    )


def test_regime_detector_calibration_requires_history():
    index = pd.date_range("2024-01-01", periods=3, freq="h")
    prices = pd.DataFrame({"asset_a": [100.0, 100.4, 100.6]}, index=index)
    detector = RegimeDetector()

    with pytest.raises(ValueError):
        detector.calibrate(prices.iloc[:2])


def test_regime_detector_calibration_skips_single_asset_correlation():
    prices = _synthetic_prices(240, 1)
    detector = RegimeDetector()
    original = detector.config

    calibrated = detector.calibrate(prices)

    assert calibrated.correlation_high_threshold == original.correlation_high_threshold
    assert calibrated.correlation_low_threshold == original.correlation_low_threshold


def test_ricci_flow_rebalancer_projected_simplex():
    covariance = pd.DataFrame(
        [[0.04, 0.01, 0.012], [0.01, 0.03, 0.008], [0.012, 0.008, 0.05]],
        columns=["a", "b", "c"],
        index=["a", "b", "c"],
    )
    rebalancer = RicciFlowRebalancer(RicciFlowConfig(step_size=0.1, turnover_penalty=0.2))
    result = rebalancer.rebalance(covariance)

    assert isinstance(result, RicciFlowResult)
    assert math.isclose(result.weights.sum(), 1.0, rel_tol=1e-6)
    assert (result.weights >= 0).all()
    assert math.isfinite(result.ricci_mean)


def test_topo_sentinel_outputs_euler_curve():
    returns = np.log(_synthetic_prices(180, 5)).diff().dropna()
    sentinel = TopoSentinel(TopoSentinelConfig(persistence_thresholds=(0.05, 0.1, 0.2)))
    result = sentinel.compute(returns)

    assert isinstance(result, TopoSentinelResult)
    assert result.euler_curve.index.tolist() == [0.05, 0.1, 0.2]
    assert math.isfinite(result.topo_score)
    assert result.tda_count_long >= 0


def test_causal_guard_scales_gates():
    matrix = pd.DataFrame(
        {
            "asset_a": {"asset_a": 0.0, "asset_b": 0.12},
            "asset_b": {"asset_a": 0.08, "asset_b": 0.0},
        }
    )
    guard = CausalGuard(CausalGuardConfig(kappa=0.5, te_threshold=0.05))
    result = guard.evaluate(
        matrix,
        rolling_te={("asset_b", "asset_a"): 0.1, ("asset_a", "asset_b"): 0.06},
        ftest_pass={("asset_b", "asset_a"): True, ("asset_a", "asset_b"): True},
    )

    assert isinstance(result, CausalGuardResult)
    assert (result.gates < 1.0).any()
    assert (result.gates >= guard.config.min_gate).all()


def test_ews_aggregator_combines_scores():
    fk = FKDetectorResult(
        fk_index=1.2,
        r_value=0.9,
        delta_r=0.1,
        hurst_mean=0.4,
        hurst_dispersion=0.05,
        trigger_threshold=1.0,
        triggered=True,
    )
    ricci = RicciFlowResult(
        weights=pd.Series([0.4, 0.3, 0.3], index=["a", "b", "c"]),
        ricci_mean=0.6,
        curvature_distribution=pd.Series([0.5, 0.6, 0.7], index=["a", "b", "c"]),
        objective_value=0.2,
    )
    topo = TopoSentinelResult(
        topo_score=0.8,
        tda_count_long=2,
        tda_entropy=0.3,
        euler_curve=pd.Series([2.0, 1.5, 1.0], index=[0.05, 0.1, 0.2]),
    )
    causal = CausalGuardResult(
        gates=pd.Series([0.9, 0.85], index=["a", "b"]),
        causal_strength=pd.Series([0.1, 0.2], index=["a", "b"]),
    )

    ews = EarlyWarningSignal(
        EWSConfig(weight_fk=0.6, weight_ricci=0.4, weight_topo=0.3, weight_causal=0.2)
    )
    result = ews.aggregate(
        fk,
        ricci,
        topo,
        causal,
        online_auc=0.55,
        false_positive_rate=0.2,
    )

    assert 0.0 <= result.probability <= 1.0
    assert result.kill_switch_recommended is True
