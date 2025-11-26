import math
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from analytics.signals.irreversibility import (
    IGSConfig,
    RollingRankQuantizer,
    StreamingIGS,
    compute_igs_features,
)


@pytest.mark.parametrize("quant_mode", ["zscore", "rank"])
def test_batch_streaming_parity_quantization(quant_mode: str):
    rng = np.random.default_rng(42)
    periods = 320
    base_price = 100.0
    returns = rng.normal(0.0, 0.002, size=periods)
    log_prices = np.cumsum(np.insert(returns, 0, math.log(base_price)))
    prices = pd.Series(
        np.exp(log_prices[1:]),
        index=pd.date_range("2023-01-01", periods=periods, freq="min"),
    )

    cfg = IGSConfig(
        window=60,
        n_states=6,
        min_counts=45,
        quantize_mode=quant_mode,
        adapt_method="off",
        prometheus_enabled=False,
    )

    batch = compute_igs_features(prices, cfg)

    streamer = StreamingIGS(cfg)
    stream_records: Dict[pd.Timestamp, Dict[str, float]] = {}
    for ts, price in prices.items():
        metrics = streamer.update(ts, float(price))
        if metrics is None:
            continue
        stream_records[metrics.timestamp] = {
            "epr": metrics.epr,
            "flux_index": metrics.flux_index,
            "tra": metrics.tra,
            "pe": metrics.pe,
            "regime_score": metrics.regime_score,
        }

    stream_df = pd.DataFrame.from_dict(stream_records, orient="index").sort_index()

    common_idx = stream_df.index.intersection(batch.index)
    assert len(common_idx) > 0
    batch_common = batch.loc[
        common_idx, ["epr", "flux_index", "tra", "pe", "regime_score"]
    ]
    stream_common = stream_df.loc[common_idx]
    mask = batch_common.notna().all(axis=1) & stream_common.notna().all(axis=1)
    common_idx = common_idx[mask.values]
    assert len(common_idx) > 0

    batch_vals = batch_common.loc[common_idx]
    stream_vals = stream_common.loc[common_idx]

    for column in ["epr", "flux_index", "tra", "pe", "regime_score"]:
        np.testing.assert_allclose(
            stream_vals[column].to_numpy(),
            batch_vals[column].to_numpy(),
            rtol=1e-5,
            atol=1e-6,
            err_msg=f"Mismatch in {column}",
        )


def test_rolling_rank_quantizer_initial_states_centered():
    quantizer = RollingRankQuantizer(window=8, n_states=5)
    mid_bucket = quantizer.K // 2
    states = [quantizer.update_and_state(0.0) for _ in range(3)]
    assert all(state == mid_bucket for state in states)


def test_streaming_rank_quantizer_gap_resets_to_neutral_bucket():
    cfg = IGSConfig(
        window=20,
        n_states=5,
        quantize_mode="rank",
        min_counts=5,
        adapt_method="off",
        prometheus_enabled=False,
    )
    streamer = StreamingIGS(cfg)
    t0 = pd.Timestamp("2024-01-01 00:00:00")
    mid_bucket = cfg.n_states // 2

    streamer.update(t0, 100.0)
    assert list(streamer.states) == [mid_bucket]

    streamer.update(t0 + pd.Timedelta(minutes=1), float("nan"))
    assert list(streamer.states) == []

    streamer.update(t0 + pd.Timedelta(minutes=2), 105.0)
    assert list(streamer.states) == [mid_bucket]
