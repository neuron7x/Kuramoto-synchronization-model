import numpy as np
import pandas as pd

from analytics.signals.irreversibility_adapter import IGSFeatureProvider


def test_feature_provider_batch_interface() -> None:
    rng = np.random.default_rng(21)
    prices = 90.0 * np.exp(np.cumsum(rng.normal(scale=0.3, size=800)) / 60.0)
    index = pd.date_range("2024-01-01", periods=800, freq="min")
    series = pd.Series(prices, index=index)

    provider = IGSFeatureProvider({"window": 150, "n_states": 5, "min_counts": 130})
    features = provider.compute_batch(series)

    assert set(features.columns) == {"epr", "flux_index", "tra", "pe", "regime_score"}
    assert features.index.equals(series.index)


def test_streaming_update_emits_metrics() -> None:
    rng = np.random.default_rng(5)
    prices = 75.0 * np.exp(np.cumsum(rng.normal(loc=0.05, scale=0.15, size=500)) / 30.0)
    index = pd.date_range("2024-01-01", periods=500, freq="min")

    provider = IGSFeatureProvider({"window": 120, "n_states": 5, "min_counts": 110})
    last_metrics = None
    for ts, price in zip(index, prices):
        last_metrics = provider.streaming_update("TEST", ts, float(price)) or last_metrics

    assert last_metrics is not None
    assert last_metrics.regime in {"reversible", "directional", "turbulent", "mixed"}
