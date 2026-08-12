"""Task 15: multi-horizon IC sweep for spread_z and kappa."""

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

HORIZONS = [1, 2, 4, 8, 12, 24, 48]


def _scorr(a: pd.Series, b: pd.Series) -> float:
    df = pd.concat([a, b], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 0.0
    return float(spearmanr(df.iloc[:, 0], df.iloc[:, 1]).statistic)


def _pval(a: pd.Series, b: pd.Series, n: int = 200, seed: int = 42) -> float:
    df = pd.concat([a, b], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 1.0
    x = df.iloc[:, 0].to_numpy()
    y = df.iloc[:, 1].to_numpy()
    obs = abs(float(spearmanr(x, y).statistic))
    rng = np.random.default_rng(seed)
    c = 0
    for _ in range(n):
        if abs(float(spearmanr(x, rng.permutation(y)).statistic)) >= obs:
            c += 1
    return float((c + 1) / (n + 1))


def run(input_csv: Path, output_json: Path) -> dict[str, Any]:
    feat, kappa = compute_ricci_features(input_csv)
    _, _, spread_z = compute_spread_z(input_csv)
    mid_r = feat["mid_r"]

    rows = []
    for h in HORIZONS:
        target = mid_r.rolling(h).sum().shift(-h)
        ic_s = _scorr(spread_z.reindex(target.index), target)
        ic_r = _scorr(kappa.reindex(target.index), target)
        p_s = _pval(spread_z.reindex(target.index), target)
        p_r = _pval(kappa.reindex(target.index), target)
        rows.append(
            {"horizon": h, "IC_spread": ic_s, "IC_ricci": ic_r, "p_spread": p_s, "p_ricci": p_r}
        )

    tbl = pd.DataFrame(rows)
    best_spread = tbl.iloc[tbl["IC_spread"].idxmax()]
    best_ricci = tbl.iloc[tbl["IC_ricci"].idxmax()]

    verdict = {
        "table": tbl.round(6).to_dict(orient="records"),
        "optimal_horizon_spread": int(best_spread["horizon"]),
        "optimal_horizon_ricci": int(best_ricci["horizon"]),
        "best_IC_spread": float(best_spread["IC_spread"]),
        "best_IC_ricci": float(best_ricci["IC_ricci"]),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument("--output-json", type=Path, default=Path("results/horizon_sweep_verdict.json"))
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
