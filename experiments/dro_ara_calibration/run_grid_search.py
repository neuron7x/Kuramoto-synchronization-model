# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Walk-forward H × rs threshold grid search for DRO-ARA v7.

Contract:
* Hurst is computed on the *train* window only (no leakage).
* rs is derived from H via INV-DRO1/INV-DRO2: rs = max(0, 1 − |2H|).
* Gate is static per (fold, grid-point): if ``H_train < H_threshold`` AND
  ``rs_train >= rs_threshold`` → gate ON for the test window, else gate OFF.
* combo_v1 signal (AMMComboStrategy) is generated per fold and cached; the
  gate masks entries (multiplies signal by {0, 1}).
* Backtest: ``vectorized_backtest`` (O(n), documented entry point for rapid
  parameter optimisation and walk-forward analysis — see backtest/event_driven.py).
* Rejection filters (post-fold aggregation):
    - mean OOS Sharpe < 0.80 → reject
    - any fold drawdown > 0.25 → reject
    - mean n_trades < 20 → reject
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from numpy.typing import NDArray

from backtest.event_driven import vectorized_backtest
from backtest.strategies.amm_combo import AMMComboStrategy, AMMStrategyConfig
from core.dro_ara.engine import (
    H_CRITICAL,
    RS_LONG_THRESH,
    _adf_stationary,
    _hurst_dfa,
    derive_gamma,
    risk_scalar,
)

TRAIN_WINDOW: Final[int] = 252
TEST_WINDOW: Final[int] = 63
STEP: Final[int] = 21
MIN_HISTORY: Final[int] = 504

H_GRID: Final[NDArray[np.float64]] = np.round(np.arange(0.30, 0.65, 0.05), 2)
RS_GRID: Final[NDArray[np.float64]] = np.round(np.arange(0.10, 0.65, 0.05), 2)

DEFAULT_DATA: Final[Path] = Path("data/askar/SPDR_S_P_500_ETF_GMT_0_NO-DST.parquet")
RESULTS_DIR: Final[Path] = Path("experiments/dro_ara_calibration/results")
DOCS_DIR: Final[Path] = Path("docs")
FEE: Final[float] = 0.0005

CRISIS_START: Final[pd.Timestamp] = pd.Timestamp("2022-01-01")
CRISIS_END: Final[pd.Timestamp] = pd.Timestamp("2022-12-31")


@dataclass(frozen=True)
class FoldBundle:
    """Per-fold cached artefacts invariant across the (H, rs) grid."""

    fold_id: int
    fold_start: pd.Timestamp
    H_train: float
    rs_train: float
    stationary_train: bool
    combo_signal: NDArray[np.float64]
    test_prices: NDArray[np.float64]


def load_daily_close(path: Path) -> pd.DataFrame:
    """Load parquet and downsample hourly OHLC to daily close."""

    df = pd.read_parquet(path)
    if "ts" not in df.columns or "close" not in df.columns:
        raise ValueError(f"{path} missing expected 'ts'/'close' columns")
    df = df[["ts", "close"]].copy()
    df["ts"] = pd.to_datetime(df["ts"])
    daily = (
        df.set_index("ts")["close"].resample("1D").last().dropna().to_frame("close").reset_index()
    )
    return daily


def build_fold_starts(n: int) -> list[int]:
    first = MIN_HISTORY
    starts: list[int] = []
    t = first
    while t + TRAIN_WINDOW + TEST_WINDOW <= n:
        starts.append(t)
        t += STEP
    return starts


def combo_v1_signal(prices: NDArray[np.float64]) -> NDArray[np.float64]:
    """Run AMMComboStrategy over ``prices`` → {-1, 0, +1} position array.

    combo_v1 is treated as read-only: we only *consume* its ``on_step`` output,
    never mutate its logic. Constant ``R=0.6``, ``kappa=0.1`` match the
    canonical unit-test wiring (tests/strategies/test_amm_combo.py).
    """
    cfg = AMMStrategyConfig()
    strat = AMMComboStrategy(cfg)
    n = len(prices)
    signals = np.zeros(n, dtype=np.float64)
    position = 0
    log_ret = np.zeros(n, dtype=np.float64)
    log_ret[1:] = np.diff(np.log(np.maximum(prices, 1e-12)))
    for i in range(n):
        out = strat.on_step(float(log_ret[i]), 0.6, 0.1, None)
        action = out["action"]
        if action == "ENTER_LONG":
            position = 1
        elif action == "ENTER_SHORT":
            position = -1
        elif action == "EXIT_ALL":
            position = 0
        signals[i] = float(position)
    return signals


def hurst_on_train(train_prices: NDArray[np.float64]) -> tuple[float, float, bool]:
    """DFA-1 Hurst + ADF stationarity on train window only.

    Mirrors State.from_window semantics (PR #349): ADF runs on log-returns,
    not raw prices, to match the DFA transform.
    """

    log_returns = np.diff(np.log(np.abs(train_prices) + 1e-12))
    stat = _adf_stationary(log_returns)
    H, r2 = _hurst_dfa(train_prices)
    _, _, _ = derive_gamma(train_prices)  # invariant self-check path
    return float(H), float(r2), bool(stat)


def compute_fold(
    fold_id: int,
    fold_start: pd.Timestamp,
    train_prices: NDArray[np.float64],
    test_prices: NDArray[np.float64],
) -> FoldBundle:
    H_train, _, stationary = hurst_on_train(train_prices)
    gamma_train = 2.0 * H_train + 1.0
    rs_train = risk_scalar(gamma_train)
    combo_signal = combo_v1_signal(test_prices)
    return FoldBundle(
        fold_id=fold_id,
        fold_start=fold_start,
        H_train=float(H_train),
        rs_train=float(rs_train),
        stationary_train=bool(stationary),
        combo_signal=combo_signal,
        test_prices=test_prices,
    )


def ic_spearman(signal: NDArray[np.float64], prices: NDArray[np.float64]) -> float:
    """Rank-IC between t-signal and t→t+1 return."""

    if len(signal) < 3:
        return 0.0
    rets = np.zeros_like(prices)
    rets[1:] = (prices[1:] - prices[:-1]) / np.maximum(prices[:-1], 1e-12)
    # Align: position at t uses signal at t-1 (same as vectorized_backtest shift).
    sig = signal[:-1]
    fwd = rets[1:]
    if np.std(sig) < 1e-12 or np.std(fwd) < 1e-12:
        return 0.0
    sr = pd.Series(sig).rank().to_numpy()
    fr = pd.Series(fwd).rank().to_numpy()
    sr = sr - sr.mean()
    fr = fr - fr.mean()
    denom = float(np.sqrt((sr @ sr) * (fr @ fr)))
    if denom < 1e-12:
        return 0.0
    return float((sr @ fr) / denom)


def eval_grid_cell(bundle: FoldBundle, H_threshold: float, rs_threshold: float) -> dict[str, Any]:
    gate_on = (
        bundle.stationary_train and bundle.H_train < H_threshold and bundle.rs_train >= rs_threshold
    )
    signal = bundle.combo_signal * (1.0 if gate_on else 0.0)
    bt = vectorized_backtest(bundle.test_prices, signal, fee_per_trade=FEE)

    equity = np.asarray(bt["equity_curve"], dtype=np.float64)
    if equity.size > 1:
        base = equity[0] if abs(equity[0]) > 1e-12 else 1.0
        peaks = np.maximum.accumulate(equity)
        dd_series = (equity - peaks) / np.maximum(np.abs(peaks) + abs(base), 1e-12)
        max_dd_pct = float(-np.min(dd_series))
    else:
        max_dd_pct = 0.0

    return {
        "fold_id": bundle.fold_id,
        "fold_start": bundle.fold_start.strftime("%Y-%m-%d"),
        "H": float(H_threshold),
        "rs": float(rs_threshold),
        "H_train": bundle.H_train,
        "rs_train": bundle.rs_train,
        "gate_on": bool(gate_on),
        "sharpe_oos": float(bt["sharpe"]),
        "max_drawdown": max_dd_pct,
        "ic": ic_spearman(signal, bundle.test_prices),
        "n_trades": int(bt["trades"]),
        "pnl": float(bt["pnl"]),
    }


def build_fold_bundles(prices: NDArray[np.float64], timestamps: pd.Series) -> list[FoldBundle]:
    starts = build_fold_starts(len(prices))
    if not starts:
        raise RuntimeError(
            f"Insufficient history: need ≥ {MIN_HISTORY + TRAIN_WINDOW + TEST_WINDOW} "
            f"daily bars, got {len(prices)}"
        )

    payloads: list[tuple[int, pd.Timestamp, NDArray[np.float64], NDArray[np.float64]]] = []
    for fid, s in enumerate(starts):
        train = prices[s - TRAIN_WINDOW : s]
        test = prices[s : s + TEST_WINDOW]
        payloads.append((fid, timestamps.iloc[s], train, test))

    bundles: list[FoldBundle] = Parallel(n_jobs=-1, prefer="processes")(
        delayed(compute_fold)(fid, ts, train, test) for fid, ts, train, test in payloads
    )
    return bundles


def evaluate_all(
    bundles: list[FoldBundle],
) -> pd.DataFrame:
    tasks = [(b, float(H), float(rs)) for b in bundles for H in H_GRID for rs in RS_GRID]
    rows: list[dict[str, Any]] = Parallel(n_jobs=-1, prefer="processes")(
        delayed(eval_grid_cell)(b, H, rs) for (b, H, rs) in tasks
    )
    return pd.DataFrame(rows)


def apply_filters(
    grid_df: pd.DataFrame,
) -> pd.DataFrame:
    agg = (
        grid_df.groupby(["H", "rs"])
        .agg(
            mean_sharpe=("sharpe_oos", "mean"),
            std_sharpe=("sharpe_oos", "std"),
            worst_fold_sharpe=("sharpe_oos", "min"),
            worst_drawdown=("max_drawdown", "max"),
            mean_trades=("n_trades", "mean"),
            gate_on_folds=("gate_on", "sum"),
        )
        .reset_index()
    )
    agg["passes_filters"] = (
        (agg["mean_sharpe"] >= 0.80)
        & (agg["worst_drawdown"] <= 0.25)
        & (agg["mean_trades"] >= 20.0)
    )
    return agg


def isolate_crisis(grid_df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(grid_df["fold_start"])
    mask = (ts >= CRISIS_START) & (ts <= CRISIS_END)
    crisis = grid_df.loc[mask].copy()
    if crisis.empty:
        return crisis
    return (
        crisis.groupby(["H", "rs"])
        .agg(
            crisis_mean_sharpe=("sharpe_oos", "mean"),
            crisis_worst_dd=("max_drawdown", "max"),
            crisis_folds=("fold_id", "nunique"),
        )
        .reset_index()
    )


def plot_heatmap(agg: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    pivot = agg.pivot(index="H", columns="rs", values="mean_sharpe").sort_index(ascending=False)

    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".2f",
        cmap="RdBu_r",
        center=0.0,
        cbar_kws={"label": "mean OOS Sharpe"},
        ax=ax,
    )

    rs_values = [round(float(v), 2) for v in pivot.columns]
    H_values = [round(float(v), 2) for v in pivot.index]
    rs_target = round(float(RS_LONG_THRESH), 2)
    H_target = round(float(H_CRITICAL), 2)
    if rs_target in rs_values and H_target in H_values:
        col = rs_values.index(rs_target)
        row = H_values.index(H_target)
        ax.plot(col + 0.5, row + 0.5, marker="x", color="red", markersize=18, mew=3)

    ax.set_title("DRO-ARA OOS Sharpe · Walk-Forward Grid Search")
    ax.set_xlabel("rs_threshold")
    ax.set_ylabel("H_threshold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def write_report(
    summary: dict[str, Any],
    agg: pd.DataFrame,
    crisis_agg: pd.DataFrame,
    meta: dict[str, Any],
    out_path: Path,
) -> None:
    # Rank: prefer cells with ≥ 1 active fold; fall back to fully-degenerate
    # cells only when the grid is uniformly inactive. Without this filter, a
    # 0-Sharpe-because-0-folds cell would outrank a (-0.01)-Sharpe cell that
    # actually executed trades — misleading for calibration.
    active = agg[agg["gate_on_folds"] > 0]
    ranked = (active if len(active) else agg).sort_values(
        ["mean_sharpe", "gate_on_folds"], ascending=[False, False]
    )
    top5 = ranked.head(5)
    opt = top5.iloc[0]
    H_opt = float(opt["H"])
    rs_opt = float(opt["rs"])
    delta_H = abs(H_opt - H_CRITICAL)
    delta_rs = abs(rs_opt - RS_LONG_THRESH)

    lines: list[str] = []
    lines.append("# DRO-ARA v7 · Walk-Forward Calibration Report\n")
    lines.append("## Header\n")
    lines.append(f"- data_source: `{meta['data_source']}`")
    lines.append(f"- date_range: {meta['date_range']}")
    lines.append(f"- n_daily_bars: {meta['n_bars']}")
    lines.append(f"- n_folds: {meta['n_folds']}")
    lines.append(f"- grid_size: {len(H_GRID)} × {len(RS_GRID)} = {len(H_GRID) * len(RS_GRID)}")
    lines.append(
        f"- train_window={TRAIN_WINDOW}, test_window={TEST_WINDOW}, "
        f"step={STEP}, min_history={MIN_HISTORY}"
    )
    lines.append("")
    lines.append("## Current vs Optimal\n")
    lines.append("| param | current | optimal | delta |")
    lines.append("|-------|---------|---------|-------|")
    lines.append(f"| H_threshold (H_CRITICAL) | {H_CRITICAL:.2f} | {H_opt:.2f} | {delta_H:+.2f} |")
    lines.append(
        f"| rs_threshold (RS_LONG_THRESH) | {RS_LONG_THRESH:.2f} | {rs_opt:.2f} | {delta_rs:+.2f} |"
    )
    lines.append("")
    lines.append("## Top-5 Pairs (by mean OOS Sharpe)\n")
    lines.append(
        "| rank | H | rs | mean_sharpe | std_sharpe | worst_fold_sharpe | worst_dd | mean_trades | passes_filters |"
    )
    lines.append(
        "|------|----|----|-------------|------------|--------------------|----------|-------------|----------------|"
    )
    for i, row in enumerate(top5.itertuples(index=False), 1):
        lines.append(
            f"| {i} | {row.H:.2f} | {row.rs:.2f} | {row.mean_sharpe:.3f} | "
            f"{row.std_sharpe:.3f} | {row.worst_fold_sharpe:.3f} | "
            f"{row.worst_drawdown:.3f} | {row.mean_trades:.1f} | {row.passes_filters} |"
        )
    lines.append("")
    lines.append("## Robustness\n")
    lines.append(
        f"- Top pair (H={H_opt:.2f}, rs={rs_opt:.2f}): "
        f"mean_sharpe={opt['mean_sharpe']:.3f}, "
        f"std_sharpe={opt['std_sharpe']:.3f}, "
        f"worst_fold_sharpe={opt['worst_fold_sharpe']:.3f}, "
        f"worst_dd={opt['worst_drawdown']:.3f}, "
        f"mean_trades={opt['mean_trades']:.1f}, "
        f"gate_on_folds={int(opt['gate_on_folds'])}"
    )
    lines.append("")
    lines.append("## Crisis Window (2022)\n")
    if crisis_agg.empty:
        lines.append("_No test fold overlapped calendar year 2022._")
    else:
        crisis_top = crisis_agg.sort_values("crisis_mean_sharpe", ascending=False).head(5)
        lines.append("| H | rs | crisis_mean_sharpe | crisis_worst_dd | crisis_folds |")
        lines.append("|----|----|--------------------|-----------------|--------------|")
        for _, crisis_row in crisis_top.iterrows():
            lines.append(
                f"| {float(crisis_row['H']):.2f} | {float(crisis_row['rs']):.2f} | "
                f"{float(crisis_row['crisis_mean_sharpe']):.3f} | "
                f"{float(crisis_row['crisis_worst_dd']):.3f} | "
                f"{int(crisis_row['crisis_folds'])} |"
            )
    lines.append("")
    lines.append("## Recommendation\n")
    active_cells = agg[agg["gate_on_folds"] > 0]
    total_active = len(active_cells)
    max_mean_sharpe = float(active_cells["mean_sharpe"].max()) if total_active else 0.0
    top_passes = bool(opt["passes_filters"])
    if total_active == 0:
        verdict = (
            "**NO_ACTIVITY / REJECT** — across the entire H × rs grid, no "
            "(H_threshold, rs_threshold) pair produced any gate-on fold. "
            "The combo_v1 × DRO-ARA composition does not activate on this "
            "asset over the tested window. No threshold change justified."
        )
    elif max_mean_sharpe <= 0.0:
        verdict = (
            f"**STRATEGY_UNPROFITABLE / REJECT** — {total_active} (H, rs) "
            f"pairs activated the gate, but the best mean OOS Sharpe across "
            f"all active cells is {max_mean_sharpe:.3f} (≤ 0). The "
            f"combo_v1 × DRO-ARA pipeline does not produce a profitable edge "
            f"on this asset at this bar granularity. Threshold tuning cannot "
            f"fix a non-existent signal. Operator action: DO NOT modify "
            f"engine constants. Consider: (a) higher-frequency data, "
            f"(b) richer R/κ feature proxies than constants, or "
            f"(c) a different asset class for combo_v1 deployment."
        )
    elif delta_H > 0.20 or delta_rs > 0.30:
        verdict = (
            f"**HALT / ESCALATE RE-SPECIFICATION** — deltas "
            f"(ΔH={delta_H:.2f}, Δrs={delta_rs:.2f}) exceed safety bounds "
            f"(0.20 / 0.30). This is an engine-design mismatch, not a "
            f"parameter tune. Do not modify engine.py."
        )
    elif delta_H > 0.10 or delta_rs > 0.10:
        verdict = (
            f"**HALT / AWAIT OPERATOR** — deltas (ΔH={delta_H:.2f}, "
            f"Δrs={delta_rs:.2f}) exceed 0.10 threshold on ≥1 axis. "
            f"Report captured; no engine changes applied."
        )
    elif not top_passes:
        verdict = (
            "**REJECT** — top pair fails rejection filters "
            "(Sharpe ≥ 0.80, worst_dd ≤ 0.25, mean_trades ≥ 20)."
        )
    else:
        verdict = (
            "**ADOPT** — optimal within ±0.10 of current and passes all "
            "rejection filters. Safe to apply as a minor calibration."
        )
    lines.append(verdict)
    lines.append("")
    lines.append(
        f"Notes: Hurst computed exclusively on train windows (no leakage). "
        f"Signal = combo_v1 (AMMComboStrategy) position × DRO-ARA gate. "
        f"Gate logic = INV-DRO4 under grid-swept thresholds. "
        f"Backtest = vectorized_backtest(fee={FEE}, signal shift=1 anti-lookahead)."
    )
    out_path.write_text("\n".join(lines) + "\n")


def main(data_path: Path = DEFAULT_DATA) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    daily = load_daily_close(data_path)
    prices = daily["close"].to_numpy(dtype=np.float64)
    timestamps = daily["ts"]

    if len(prices) < MIN_HISTORY + TRAIN_WINDOW + TEST_WINDOW:
        raise RuntimeError(
            f"Data too short: {len(prices)} daily bars < required "
            f"{MIN_HISTORY + TRAIN_WINDOW + TEST_WINDOW}."
        )

    date_range = f"{timestamps.iloc[0].date()} → {timestamps.iloc[-1].date()}"
    bundles = build_fold_bundles(prices, timestamps)

    grid_df = evaluate_all(bundles)
    grid_df = grid_df[
        ["H", "rs", "fold_id", "fold_start", "sharpe_oos", "max_drawdown", "ic", "n_trades"]
        + ["gate_on", "H_train", "rs_train", "pnl"]
    ]
    grid_csv = RESULTS_DIR / "dro_ara_grid_search.csv"
    grid_df.to_csv(grid_csv, index=False)

    agg = apply_filters(grid_df)
    active = agg[agg["gate_on_folds"] > 0]
    ranked = (active if len(active) else agg).sort_values(
        ["mean_sharpe", "gate_on_folds"], ascending=[False, False]
    )
    top5 = ranked.head(5)
    summary = {
        "top5": top5.to_dict(orient="records"),
        "current": {"H": H_CRITICAL, "rs": RS_LONG_THRESH},
        "optimal": {
            "H": float(top5.iloc[0]["H"]),
            "rs": float(top5.iloc[0]["rs"]),
            "mean_sharpe": float(top5.iloc[0]["mean_sharpe"]),
            "std_sharpe": float(top5.iloc[0]["std_sharpe"]),
            "worst_fold_sharpe": float(top5.iloc[0]["worst_fold_sharpe"]),
            "passes_filters": bool(top5.iloc[0]["passes_filters"]),
        },
    }
    (RESULTS_DIR / "dro_ara_summary.json").write_text(json.dumps(summary, indent=2, default=float))

    plot_heatmap(agg, RESULTS_DIR / "dro_ara_heatmap.png")

    crisis_agg = isolate_crisis(grid_df)
    meta = {
        "data_source": str(data_path),
        "date_range": date_range,
        "n_bars": int(len(prices)),
        "n_folds": int(grid_df["fold_id"].nunique()),
    }
    write_report(summary, agg, crisis_agg, meta, DOCS_DIR / "DRO_ARA_CALIBRATION_REPORT.md")
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help="Parquet file with 'ts'/'close' columns (default: SPDR S&P 500).",
    )
    ns = parser.parse_args()
    s = main(ns.data)
    print(json.dumps(s, indent=2, default=float))
