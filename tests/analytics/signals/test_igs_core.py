from __future__ import annotations

import numpy as np
import pandas as pd

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
    assert list(features.columns) == ["epr", "flux_index", "tra", "pe", "balance_gap", "regime_score"]
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
    assert abs(metric.flux_index - batch_last["flux_index"]) < 0.1
    assert np.isfinite(metric.balance_gap)
