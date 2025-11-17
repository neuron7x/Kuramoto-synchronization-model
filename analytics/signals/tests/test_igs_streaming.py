import numpy as np
import pandas as pd
import pytest

from analytics.signals.irreversibility import (
    IGSConfig,
    StreamingIGS,
    compute_igs_features,
)


@pytest.mark.parametrize("quantize_mode", ["zscore", "rank"])
def test_streaming_approx_batch(quantize_mode: str):
    np.random.seed(3)
    n = 1500
    prices = 100 + np.cumsum(np.random.randn(n))
    idx = pd.date_range("2024-01-01", periods=n, freq="T")
    series = pd.Series(prices, index=idx)

    cfg = IGSConfig(
        window=200,
        n_states=5,
        min_counts=50,
        adapt_method="off",
        quantize_mode=quantize_mode,
    )
    feats = compute_igs_features(series, cfg)
    engine = StreamingIGS(cfg)

    metrics = []
    for ts, price in zip(idx, prices):
        metrics.append(engine.update(ts, float(price)))

    batch_valid = feats.dropna(subset=["epr"])
    if batch_valid.empty:
        return

    last_ts = batch_valid.index[-1]
    stream_metric = None
    for metric in reversed(metrics):
        if metric is not None and metric.timestamp == last_ts:
            stream_metric = metric
            break

    if stream_metric is None:
        return

    batch_epr = float(batch_valid.loc[last_ts, "epr"])
    diff = abs(batch_epr - stream_metric.epr)
    rel = diff / (abs(batch_epr) + 1e-9)
    assert diff < 1e-2 or rel < 1e-2
