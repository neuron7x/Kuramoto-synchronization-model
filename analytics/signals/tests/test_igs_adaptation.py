import numpy as np
import pandas as pd

from analytics.signals.irreversibility import (
    IGSConfig,
    StreamingIGS,
    compute_igs_features,
)


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


def test_k_adaptation_rebuild_matches_batch_metrics():
    window = 80
    cfg = IGSConfig(
        window=window,
        n_states=5,
        min_counts=40,
        adapt_method="external",
        adapt_threshold=0.05,
        adapt_persist=1,
        adapt_cooldown=0,
        adapt_step=2,
        k_max=9,
    )

    call_counter = {"count": 0}

    def external_measure(_P):
        call_counter["count"] += 1
        return 0.0 if call_counter["count"] < 4 else 1.0

    engine = StreamingIGS(cfg, external_adaptation_measure=external_measure)

    rng = np.random.default_rng(7)
    n = 600
    prices = 100.0 + np.cumsum(rng.normal(scale=0.8, size=n))
    idx = pd.date_range("2024-01-01", periods=n, freq="min")

    current_K = engine.K
    adaptation_seen = False
    just_adapted = False
    metrics_after = []
    for ts, price in zip(idx, prices):
        metric = engine.update(ts, float(price))
        if engine.K != current_K:
            adaptation_seen = True
            current_K = engine.K
            just_adapted = True
        else:
            if just_adapted:
                just_adapted = False
            if adaptation_seen and metric is not None and not just_adapted:
                metrics_after.append((ts, metric))

    assert adaptation_seen, "K adaptation did not trigger"
    assert metrics_after, "No metrics captured after adaptation"

    final_K = engine.K
    series_full = pd.Series(prices, index=idx)
    batch_cfg = IGSConfig(window=window, n_states=final_K, min_counts=cfg.min_counts)
    batch_features = compute_igs_features(series_full, batch_cfg)

    matched = False
    for ts, metric in metrics_after:
        row = batch_features.loc[ts]
        if np.isnan(row["epr"]) or np.isnan(row["flux_index"]):
            continue
        assert np.isclose(metric.epr, row["epr"], rtol=0.25, atol=0.05)
        assert np.isclose(metric.flux_index, row["flux_index"], rtol=0.5, atol=0.07)
        matched = True
        break

    assert matched, "Did not find a batch metric to compare after adaptation"
