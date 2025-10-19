import math

import numpy as np
import pandas as pd

from analytics.signals.irreversibility import (
    IGSConfig,
    IGSMetrics,
    StreamingIGS,
    compute_igs_features,
)


def test_streaming_matches_batch_outputs() -> None:
    rng = np.random.default_rng(7)
    n = 1600
    prices = 120.0 * np.exp(np.cumsum(rng.normal(scale=0.4, size=n)) / 80.0)
    index = pd.date_range("2024-01-01", periods=n, freq="min")
    series = pd.Series(prices, index=index)

    cfg = IGSConfig(window=180, n_states=5, min_counts=160)
    features = compute_igs_features(series, cfg)
    engine = StreamingIGS(cfg)

    streaming_metrics: dict[pd.Timestamp, IGSMetrics] = {}
    for ts, price in series.items():
        metrics = engine.update(ts, float(price))
        if metrics:
            streaming_metrics[ts] = metrics

    for ts, row in features.dropna().iterrows():
        if ts not in streaming_metrics:
            continue
        metrics = streaming_metrics[ts]
        assert math.isclose(row["epr"], metrics.epr, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(row["flux_index"], metrics.flux_index, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(row["tra"], metrics.tra, rel_tol=1e-9, abs_tol=1e-9)
        if not math.isnan(row["pe"]):
            assert math.isclose(row["pe"], metrics.pe, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(row["regime_score"], metrics.regime_score, rel_tol=1e-9, abs_tol=1e-9)


def test_streaming_signal_thresholds() -> None:
    trend = np.linspace(0.0, 0.4, 400)
    noise = np.random.default_rng(11).normal(scale=0.02, size=400)
    prices = 80.0 * np.exp(np.cumsum(trend + noise) / 40.0)
    index = pd.date_range("2024-01-01", periods=400, freq="min")

    cfg = IGSConfig(window=100, n_states=5, min_counts=90)
    engine = StreamingIGS(cfg)
    threshold = None

    last_signal = 0
    for ts, price in zip(index, prices):
        metrics = engine.update(ts, float(price))
        if metrics:
            if threshold is None:
                threshold = max(0.1, metrics.epr / 2)
            last_signal = engine.get_signal(
                epr_threshold=threshold,
                flux_threshold=0.05,
                regime_threshold=0.2,
            )

    assert last_signal in (-1, 0, 1)
    assert engine.get_current_metrics() is not None
