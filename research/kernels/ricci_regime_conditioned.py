"""Task 14: regime-conditioned Ricci IC."""

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


def _pval(a: pd.Series, b: pd.Series, n: int = 500, seed: int = 42) -> float:
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

    target = feat["mid_r"].shift(-1)
    z = spread_z.reindex(kappa.index)
    q90 = z.quantile(0.9)
    stress_mask = (z > q90).reindex(kappa.index).fillna(False).astype(bool)

    ic_stress = _scorr(kappa.loc[stress_mask], target.reindex(kappa.index).loc[stress_mask])
    ic_normal = _scorr(kappa.loc[~stress_mask], target.reindex(kappa.index).loc[~stress_mask])
    p_stress = _pval(kappa.loc[stress_mask], target.reindex(kappa.index).loc[stress_mask])
    p_normal = _pval(kappa.loc[~stress_mask], target.reindex(kappa.index).loc[~stress_mask])
    lift = ic_stress - ic_normal

    verdict = {
        "IC_stress": round(ic_stress, 4),
        "IC_normal": round(ic_normal, 4),
        "p_stress": round(p_stress, 4),
        "p_normal": round(p_normal, 4),
        "regime_lift": round(lift, 4),
        "FINAL": "REGIME_EFFECT" if lift > 0.05 else "REJECT",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument("--output-json", type=Path, default=Path("results/ricci_regime_verdict.json"))
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
