from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.signals.irreversibility import (
    IGSConfig,
    StreamingIGS,
    _entropy_production,
    _transition_matrix,
    compute_igs_features,
)


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


def test_transition_matrix_stationary_distribution_matches_linear_solution() -> None:
    states = np.array([0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1])
    eps = 1e-9
    P_emp, pi_empirical = _transition_matrix(states, n_states=2, eps=eps, pi_method="empirical")
    P_sta, pi_stationary = _transition_matrix(states, n_states=2, eps=eps, pi_method="stationary")

    assert np.allclose(P_emp, P_sta)

    # Solve the constrained linear system independently to confirm the stationary solution.
    A = np.vstack([P_sta.T - np.eye(2), np.ones((1, 2))])
    b = np.concatenate([np.zeros(2), np.array([1.0])])
    expected, *_ = np.linalg.lstsq(A, b, rcond=None)
    expected = np.maximum(expected, 0.0)
    expected = expected / expected.sum()

    assert not np.allclose(pi_empirical, pi_stationary)
    assert np.allclose(pi_stationary, expected, atol=1e-8)


def test_entropy_production_differs_between_pi_methods() -> None:
    states = np.array([0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1])
    eps = 1e-9
    P, pi_empirical = _transition_matrix(states, n_states=2, eps=eps, pi_method="empirical")
    _, pi_stationary = _transition_matrix(states, n_states=2, eps=eps, pi_method="stationary")

    epr_empirical, _ = _entropy_production(P, pi_empirical, eps)
    epr_stationary, _ = _entropy_production(P, pi_stationary, eps)

    assert epr_stationary < epr_empirical
    assert epr_stationary < 1e-6


def test_config_rejects_invalid_pi_method() -> None:
    with pytest.raises(ValueError):
        IGSConfig(pi_method="invalid")
