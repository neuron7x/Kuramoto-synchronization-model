import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, compute_igs_features


def test_epr_reasonable_on_noise():
    np.random.seed(1)
    n = 2000
    prices = 100 + np.cumsum(np.random.randn(n))
    series = pd.Series(prices, index=pd.date_range("2024-01-01", periods=n, freq="T"))

    cfg = IGSConfig(window=200, n_states=5, min_counts=50)
    feats = compute_igs_features(series, cfg)

    assert "epr" in feats.columns
    epr_mean = feats["epr"].dropna().mean()
    assert epr_mean < 5.0


def test_flux_in_bounds():
    np.random.seed(2)
    n = 1500
    prices = 100 + np.cumsum(np.random.randn(n))
    series = pd.Series(prices, index=pd.date_range("2024-01-01", periods=n, freq="T"))

    cfg = IGSConfig(window=200, n_states=5, min_counts=50)
    feats = compute_igs_features(series, cfg)

    flux = feats["flux_index"].dropna()
    assert len(flux) > 0
    assert (flux >= -1).all() and (flux <= 1).all()
