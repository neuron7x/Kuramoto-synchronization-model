import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, StreamingIGS


def test_entropy_adaptation_changes_k_with_loose_threshold():
    cfg = IGSConfig(
        window=120,
        n_states=5,
        min_counts=40,
        adapt_method="entropy",
        adapt_threshold=0.01,
        adapt_persist=1,
        adapt_cooldown=5,
    )
    engine = StreamingIGS(cfg)

    np.random.seed(42)
    n = 500
    prices = 100 + np.cumsum(np.random.randn(n))
    idx = pd.date_range("2024-01-01", periods=n, freq="T")

    k_values = set()
    for ts, price in zip(idx, prices):
        engine.update(ts, float(price))
        k_values.add(engine.K)

    assert len(k_values) >= 2
