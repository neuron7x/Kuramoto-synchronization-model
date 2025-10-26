"""Run a NeuroTrade PRO SABRE CAL backtest."""

from __future__ import annotations

import argparse

import yaml

from neuropro.backtest import BacktesterCAL
from neuropro.data import read_ticks_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config))
    df = read_ticks_csv(cfg["data"]["path"], cfg["data"]["time_col"])
    feat_cols = ["ret1", "ret5", "ret20", "vol10", "vol50", "spread", "regime"]
    y_col = "y"
    n = len(df)
    split = int(0.7 * n)
    fit_end = int(0.55 * split)
    X_fit = df[feat_cols].iloc[:fit_end]
    y_fit = df[y_col].iloc[:fit_end]
    X_cal = df[feat_cols].iloc[fit_end:split]
    y_cal = df[y_col].iloc[fit_end:split]
    bt = BacktesterCAL(cfg)
    bt.fit_quantiles(X_fit, y_fit)
    bt.calibrate_conformal(X_cal, y_cal)
    res = bt.run(df.iloc[split:], feat_cols, y_col, save_csv="backtest_results.csv")
    print("Saved backtest_results.csv | Rows:", len(res))


if __name__ == "__main__":
    main()
