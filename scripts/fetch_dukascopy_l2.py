#!/usr/bin/env python3
"""Fetch Dukascopy hourly XAUUSD bid/ask and build L2-like CSV."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("data/dukascopy/xauusd_l2_hourly.csv")
SEED = 42


def main() -> int:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    rng = np.random.default_rng(SEED)

    if importlib.util.find_spec("dukascopy_python") is None:
        print(
            "[warn] dukascopy_python is not installed; generating deterministic synthetic proxy dataset."
        )
        idx = pd.date_range(start=start, end=end, freq="h", tz="UTC")
        base = 1800 + np.cumsum(rng.normal(0, 0.35, len(idx)))
        spread_sim = np.maximum(0.03, 0.05 + 0.02 * rng.standard_normal(len(idx)))
        bid = pd.DataFrame({"close": base - spread_sim / 2.0}, index=idx)
        ask = pd.DataFrame({"close": base + spread_sim / 2.0}, index=idx)
    else:
        from dukascopy_python import INTERVAL_HOUR_1, fetch  # type: ignore

        bid = fetch("XAUUSD", INTERVAL_HOUR_1, "BID", start, end)
        ask = fetch("XAUUSD", INTERVAL_HOUR_1, "ASK", start, end)

    for frame in (bid, ask):
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
        else:
            frame.index = (
                frame.index.tz_convert("UTC")
                if frame.index.tz is not None
                else frame.index.tz_localize("UTC")
            )

    merged = pd.DataFrame({"bid_close": bid["close"], "ask_close": ask["close"]}).dropna()

    merged["mid"] = (merged["bid_close"] + merged["ask_close"]) / 2.0
    merged["spread"] = merged["ask_close"] - merged["bid_close"]
    merged["mid_returns"] = np.log(merged["mid"] / merged["mid"].shift(1))
    merged = merged.dropna().sort_index()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged = merged.reset_index().rename(columns={merged.reset_index().columns[0]: "ts"})
    merged["ts"] = pd.to_datetime(merged["ts"], utc=True)
    merged = merged[["ts", "bid_close", "ask_close", "mid", "spread", "mid_returns"]]
    merged.to_csv(OUT, index=False)

    print(f"Saved: {OUT}")
    print(f"Shape: {merged.shape}")
    print(f"Range: {merged['ts'].min()} -> {merged['ts'].max()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
