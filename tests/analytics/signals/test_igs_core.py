from __future__ import annotations

import math

import numpy as np
import pandas as pd

import analytics.signals.irreversibility as igs
from analytics.signals.irreversibility import IGSConfig, StreamingIGS, compute_igs_features


def _random_walk(seed: int, length: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_price = np.cumsum(rng.standard_normal(length))
    price = 100.0 * np.exp(log_price / 100.0)
    index = pd.date_range("2024-01-01", periods=length, freq="min")
    return pd.Series(price, index=index)


def test_compute_igs_features_returns_expected_columns() -> None:
    series = _random_walk(seed=1, length=1500)
    config = IGSConfig(window=200, n_states=5, min_counts=50)
    features = compute_igs_features(series, config)
    assert list(features.columns) == ["epr", "flux_index", "tra", "pe", "regime_score"]
    assert features.index.equals(series.index)


def test_entropy_production_small_for_iid_noise() -> None:
    series = _random_walk(seed=2, length=2000)
    config = IGSConfig(window=250, n_states=5, min_counts=80)
    features = compute_igs_features(series, config)
    epr = features["epr"].dropna()
    assert not epr.empty
    assert float(epr.mean()) < 5.0


def test_streaming_matches_batch_tail_window() -> None:
    series = _random_walk(seed=3, length=1600)
    config = IGSConfig(window=200, n_states=5, min_counts=80)
    features = compute_igs_features(series, config)
    engine = StreamingIGS(config)
    metric = None
    for timestamp, price in series.items():
        metric = engine.update(timestamp, float(price))
    assert metric is not None
    batch_last = features.dropna().iloc[-1]
    assert np.isclose(metric.epr, batch_last["epr"], rtol=5e-1, atol=2e-2)
    assert np.isclose(metric.flux_index, batch_last["flux_index"], rtol=2e-1, atol=2e-2)


def test_regime_score_respects_weights_in_batch(monkeypatch) -> None:
    series = pd.Series(
        np.linspace(100.0, 110.0, 40),
        index=pd.date_range("2024-01-01", periods=40, freq="min"),
    )

    def fake_entropy_production(P, pi, eps):
        return math.expm1(0.3), np.zeros_like(P)

    monkeypatch.setattr(igs, "_entropy_production", fake_entropy_production)
    monkeypatch.setattr(igs, "_net_flux_index", lambda J, normalize: 0.9)
    monkeypatch.setattr(igs, "_time_reversal_asymmetry_arr", lambda arr: 0.0)
    monkeypatch.setattr(igs, "_permutation_entropy_arr", lambda arr, m, tau, eps: 0.2)

    cfg_equal = IGSConfig(window=10, n_states=4, min_counts=1, regime_weights=(1.0, 1.0, 1.0))
    cfg_fluxless = IGSConfig(window=10, n_states=4, min_counts=1, regime_weights=(1.0, 0.0, 1.0))

    expected_equal = igs._weighted_regime_score((0.3, 0.9, 0.8), cfg_equal.regime_weights)
    expected_fluxless = igs._weighted_regime_score((0.3, 0.9, 0.8), cfg_fluxless.regime_weights)

    features_equal = compute_igs_features(series, cfg_equal).dropna()
    features_fluxless = compute_igs_features(series, cfg_fluxless).dropna()

    assert not features_equal.empty and not features_fluxless.empty

    score_equal = float(features_equal.iloc[-1]["regime_score"])
    score_fluxless = float(features_fluxless.iloc[-1]["regime_score"])

    assert math.isclose(score_equal, expected_equal, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(score_fluxless, expected_fluxless, rel_tol=1e-12, abs_tol=1e-12)
    assert score_fluxless < score_equal


def test_regime_score_respects_weights_streaming(monkeypatch) -> None:
    series = pd.Series(
        np.linspace(100.0, 110.0, 40),
        index=pd.date_range("2024-01-01", periods=40, freq="min"),
    )

    def fake_entropy_production(P, pi, eps):
        return math.expm1(0.3), np.zeros_like(P)

    monkeypatch.setattr(igs, "_entropy_production", fake_entropy_production)
    monkeypatch.setattr(igs, "_net_flux_index", lambda J, normalize: 0.9)
    monkeypatch.setattr(igs.RollingPermutationEntropy, "update", lambda self, x: 0.2)

    cfg_equal = IGSConfig(window=10, n_states=4, min_counts=1, regime_weights=(1.0, 1.0, 1.0))
    cfg_fluxless = IGSConfig(window=10, n_states=4, min_counts=1, regime_weights=(1.0, 0.0, 1.0))

    expected_equal = igs._weighted_regime_score((0.3, 0.9, 0.8), cfg_equal.regime_weights)
    expected_fluxless = igs._weighted_regime_score((0.3, 0.9, 0.8), cfg_fluxless.regime_weights)

    engine_equal = StreamingIGS(cfg_equal)
    metric_equal = None
    for timestamp, price in series.items():
        metric_equal = engine_equal.update(timestamp, float(price))
    assert metric_equal is not None

    engine_fluxless = StreamingIGS(cfg_fluxless)
    metric_fluxless = None
    for timestamp, price in series.items():
        metric_fluxless = engine_fluxless.update(timestamp, float(price))
    assert metric_fluxless is not None

    assert math.isclose(metric_equal.regime_score, expected_equal, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(metric_fluxless.regime_score, expected_fluxless, rel_tol=1e-12, abs_tol=1e-12)
    assert metric_fluxless.regime_score < metric_equal.regime_score
