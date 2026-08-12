# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Walk-forward evaluation utilities."""

from __future__ import annotations

import pandas as pd

from .backtest import BacktesterCAL


def walkforward(
    df: pd.DataFrame,
    cfg: dict,
    feat_cols: list[str],
    y_col: str,
    train_frac: float = 0.6,
    step_frac: float = 0.1,
) -> pd.DataFrame:
    n = len(df)
    step = max(1, int(step_frac * n))
    start = int(train_frac * n)
    results = []
    i = start
    while i < n - 100:
        tr_end = i
        cal_end = tr_end - max(100, int(0.15 * tr_end))
        X_fit = df[feat_cols].iloc[:cal_end]
        y_fit = df[y_col].iloc[:cal_end]
        X_cal = df[feat_cols].iloc[cal_end:tr_end]
        y_cal = df[y_col].iloc[cal_end:tr_end]
        bt = BacktesterCAL(cfg)
        bt.fit_quantiles(X_fit, y_fit)
        bt.calibrate_conformal(X_cal, y_cal)
        te_slice = df.iloc[tr_end : min(n, tr_end + step)]
        res = bt.run(te_slice, feat_cols, y_col, save_csv=None)
        if len(res) > 0:
            results.append(res)
        i += step
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()
