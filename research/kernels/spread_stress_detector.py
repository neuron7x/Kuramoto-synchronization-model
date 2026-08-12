"""Task 13: spread stress detector with train-frozen z-score."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import spearmanr


def _scorr(a: pd.Series, b: pd.Series) -> float:
    df = pd.concat([a, b], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 0.0
    return float(spearmanr(df.iloc[:, 0], df.iloc[:, 1]).statistic)


def compute_spread_z(input_csv: Path) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    df = pd.read_csv(input_csv)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").set_index("ts")

    spread = df["spread"].astype(float)
    split = int(0.7 * len(spread))
    train = spread.iloc[:split]
    mu, sd = float(train.mean()), float(train.std() or 1e-8)
    spread_z = ((spread - mu) / sd).rename("spread_z")
    return df, spread, spread_z


def run(input_csv: Path, output_json: Path) -> dict[str, Any]:
    df, _, spread_z = compute_spread_z(input_csv)
    q90 = spread_z.expanding().quantile(0.90)
    alert = (spread_z > q90).astype(bool)
    persistence = (
        alert
        & alert.shift(1, fill_value=False).astype(bool)
        & alert.shift(2, fill_value=False).astype(bool)
    )

    midr = df["mid_returns"].astype(float)
    events = midr[midr < -0.005]
    captured = 0
    for ts in events.index:
        loc = persistence.index.get_loc(ts)
        lo = max(0, loc - 20)
        hi = max(0, loc - 5)
        if hi > lo and persistence.iloc[lo:hi].any():
            captured += 1
    lead_capture = float(captured / len(events)) if len(events) else 0.0

    target = midr.shift(-1)
    ic = _scorr(spread_z, target)
    mom = midr.rolling(20).sum()
    vol = midr.rolling(10).std()
    cm, cv = _scorr(spread_z, mom), _scorr(spread_z, vol)

    verdict = {
        "IC": round(ic, 4),
        "corr_momentum": round(cm, 4),
        "corr_vol": round(cv, 4),
        "lead_capture": round(lead_capture, 4),
        "FINAL": (
            "SIGNAL_READY"
            if ic >= 0.08 and abs(cm) < 0.15 and abs(cv) < 0.15 and lead_capture >= 0.60
            else "REJECT"
        ),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument("--output-json", type=Path, default=Path("results/spread_stress_verdict.json"))
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
