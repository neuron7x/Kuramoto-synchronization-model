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


def _valid_config_kwargs() -> dict:
    return {
        "window": 120,
        "n_states": 5,
        "min_counts": 60,
        "perm_emb_dim": 5,
        "perm_tau": 1,
        "k_min": 5,
        "k_max": 15,
        "quantize_mode": "zscore",
        "adapt_method": "off",
        "pi_method": "empirical",
        "regime_weights": (1.0, 1.0, 1.0),
        "max_update_ms": 0.0,
        "signal_epr_q": 0.7,
        "signal_flux_min": 0.0,
    }


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


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"window": 2, "min_counts": 2}, "window must be >= 3"),
        ({"n_states": 1}, "n_states must be >= 2"),
        ({"min_counts": 200}, "min_counts must be <= window"),
        ({"perm_emb_dim": 2}, "perm_emb_dim must be >= 3"),
        ({"perm_tau": 0}, "perm_tau must be >= 1"),
        ({"k_min": 1}, "k_min must be >= 2"),
        ({"k_min": 10, "k_max": 5}, "k_min must be <= k_max"),
        ({"adapt_method": "unknown"}, "adapt_method must be one of"),
        ({"quantize_mode": "invalid"}, "quantize_mode must be one of"),
        ({"pi_method": "invalid"}, "pi_method must be one of"),
        ({"regime_weights": (1.0, 1.0)}, "regime_weights must contain exactly three elements"),
        ({"regime_weights": (-1.0, 1.0, 1.0)}, "regime_weights must be non-negative"),
        ({"regime_weights": (0.0, 0.0, 0.0)}, "regime_weights cannot be all zeros"),
        ({"max_update_ms": -1.0}, "max_update_ms must be >= 0"),
        ({"signal_epr_q": 1.0}, r"signal_epr_q must be in \(0, 1\)"),
        ({"signal_flux_min": -0.1}, "signal_flux_min must be >= 0"),
    ],
)
def test_igs_config_validation(overrides: dict, message: str) -> None:
    kwargs = _valid_config_kwargs()
    kwargs.update(overrides)
    with pytest.raises(ValueError, match=message):
        IGSConfig(**kwargs)
