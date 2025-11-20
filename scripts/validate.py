"""Comprehensive validation pipeline for NeuroTrade PRO demos."""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
import yaml

from neuropro.backtest import BacktesterCAL
from neuropro.conformal import ConformalCQR
from neuropro.cv import purged_kfold
from neuropro.data import read_ticks_csv
from neuropro.evaluation import cvar, deflated_sharpe, max_drawdown, sharpe
from neuropro.execution import Execution
from neuropro.walkforward import walkforward


def summarize(res_df: pd.DataFrame, label: str) -> dict[str, float | int | str]:
    if len(res_df) == 0:
        return {
            "model": label,
            "sharpe": 0.0,
            "deflated_sharpe": 0.0,
            "cvar95": 0.0,
            "max_dd": 0.0,
            "trades": 0,
            "hit_rate": 0.0,
            "total_pnl": 0.0,
        }
    r = res_df["pnl"].values
    eq = res_df["eq"].values
    trades = int((res_df["pos"].diff() != 0).sum()) if "pos" in res_df else 0
    sr = float(sharpe(r))
    dsr = float(deflated_sharpe(sr, max(len(r), 2), trials=50))
    return {
        "model": label,
        "sharpe": sr,
        "deflated_sharpe": dsr,
        "cvar95": float(cvar(r, 0.95)),
        "max_dd": float(max_drawdown(eq)),
        "trades": trades,
        "hit_rate": float((r > 0).mean()),
        "total_pnl": float(r.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config))

    unit: dict[str, str] = {}
    try:
        ends = np.arange(200)
        folds = list(purged_kfold(ends, n_folds=5, embargo=10))
        assert len(folds) == 5
        for tr, te in folds:
            assert set(tr).isdisjoint(set(te))
        unit["purged_kfold"] = "PASS"
    except Exception as exc:
        unit["purged_kfold"] = f"FAIL: {exc}"

    try:
        cqr = ConformalCQR(alpha=0.1, decay=0.01, window=50)
        L = np.array([-0.01] * 100)
        U = np.array([0.01] * 100)
        y = np.concatenate([np.random.normal(0, 0.005, 95), np.array([0.05] * 5)])
        cqr.fit_calibrate(L, U, y)
        assert cqr.qhat >= 0.0
        unit["conformal_cqr"] = "PASS"
    except Exception as exc:
        unit["conformal_cqr"] = f"FAIL: {exc}"

    df = read_ticks_csv(cfg["data"]["path"], cfg["data"]["time_col"])
    feat = ["ret1", "ret5", "ret20", "vol10", "vol50", "spread", "regime"]
    y_col = "y"
    n = len(df)
    split = int(0.7 * n)
    fit_end = int(0.55 * split)
    X_fit = df[feat].iloc[:fit_end]
    y_fit = df[y_col].iloc[:fit_end]
    X_cal = df[feat].iloc[fit_end:split]
    y_cal = df[y_col].iloc[fit_end:split]
    test_df = df.iloc[split:].copy()

    bt = BacktesterCAL(cfg)
    bt.fit_quantiles(X_fit, y_fit)
    bt.calibrate_conformal(X_cal, y_cal)
    res = bt.run(test_df, feat, y_col, save_csv=None)

    y_true = test_df[y_col].iloc[: len(res)].values if len(res) > 0 else np.array([])
    L_hat = res["L"].values if len(res) > 0 else np.array([])
    U_hat = res["U"].values if len(res) > 0 else np.array([])
    coverage = (
        float(np.mean((y_true >= L_hat) & (y_true <= U_hat))) if len(res) > 0 else 0.0
    )
    coverage_info = {
        "empirical_coverage": coverage,
        "target_alpha0": cfg["conformal"]["alpha"],
    }
    assert (
        coverage >= 1.0 - cfg["conformal"]["alpha"] - 0.03
    ), "Coverage below expected tolerance"

    exec_sim = Execution(
        cfg["execution"]["fee_bps"],
        cfg["execution"]["impact_coeff"],
        cfg["execution"].get("impact_model", "square_root"),
    )
    pos = 0.0
    eq = 0.0
    eqs: list[float] = []
    pnls: list[float] = []
    for i in range(max(0, len(res) - 1)):
        mid = res["mid"].iloc[i]
        m_hat = res["M"].iloc[i]
        low_b = res["L"].iloc[i]
        high_b = res["U"].iloc[i]
        width = max(1e-9, high_b - low_b)
        target = (
            np.sign(m_hat) * min(1.0, abs(m_hat) / width) if abs(m_hat) > 0 else 0.0
        )
        costs = exec_sim.costs(res["spread"].iloc[i], test_df["vol10"].iloc[i])
        fill_p = exec_sim.fill(mid, res["spread"].iloc[i], target, pos)
        nxt = res["mid"].iloc[i + 1]
        pnl = (target - pos) * (nxt - fill_p) - abs(target - pos) * (costs * mid)
        pnls.append(pnl)
        pos = target
        eq += pnl
        eqs.append(eq)
    naive_res = pd.DataFrame({"pnl": pnls, "eq": eqs, "pos": np.nan})

    wf_cfg = yaml.safe_load(open("configs/wf.yaml"))
    base_cfg = yaml.safe_load(open(wf_cfg.get("extends", "configs/demo.yaml")))
    base_cfg.update(wf_cfg.get("overrides", {}))
    wf_df = read_ticks_csv(base_cfg["data"]["path"], base_cfg["data"]["time_col"])
    wf_res = walkforward(
        wf_df,
        base_cfg,
        feat,
        y_col,
        train_frac=wf_cfg["walkforward"]["train_frac"],
        step_frac=wf_cfg["walkforward"]["step_frac"],
    )

    summary = pd.DataFrame(
        [
            summarize(res, "CAL"),
            summarize(naive_res, "Naive"),
            summarize(wf_res, "CAL_WF"),
        ]
    )

    print("=== UNIT TESTS ===")
    print(json.dumps(unit, indent=2))
    print("\n=== COVERAGE ===")
    print(json.dumps(coverage_info, indent=2))
    print("\n=== SUMMARY ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
