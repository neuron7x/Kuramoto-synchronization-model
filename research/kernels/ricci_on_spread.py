"""Task 11: Ricci on bid/ask spread microstructure graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from core.physics.forman_ricci import FormanRicciCurvature

_RUN_RESULT_T = dict[str, Any]


def _scorr(a: pd.Series, b: pd.Series) -> float:
    df = pd.concat([a, b], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 0.0
    return float(spearmanr(df.iloc[:, 0], df.iloc[:, 1]).statistic)


def _perm_pvalue(x: pd.Series, y: pd.Series, n: int = 500, seed: int = 42) -> float:
    df = pd.concat([x, y], axis=1, sort=False).dropna()
    if len(df) < 30:
        return 1.0
    xv = df.iloc[:, 0].to_numpy()
    yv = df.iloc[:, 1].to_numpy()
    obs = abs(float(spearmanr(xv, yv).statistic))
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n):
        c = abs(float(spearmanr(xv, rng.permutation(yv)).statistic))
        if c >= obs:
            count += 1
    return float((count + 1) / (n + 1))


def compute_ricci_features(
    input_csv: Path, window: int = 60, threshold: float = 0.30
) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(input_csv)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").set_index("ts")

    spread = (df["ask_close"] - df["bid_close"]).rename("spread")
    feat = (
        pd.DataFrame(
            {
                "bid_r": np.log(df["bid_close"] / df["bid_close"].shift(1)),
                "ask_r": np.log(df["ask_close"] / df["ask_close"].shift(1)),
                "spread": spread,
                "mid_r": df["mid_returns"],
                "dspread": spread.diff(),
            }
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    ricci = FormanRicciCurvature(threshold=threshold)
    vals = feat.to_numpy(dtype=float)
    kappa = pd.Series(np.nan, index=feat.index)
    for t in range(window - 1, len(feat)):
        w = vals[t - window + 1 : t + 1]
        corr = np.nan_to_num(np.corrcoef(w, rowvar=False), nan=0.0)
        kappa.iloc[t] = ricci.compute_from_correlation(corr).kappa_mean
    kappa = kappa.dropna().rename("kappa")

    return feat, kappa


def run(
    input_csv: Path,
    output_json: Path,
    window: int = 60,
    threshold: float = 0.30,
) -> _RUN_RESULT_T:
    feat, kappa = compute_ricci_features(input_csv, window=window, threshold=threshold)
    target = feat["mid_r"].shift(-1)
    ic = _scorr(kappa, target)
    p = _perm_pvalue(kappa, target)
    mom = feat["mid_r"].rolling(20).sum()
    vol = feat["mid_r"].rolling(10).std()
    cm = _scorr(kappa, mom)
    cv = _scorr(kappa, vol)

    verdict = {
        "IC": round(ic, 4),
        "p_value": round(p, 4),
        "corr_momentum": round(cm, 4),
        "corr_vol": round(cv, 4),
        "FINAL": "BREAKTHROUGH" if ic >= 0.08 else "REJECT",
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument("--output-json", type=Path, default=Path("results/ricci_on_spread_verdict.json"))
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
