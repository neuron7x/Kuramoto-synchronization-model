# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.signals.pipeline import (
    FeaturePipelineConfig,
    LeakageGate,
    SignalModelSelector,
    build_supervised_learning_frame,
    make_default_candidates,
)
from backtest.time_splits import WalkForwardSplitter
from core.compat import UTC
from core.data.ingestion import DataIngestor


def _write_synthetic_csv(path: Path, *, periods: int = 80) -> None:
    start = pd.Timestamp("2024-01-01 00:00:00", tz=UTC)
    index = pd.date_range(start=start, periods=periods, freq="1min", tz=UTC)
    rows: list[dict[str, object]] = []
    base_price = 100.0
    rng = np.random.default_rng(seed=1234)
    noise = rng.normal(0.0, 0.2, size=periods)
    drift = np.linspace(0.0, 1.5, periods)
    volumes = rng.integers(1, 5, size=periods)
    for ts, dz, vol in zip(index, noise, volumes, strict=True):
        price = base_price + drift[len(rows)] + dz
        rows.append(
            {
                "ts": ts.timestamp(),
                "price": round(price, 6),
                "volume": int(vol),
            }
        )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def test_ingestion_feature_signal_pipeline(tmp_path):
    csv_path = tmp_path / "synthetic_ticks.csv"
    _write_synthetic_csv(csv_path)

    ingestor = DataIngestor(allowed_roots=[tmp_path])
    collected = []
    ingestor.historical_csv(
        str(csv_path),
        collected.append,
        symbol="BTC-USD",
        venue="SYNTH",
    )

    assert len(collected) > 40

    index = pd.DatetimeIndex([tick.timestamp for tick in collected]).tz_convert(UTC)
    frame = pd.DataFrame(
        {
            "close": [float(tick.price) for tick in collected],
            "volume": [float(tick.volume) for tick in collected],
        },
        index=index,
    )

    features, target = build_supervised_learning_frame(
        frame,
        config=FeaturePipelineConfig(price_col="close", volume_col="volume"),
        gate=LeakageGate(lag=1, dropna=True),
        horizon=1,
    )

    assert not features.empty
    assert not target.empty
    assert features.index.equals(target.index)

    splitter = WalkForwardSplitter(train_window=10, test_window=5, freq="min")
    candidates = make_default_candidates()[:1]
    selector = SignalModelSelector(splitter, candidates=candidates)
    evaluations = selector.evaluate(features, target)

    assert evaluations
    best = evaluations[0]
    assert best.name == candidates[0].name
    assert "hit_rate" in best.aggregate_metrics
    assert "sharpe_ratio" in best.aggregate_metrics
    assert not best.regression_report.empty
