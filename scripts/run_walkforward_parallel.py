"""Parallel walk-forward SABRE CAL evaluation."""

from __future__ import annotations

import argparse

import pandas as pd
import yaml
from joblib import Parallel, delayed

from neuropro.backtest import BacktesterCAL
from neuropro.data import read_ticks_csv


def _segment_run(
    df: pd.DataFrame,
    cfg: dict,
    feat_cols: list[str],
    y_col: str,
    start_idx: int,
    end_idx: int,
):
    fit_end = int(0.55 * start_idx)
    cal_end = start_idx
    X_fit = df[feat_cols].iloc[:fit_end]
    y_fit = df[y_col].iloc[:fit_end]
    X_cal = df[feat_cols].iloc[fit_end:cal_end]
    y_cal = df[y_col].iloc[fit_end:cal_end]
    bt = BacktesterCAL(cfg)
    bt.fit_quantiles(X_fit, y_fit)
    bt.calibrate_conformal(X_cal, y_cal)
    seg = df.iloc[start_idx:end_idx]
    if len(seg) < 2:
        return None
    return bt.run(seg, feat_cols, y_col, save_csv=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--n_jobs", type=int, default=2)
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config))
    base_cfg = yaml.safe_load(open(cfg.get("extends", "configs/demo.yaml")))
    base_cfg.update(cfg.get("overrides", {}))
    df = read_ticks_csv(base_cfg["data"]["path"], base_cfg["data"]["time_col"])
    feat_cols = ["ret1", "ret5", "ret20", "vol10", "vol50", "spread", "regime"]
    y_col = "y"

    n = len(df)
    start = int(cfg["walkforward"]["train_frac"] * n)
    step = max(1, int(cfg["walkforward"]["step_frac"] * n))
    jobs = []
    for s in range(start, n - 1, step):
        e = min(n, s + step)
        jobs.append((s, e))

    def _runner(s: int, e: int):
        local_cfg = dict(base_cfg)
        local_cfg["seed"] = int(base_cfg.get("seed", 7)) + int(s)
        return _segment_run(df, local_cfg, feat_cols, y_col, s, e)

    results = Parallel(n_jobs=args.n_jobs)(delayed(_runner)(s, e) for s, e in jobs)
    frames = [r for r in results if r is not None]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out.to_csv("wf_results.csv", index=False)
    print("Saved wf_results.csv | Segments:", len(frames))


if __name__ == "__main__":
    main()
