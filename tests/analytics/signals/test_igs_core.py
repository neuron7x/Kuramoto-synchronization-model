from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
import pandas as pd
import pytest

import analytics.signals.irreversibility as igs
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


def _valid_config_kwargs() -> dict:
    return {
        "window": 120,
        "n_states": 5,
        "min_counts": 60,
        "eps": 1e-9,
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


@pytest.mark.parametrize(
    "n_states,k_min,k_max,expect_error",
    [
        (4, 5, 15, True),
        (12, 5, 9, True),
        (7, 5, 9, False),
    ],
)
def test_igs_config_enforces_n_state_bounds(
    n_states: int, k_min: int, k_max: int, expect_error: bool
) -> None:
    kwargs = _valid_config_kwargs()
    kwargs.update({"n_states": n_states, "k_min": k_min, "k_max": k_max})

    if expect_error:
        with pytest.raises(
            ValueError, match="n_states must satisfy k_min <= n_states <= k_max"
        ):
            IGSConfig(**kwargs)
    else:
        cfg = IGSConfig(**kwargs)
        assert cfg.n_states == n_states
        assert cfg.k_min == k_min
        assert cfg.k_max == k_max


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
    config = IGSConfig(
        window=200, n_states=5, min_counts=80, quantize_mode=quantize_mode
    )
    features = compute_igs_features(series, config)
    engine = StreamingIGS(config)
    metric = None
    for timestamp, price in series.items():
        metric = engine.update(timestamp, float(price))
    assert metric is not None
    batch_last = features.dropna().iloc[-1]
    assert np.isclose(metric.epr, batch_last["epr"], rtol=5e-1, atol=2e-2)
    assert np.isclose(metric.flux_index, batch_last["flux_index"], rtol=5e-1, atol=5e-2)


def test_streaming_resets_on_invalid_prices() -> None:
    series = _random_walk(seed=17, length=800)
    gap_idx = 320
    series.iloc[gap_idx] = np.nan
    series.iloc[gap_idx + 1] = 0.0
    gap_ts = series.index[gap_idx]
    zero_ts = series.index[gap_idx + 1]
    recovery_candidates = series.iloc[gap_idx + 1 :][series.iloc[gap_idx + 1 :] > 0]
    assert not recovery_candidates.empty
    recovery_ts = recovery_candidates.index[0]
    recovery_start = series.index.get_loc(recovery_ts)
    config = IGSConfig(window=120, n_states=5, min_counts=60, quantize_mode="rank")
    features = compute_igs_features(series.iloc[recovery_start:], config).reindex(
        series.index
    )
    engine = StreamingIGS(config)
    metrics_by_ts: Dict[pd.Timestamp, Optional[igs.IGSMetrics]] = {}
    first_after_gap: Optional[pd.Timestamp] = None

    for timestamp, price in series.items():
        price_value = float(price) if pd.notna(price) else float("nan")
        metric = engine.update(timestamp, price_value)
        metrics_by_ts[timestamp] = metric
        if timestamp in {gap_ts, zero_ts}:
            assert metric is None
            assert engine.last_price is None
            assert engine.prev_state is None
            assert len(engine.returns) == 0
            assert len(engine.states) == 0
            assert float(engine.row_sums.sum()) == 0.0
            assert engine.tra_roll.n_pairs == 0
            assert engine.pe_roll.total == 0
        if metric is not None and first_after_gap is None and timestamp > zero_ts:
            first_after_gap = timestamp

    batch_valid = features.dropna()
    assert not batch_valid.empty
    post_gap_valid = batch_valid.loc[batch_valid.index > zero_ts]
    assert not post_gap_valid.empty
    assert first_after_gap is not None
    assert first_after_gap >= post_gap_valid.index[0]
    earlier_valid = post_gap_valid.loc[post_gap_valid.index < first_after_gap]
    for ts in earlier_valid.index:
        assert metrics_by_ts[ts] is None

    for timestamp, metric in metrics_by_ts.items():
        if timestamp < recovery_ts:
            continue
        if timestamp not in batch_valid.index:
            assert metric is None
            continue
        if metric is None:
            assert timestamp < first_after_gap
            continue
        row = batch_valid.loc[timestamp]
        assert np.isclose(metric.epr, row["epr"], rtol=5e-1, atol=2e-2)
        assert np.isclose(metric.flux_index, row["flux_index"], rtol=5e-1, atol=5e-2)
        assert np.isclose(metric.tra, row["tra"], rtol=5e-1, atol=5e-2, equal_nan=True)
        assert np.isclose(metric.pe, row["pe"], rtol=5e-1, atol=5e-2, equal_nan=True)


def test_batch_features_suppressed_across_gaps() -> None:
    series = _random_walk(seed=19, length=900)
    gap_idx = 400
    series.iloc[gap_idx] = np.nan
    series.iloc[gap_idx + 1] = 0.0
    zero_ts = series.index[gap_idx + 1]
    config = IGSConfig(window=150, n_states=5, min_counts=70, quantize_mode="zscore")

    features_full = compute_igs_features(series, config)
    engine = StreamingIGS(config)
    first_stream_ts: Optional[pd.Timestamp] = None

    for timestamp, price in series.items():
        price_value = float(price) if pd.notna(price) else float("nan")
        metric = engine.update(timestamp, price_value)
        if metric is not None and timestamp > zero_ts and first_stream_ts is None:
            first_stream_ts = timestamp

    assert first_stream_ts is not None

    post_gap_batch = features_full.loc[features_full.index > zero_ts]
    suppressed = post_gap_batch.loc[post_gap_batch.index < first_stream_ts]
    assert not suppressed.empty
    assert suppressed.isna().all().all()

    first_row = features_full.loc[first_stream_ts]
    assert not np.isnan(first_row["epr"])


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


def test_transition_matrix_stationary_distribution_matches_linear_solution() -> None:
    states = np.array([0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1])
    eps = 1e-9
    P_emp, pi_empirical = _transition_matrix(
        states, n_states=2, eps=eps, pi_method="empirical"
    )
    P_sta, pi_stationary = _transition_matrix(
        states, n_states=2, eps=eps, pi_method="stationary"
    )

    assert np.allclose(P_emp, P_sta)

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
    P, pi_empirical = _transition_matrix(
        states, n_states=2, eps=eps, pi_method="empirical"
    )
    _, pi_stationary = _transition_matrix(
        states, n_states=2, eps=eps, pi_method="stationary"
    )

    epr_empirical, _ = _entropy_production(P, pi_empirical, eps)
    epr_stationary, _ = _entropy_production(P, pi_stationary, eps)

    assert epr_stationary < epr_empirical
    assert epr_stationary < 1e-6


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
    monkeypatch.setattr(igs.RollingPermutationEntropy, "update", lambda self, x: 0.2)

    cfg_equal = IGSConfig(
        window=10, n_states=4, min_counts=1, regime_weights=(1.0, 1.0, 1.0)
    )
    cfg_fluxless = IGSConfig(
        window=10, n_states=4, min_counts=1, regime_weights=(1.0, 0.0, 1.0)
    )

    expected_equal = igs._weighted_regime_score(
        (0.3, 0.9, 0.8), cfg_equal.regime_weights
    )
    expected_fluxless = igs._weighted_regime_score(
        (0.3, 0.9, 0.8), cfg_fluxless.regime_weights
    )

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

    cfg_equal = IGSConfig(
        window=10, n_states=4, min_counts=1, regime_weights=(1.0, 1.0, 1.0)
    )
    cfg_fluxless = IGSConfig(
        window=10, n_states=4, min_counts=1, regime_weights=(1.0, 0.0, 1.0)
    )

    expected_equal = igs._weighted_regime_score(
        (0.3, 0.9, 0.8), cfg_equal.regime_weights
    )
    expected_fluxless = igs._weighted_regime_score(
        (0.3, 0.9, 0.8), cfg_fluxless.regime_weights
    )

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

    assert math.isclose(
        metric_equal.regime_score, expected_equal, rel_tol=1e-12, abs_tol=1e-12
    )
    assert math.isclose(
        metric_fluxless.regime_score, expected_fluxless, rel_tol=1e-12, abs_tol=1e-12
    )
    assert metric_fluxless.regime_score < metric_equal.regime_score


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"window": 2, "min_counts": 2}, "window must be >= 3"),
        ({"n_states": 1}, "n_states must be >= 2"),
        ({"min_counts": 0}, "min_counts must be >= 1"),
        ({"min_counts": 200}, "min_counts must be <= window"),
        ({"perm_emb_dim": 2}, "perm_emb_dim must be >= 3"),
        ({"perm_tau": 0}, "perm_tau must be >= 1"),
        (
            {"window": 4, "min_counts": 4, "perm_emb_dim": 5, "perm_tau": 1},
            r"window must be >= \(perm_emb_dim - 1\) \* perm_tau \+ 1 to compute permutation entropy",
        ),
        ({"k_min": 1}, "k_min must be >= 2"),
        ({"k_min": 10, "k_max": 5}, "k_min must be <= k_max"),
        ({"adapt_method": "unknown"}, "adapt_method must be one of"),
        ({"quantize_mode": "invalid"}, "quantize_mode must be one of"),
        ({"pi_method": "invalid"}, "pi_method must be one of"),
        (
            {"regime_weights": (1.0, 1.0)},
            "regime_weights must contain exactly three elements",
        ),
        ({"regime_weights": (-1.0, 1.0, 1.0)}, "regime_weights must be non-negative"),
        ({"regime_weights": (0.0, 0.0, 0.0)}, "regime_weights cannot be all zeros"),
        ({"max_update_ms": -1.0}, "max_update_ms must be >= 0"),
        ({"signal_epr_q": 1.0}, r"signal_epr_q must be in \(0, 1\)"),
        ({"signal_flux_min": -0.1}, "signal_flux_min must be >= 0"),
        ({"eps": 0.0}, "eps must be > 0"),
    ],
)
def test_igs_config_validation(overrides: dict, message: str) -> None:
    kwargs = _valid_config_kwargs()
    kwargs.update(overrides)
    with pytest.raises(ValueError, match=message):
        IGSConfig(**kwargs)


@pytest.mark.parametrize("eps", [0.0, -1e-12])
def test_config_rejects_non_positive_eps(eps: float) -> None:
    kwargs = _valid_config_kwargs()
    kwargs["eps"] = eps
    with pytest.raises(ValueError, match="eps must be > 0"):
        IGSConfig(**kwargs)


@pytest.mark.parametrize("min_counts", [-1, -10])
def test_config_rejects_negative_min_counts(min_counts: int) -> None:
    kwargs = _valid_config_kwargs()
    kwargs["min_counts"] = min_counts
    with pytest.raises(ValueError, match="min_counts must be >= 1"):
        IGSConfig(**kwargs)


def test_config_rejects_invalid_pi_method() -> None:
    with pytest.raises(ValueError):
        IGSConfig(pi_method="invalid")


def test_igs_config_accepts_min_window_for_permutation_entropy() -> None:
    kwargs = _valid_config_kwargs()
    kwargs.update({"perm_emb_dim": 6, "perm_tau": 2})
    kwargs["window"] = (kwargs["perm_emb_dim"] - 1) * kwargs["perm_tau"] + 1
    kwargs["min_counts"] = min(kwargs["min_counts"], kwargs["window"])

    cfg = IGSConfig(**kwargs)

    assert cfg.window == (cfg.perm_emb_dim - 1) * cfg.perm_tau + 1
