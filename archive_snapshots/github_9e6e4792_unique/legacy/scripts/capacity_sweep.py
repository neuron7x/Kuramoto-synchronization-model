import argparse

import pandas as pd
import yaml

from neuropro.backtest import BacktesterCAL
from neuropro.data import read_ticks_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--impact_coeffs", default="0.2,0.5,0.8,1.2")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as fh:
        base = yaml.safe_load(fh)
    df = read_ticks_csv(base["data"]["path"], base["data"]["time_col"])
    feat_cols = ["ret1", "ret5", "ret20", "vol10", "vol50", "spread", "regime"]
    y_col = "y"
    n = len(df)
    split = int(0.7 * n)
    fit_end = int(0.55 * split)
    X_fit = df[feat_cols].iloc[:fit_end]
    y_fit = df[y_col].iloc[:fit_end]
    X_cal = df[feat_cols].iloc[fit_end:split]
    y_cal = df[y_col].iloc[fit_end:split]

    rows = []
    for coeff in [float(x) for x in args.impact_coeffs.split(",") if x.strip()]:
        cfg = dict(base)
        cfg["execution"] = dict(base["execution"])
        cfg["execution"]["impact_coeff"] = coeff
        bt = BacktesterCAL(cfg)
        bt.fit_quantiles(X_fit, y_fit)
        bt.calibrate_conformal(X_cal, y_cal)
        res = bt.run(df.iloc[split:], feat_cols, y_col)
        pnl = res["pnl"].sum() if len(res) > 0 else 0.0
        rows.append({"impact_coeff": coeff, "rows": len(res), "total_pnl": pnl})

    pd.DataFrame(rows).to_csv("capacity_sweep.csv", index=False)
    print("Saved capacity_sweep.csv")


if __name__ == "__main__":
    main()
