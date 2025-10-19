from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


@pytest.mark.parametrize("quantize_mode", ["zscore", "rank"])
def test_streaming_matches_batch_tail_window(quantize_mode: str) -> None:
    series = _random_walk(seed=3, length=1600)
    config = IGSConfig(window=200, n_states=5, min_counts=80, quantize_mode=quantize_mode)
    features = compute_igs_features(series, config)
    engine = StreamingIGS(config)
    metric = None
    for timestamp, price in series.items():
        metric = engine.update(timestamp, float(price))
    assert metric is not None
    batch_last = features.dropna().iloc[-1]
    assert np.isclose(metric.epr, batch_last["epr"], rtol=5e-1, atol=2e-2)
    assert np.isclose(metric.flux_index, batch_last["flux_index"], rtol=5e-1, atol=5e-2)


def test_rank_quantization_walk_forward_consistency() -> None:
    series = _random_walk(seed=7, length=900)
    config = IGSConfig(window=180, n_states=5, min_counts=60, quantize_mode="rank")
    full_features = compute_igs_features(series, config)
    cutoff = 720
    truncated = series.iloc[:cutoff]
    truncated_features = compute_igs_features(truncated, config)
    idx = truncated.index[-1]
    full_row = full_features.loc[idx]
    trunc_row = truncated_features.loc[idx]
    for column in ["epr", "flux_index", "tra", "pe", "regime_score"]:
        full_val = float(full_row[column])
        trunc_val = float(trunc_row[column])
        if np.isnan(full_val) and np.isnan(trunc_val):
            continue
        assert np.isclose(trunc_val, full_val, rtol=1e-9, atol=1e-9)
