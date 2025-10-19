import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, compute_igs_features, igs_directional_signal


def _make_price_series(seed: int, n: int = 1500) -> pd.Series:
    rng = np.random.default_rng(seed)
    returns = rng.normal(scale=0.5, size=n)
    prices = 100.0 * np.exp(np.cumsum(returns) / 100.0)
    index = pd.date_range("2024-01-01", periods=n, freq="min")
    return pd.Series(prices, index=index, name="close")


def test_compute_igs_features_has_expected_structure() -> None:
    price = _make_price_series(1)
    cfg = IGSConfig(window=120, n_states=5, min_counts=80)
    features = compute_igs_features(price, cfg)

    assert list(features.columns) == ["epr", "flux_index", "tra", "pe", "regime_score"]
    assert features.index.equals(price.index)
    assert features.iloc[: cfg.window].isna().all().all()
    assert features.iloc[cfg.window :].notna().any(axis=1).any()


def test_directional_signal_prefers_trending_windows() -> None:
    n = 1200
    trend = np.linspace(0.0, 0.8, n)
    noise = np.random.default_rng(42).normal(scale=0.05, size=n)
    prices = 50.0 * np.exp(np.cumsum(trend + noise) / 50.0)
    index = pd.date_range("2024-01-01", periods=n, freq="min")
    series = pd.Series(prices, index=index)

    cfg = IGSConfig(window=200, n_states=7, min_counts=180)
    features = compute_igs_features(series, cfg)
    signal = igs_directional_signal(features, epr_q=0.6, flux_q=0.6, regime_threshold=0.3)

    assert (signal == -1).sum() == 0
    assert (signal == 1).sum() > 0
