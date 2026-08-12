"""Task 16: train-frozen signal combiner for spread_z and kappa."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.kernels.ricci_on_spread import compute_ricci_features
from research.kernels.spread_stress_detector import compute_spread_z


def _scorr(a: pd.Series, b: pd.Series) -> float:
    df = pd.concat([a, b], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 0.0
    return float(spearmanr(df.iloc[:, 0], df.iloc[:, 1]).statistic)


def run(input_csv: Path, output_json: Path) -> dict[str, Any]:
    feat, kappa = compute_ricci_features(input_csv)
    _, _, spread_z = compute_spread_z(input_csv)
    target = feat["mid_r"].shift(-1)

    frame = pd.concat(
        [spread_z.rename("s"), kappa.rename("k"), target.rename("y")],
        axis=1,
        sort=False,
    ).dropna()
    split = int(0.7 * len(frame))
    tr, te = frame.iloc[:split], frame.iloc[split:]

    s_rank = tr["s"].rank(pct=True)
    k_rank = tr["k"].rank(pct=True)
    best_ic = -1e9
    best_w = (0.5, 0.5)
    for w1 in np.linspace(0, 1, 21):
        w2 = 1 - w1
        c = w1 * s_rank + w2 * k_rank
        ic = _scorr(c, tr["y"])
        if ic > best_ic:
            best_ic = ic
            best_w = (float(w1), float(w2))

    s_te = te["s"].rank(pct=True)
    k_te = te["k"].rank(pct=True)
    comb = best_w[0] * s_te + best_w[1] * k_te

    ic_comb = _scorr(comb, te["y"])
    ic_s = _scorr(s_te, te["y"])
    ic_k = _scorr(k_te, te["y"])
    mom = feat["mid_r"].rolling(20).sum().reindex(te.index)
    vol = feat["mid_r"].rolling(10).std().reindex(te.index)
    cm = _scorr(comb, mom)
    cv = _scorr(comb, vol)

    alerts = comb > comb.quantile(0.9)
    events = te["y"][te["y"] < -0.005]
    captured = int(alerts.reindex(events.index, fill_value=False).sum())
    lead_capture = float(captured / len(events)) if len(events) else 0.0

    verdict = {
        "weights": {"w1_spread": best_w[0], "w2_ricci": best_w[1]},
        "IC_combined": round(ic_comb, 4),
        "IC_spread": round(ic_s, 4),
        "IC_ricci": round(ic_k, 4),
        "corr_momentum": round(cm, 4),
        "corr_vol": round(cv, 4),
        "lead_capture": round(lead_capture, 4),
        "FINAL": "SIGNAL_READY" if ic_comb > max(ic_s, ic_k) and ic_comb >= 0.08 else "REJECT",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument("--output-json", type=Path, default=Path("results/signal_combiner_verdict.json"))
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
