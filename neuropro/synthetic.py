"""Synthetic data generation utilities for NeuroTrade PRO demos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_DEMO_TICKS_PATH = Path(__file__).resolve().parent / "data" / "sim_ticks.csv"


def generate_demo_ticks(
    path: str | Path = DEFAULT_DEMO_TICKS_PATH,
    *,
    n: int = 15000,
    seed: int = 7,
) -> Path:
    """Generate a synthetic tick dataset for demonstration flows.

    The generated CSV mirrors the previous repository fixture while avoiding the
    need to store ~4 MB of static data in git. The schema matches the
    expectations baked into ``configs/demo.yaml`` and downstream NeuroPRO
    pipelines.
    """

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)

    regimes = np.zeros(n, dtype=int)
    regimes[4000:8000] = 1
    regimes[8000:12000] = 2
    regimes[12000:] = 1

    drift = np.choose(regimes, [0.0, 0.00003, -0.00002])
    vol = np.choose(regimes, [0.0006, 0.0012, 0.0018])
    returns = drift + rng.normal(0, vol)
    mid = 100 + np.cumsum(returns)

    spread = np.clip(rng.normal(0.0002, 0.00007, size=n), 0.00005, 0.0008)
    bid = mid - 0.5 * spread * mid
    ask = mid + 0.5 * spread * mid
    last = mid + rng.normal(0, spread * mid / 3)

    bid_size = rng.integers(5, 50, size=n)
    ask_size = rng.integers(5, 50, size=n)
    last_size = rng.integers(1, 10, size=n)

    ts = pd.date_range("2024-01-01 09:30:00", periods=n, freq="s")

    df = pd.DataFrame(
        {
            "timestamp": ts,
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "last": last,
            "last_size": last_size,
        }
    )

    df["ret1"] = df["mid"].pct_change().fillna(0.0)
    df["ret5"] = df["mid"].pct_change(5).fillna(0.0)
    df["ret20"] = df["mid"].pct_change(20).fillna(0.0)
    df["vol10"] = df["ret1"].rolling(10).std().bfill().fillna(0.0)
    df["vol50"] = df["ret1"].rolling(50).std().bfill().fillna(0.0)
    df["spread"] = spread
    df["regime"] = regimes
    df["y"] = df["mid"].shift(-10).ffill() / df["mid"] - 1.0

    df.to_csv(out_path, index=False)
    return out_path
