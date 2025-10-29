"""Tests for the adaptive regime detector."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from markets.regime import RegimeDetectionResult, RegimeDetector


ALLOWED_REGIMES = {"bull_trend", "bear_trend", "range_bound", "volatile_breakout"}


def _synthetic_market_history() -> pd.DataFrame:
    rng = np.random.default_rng(123)
    periods = 360
    index = pd.date_range("2022-01-01", periods=periods, freq="h")

    up_trend = 100 + np.linspace(0, 15, 120) + rng.normal(scale=0.3, size=120)
    up_volume = 1_000 + rng.normal(scale=60, size=120)

    range_bound = 115 + rng.normal(scale=0.2, size=120)
    range_volume = 900 + rng.normal(scale=45, size=120)

    down_trend = 115 - np.linspace(0, 18, 120) + rng.normal(scale=0.8, size=120)
    down_volume = 1_400 + rng.normal(scale=90, size=120)

    prices = np.concatenate([up_trend, range_bound, down_trend])
    volumes = np.concatenate([up_volume, range_volume, down_volume])

    prices = np.maximum(prices, 1.0)
    volumes = np.maximum(volumes, 10.0)

    return pd.DataFrame({"price": prices, "volume": volumes}, index=index)


def test_regime_detector_produces_named_states() -> None:
    history = _synthetic_market_history()
    detector = RegimeDetector(n_regimes=3, window=24, random_state=7)

    fitted = detector.fit(history, price_col="price", volume_col="volume")

    assert "regime" in fitted
    label_set = set(detector._regime_labels.values())
    assert len(label_set) == detector.n_regimes
    assert label_set.issubset(ALLOWED_REGIMES)

    for label in label_set:
        column = f"prob_{label}"
        assert column in fitted
        assert np.all((fitted[column] >= 0.0) & (fitted[column] <= 1.0))

    recent = history.iloc[-180:]
    predicted = detector.predict(recent, price_col="price", volume_col="volume")
    assert not predicted.empty
    assert predicted["regime"].isin(label_set).all()

    latest = detector.latest(recent, price_col="price", volume_col="volume")
    assert isinstance(latest, RegimeDetectionResult)
    assert latest.regime in label_set
    assert set(latest.probabilities) == label_set
    prob_sum = float(sum(latest.probabilities.values()))
    assert math.isclose(prob_sum, 1.0, rel_tol=1e-3)
    assert latest.features is not None
    assert {"trend", "momentum", "volatility", "volume_z"} <= set(latest.features.index)
