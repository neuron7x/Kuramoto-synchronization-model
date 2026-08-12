"""Full GeoSync validation on Askar's L2 multi-asset panel.

Replicates the GeoSync baseline (IC=0.106, Sharpe=1.74) with institutional
L2 hourly data from OTS Capital, extends walk-forward through 2026-02,
runs FX-only and hourly-native variants, and produces a reproducible
metrics JSON + equity-curve plots.

Input panels (produced by :mod:`research.askar.panel_builder`):
    data/askar_full/panel_hourly.parquet   — aligned multi-asset hourly
    data/askar_full/panel_daily.parquet    — same universe, daily resample
    data/askar_full/panel_fx_hourly.parquet — 14 FX pairs, hourly
    data/askar_full/panel_manifest.json    — universe metadata

Output:
    results/askar_full_validation.json
    results/askar_full_daily_equity.png
    results/askar_full_hourly_equity.png
    results/askar_full_fx_equity.png

Run:
    python research/askar/full_validation.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.askar.ricci_spread import (
    forman_ricci_per_asset,
    permutation_test,
    quintile_position,
    z_score,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "askar_full"
RESULTS_DIR = REPO_ROOT / "results"

TARGET_EQUITY = "SPDR_S_P_500_ETF"
TARGET_FX = "EURUSD"

BASELINE_YFINANCE_IC = 0.106

# Baseline grid (matches original GeoSync baseline)
DAILY_WINDOW = 60
DAILY_THRESHOLD = 0.30
DAILY_COST_BPS = 5.0

HOURLY_WINDOW = 480  # 60 trading days × 8 hours
HOURLY_THRESHOLD = 0.30
HOURLY_COST_BPS = 1.0  # tighter hourly spreads on L2 data

FX_WINDOW = 120
FX_THRESHOLD = 0.30
FX_COST_BPS = 0.5

# Walk-forward split (matches the original GeoSync train/test cut)
TRAIN_END = pd.Timestamp("2023-07-01")
CRISIS_2022 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-01-01"))
EXT_OOS_2024 = (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01"))
EXT_OOS_2025 = (pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))

SENSITIVITY_THRESHOLDS = (0.20, 0.25, 0.30, 0.35, 0.40)
SENSITIVITY_WINDOWS_DAILY = (40, 60, 80)
SENSITIVITY_WINDOWS_HOURLY = (240, 360, 480)

N_PERMUTATIONS = 300
N_WALKFORWARD_FOLDS = 5


# -------------------------------------------------------------------- #
# Data plumbing
# -------------------------------------------------------------------- #


@dataclass
class Panels:
    hourly: pd.DataFrame
    daily: pd.DataFrame
    fx_hourly: pd.DataFrame
    manifest: dict[str, Any]


def load_panels(root: Path = DATA_DIR) -> Panels:
    manifest = json.loads((root / "panel_manifest.json").read_text())
    hourly = pd.read_parquet(root / "panel_hourly.parquet")
    daily = pd.read_parquet(root / "panel_daily.parquet")
    fx_hourly = pd.read_parquet(root / "panel_fx_hourly.parquet")
    hourly.index = pd.to_datetime(hourly.index)
    daily.index = pd.to_datetime(daily.index)
    fx_hourly.index = pd.to_datetime(fx_hourly.index)
    return Panels(
        hourly=hourly.sort_index(),
        daily=daily.sort_index(),
        fx_hourly=fx_hourly.sort_index(),
        manifest=manifest,
    )


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    ratio = prices / prices.shift(1)
    log_arr = np.log(ratio.to_numpy())
    return pd.DataFrame(log_arr, index=ratio.index, columns=ratio.columns).dropna()


# -------------------------------------------------------------------- #
# Signal construction
# -------------------------------------------------------------------- #


def build_signal(
    returns: pd.DataFrame,
    target: str,
    window: int,
    threshold: float,
) -> pd.DataFrame:
    """GeoSync signal on a multi-asset panel.

    combo = z(delta_Ricci, W) − 0.5 · z(Ricci_mean, W)

    where
        delta_Ricci(t) = ricci_target(t) − ricci_mean_over_all(t)
        Ricci_mean(t)  = mean per-asset Forman-Ricci at time t
    """
    if target not in returns.columns:
        raise KeyError(f"target {target!r} not in returns panel")

    rows: list[dict[str, float]] = []
    fwd_1 = returns[target]
    fwd_4 = returns[target].rolling(4).sum().shift(-3)

    for i in range(window, len(returns) - 1):
        w = returns.iloc[i - window : i]
        per_asset, mean_deg = forman_ricci_per_asset(w, threshold)
        ricci_t = per_asset.get(target, 0.0)
        ricci_mean = float(np.mean(list(per_asset.values())))
        rows.append(
            {
                "ricci_target": ricci_t,
                "ricci_mean": ricci_mean,
                "delta_ricci": ricci_t - ricci_mean,
                "mean_deg": mean_deg,
                "fwd_1": float(fwd_1.iloc[i]),
                "fwd_4": (
                    float(fwd_4.iloc[i])
                    if i < len(fwd_4) and np.isfinite(fwd_4.iloc[i])
                    else float("nan")
                ),
            }
        )
    df = pd.DataFrame(rows, index=returns.index[window : len(returns) - 1])
    df["z_delta"] = z_score(df["delta_ricci"], window)
    df["z_mean"] = z_score(df["ricci_mean"], window)
    df["combo"] = df["z_delta"] - 0.5 * df["z_mean"]
    df["baseline"] = -df["z_mean"]
    return df


# -------------------------------------------------------------------- #
# Backtest primitives
# -------------------------------------------------------------------- #


def sharpe(series: pd.Series, bars_per_year: float) -> float:
    s = series.dropna()
    if len(s) == 0 or s.std() == 0 or not np.isfinite(s.std()):
        return 0.0
    return float(s.mean() / s.std() * np.sqrt(bars_per_year))


def max_drawdown(series: pd.Series) -> float:
    if len(series) == 0:
        return 0.0
    cum = series.cumsum()
    return float((cum - cum.cummax()).min())


def strategy_returns(
    df_sig: pd.DataFrame,
    signal_col: str,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    positions = quintile_position(df_sig[signal_col])
    trades = positions.diff().abs().fillna(0.0)
    strat = positions.shift(1) * df_sig["fwd_1"] - trades * cost_bps / 10_000.0
    return positions, strat.fillna(0.0)


# -------------------------------------------------------------------- #
# Metrics
# -------------------------------------------------------------------- #


def _period_return(strat: pd.Series, lo: pd.Timestamp, hi: pd.Timestamp) -> float:
    window = strat[(strat.index >= lo) & (strat.index < hi)]
    if len(window) == 0:
        return float("nan")
    return float(window.sum())


def compute_orthogonality(
    combo: pd.Series,
    returns_target: pd.Series,
    window: int,
) -> dict[str, float]:
    """Correlate the signal against textbook factors built from target returns."""
    common = combo.index.intersection(returns_target.index)
    combo_a = combo.loc[common]
    ret_a = returns_target.loc[common]
    momentum = ret_a.rolling(window).sum()
    vol = ret_a.rolling(window).std()
    mr = -ret_a.rolling(max(5, window // 10)).sum()

    def _corr(a: pd.Series, b: pd.Series) -> float:
        mask = a.notna() & b.notna()
        if mask.sum() < 50:
            return float("nan")
        rho, _ = spearmanr(a[mask], b[mask])
        return float(rho)

    return {
        "corr_momentum": _corr(combo_a, momentum),
        "corr_vol": _corr(combo_a, vol),
        "corr_mean_reversion": _corr(combo_a, mr),
    }


def compute_block_metrics(
    df_sig: pd.DataFrame,
    split_ts: pd.Timestamp,
    cost_bps: float,
    bars_per_year: float,
    returns_target: pd.Series,
    window: int,
    permutations: int = N_PERMUTATIONS,
) -> dict[str, Any]:
    positions, strat = strategy_returns(df_sig, "combo", cost_bps)

    train_mask = df_sig.index < split_ts
    test_mask = df_sig.index >= split_ts

    train = df_sig[train_mask]
    test = df_sig[test_mask]
    train_strat = strat[train_mask]
    test_strat = strat[test_mask]

    def _ic(sig: pd.Series, y: pd.Series) -> float:
        mask = sig.notna() & y.notna()
        if mask.sum() < 50:
            return float("nan")
        rho, _ = spearmanr(sig[mask], y[mask])
        return float(rho)

    ic_train = _ic(train["combo"], train["fwd_1"])
    ic_test = _ic(test["combo"], test["fwd_1"])
    ic_baseline = _ic(test["baseline"], test["fwd_1"])
    ic_realised = _ic(positions[test_mask].shift(1), test["fwd_1"])

    sharpe_train = sharpe(train_strat, bars_per_year)
    sharpe_test = sharpe(test_strat, bars_per_year)
    maxdd_test = max_drawdown(test_strat)
    overfit_ratio = (
        round(float(sharpe_test / (sharpe_train + 1e-8)), 3) if sharpe_train != 0 else float("nan")
    )

    ic_perm, p_perm = permutation_test(test["combo"], test["fwd_1"], n=permutations, seed=42)

    return_2022 = _period_return(strat, *CRISIS_2022)
    return_spy_2022 = _period_return(returns_target, *CRISIS_2022)
    return_2024 = _period_return(strat, *EXT_OOS_2024)
    return_2025 = _period_return(strat, *EXT_OOS_2025)

    ortho = compute_orthogonality(df_sig["combo"], returns_target, window)

    return {
        "IC_raw_signal": round(float(ic_test), 4),
        "IC_realised": round(float(ic_realised), 4),
        "IC_train": round(float(ic_train), 4),
        "IC_baseline_no_delta": round(float(ic_baseline), 4),
        "sharpe_train": round(sharpe_train, 3),
        "sharpe_test": round(sharpe_test, 3),
        "maxdd_test": round(maxdd_test, 4),
        "overfit_ratio": overfit_ratio,
        "permutation_p": round(float(p_perm), 4),
        "permutation_ic": round(float(ic_perm), 4),
        "return_2022": round(return_2022, 4),
        "return_spy_2022": round(return_spy_2022, 4),
        "delta_2022": round(return_2022 - return_spy_2022, 4),
        "return_2024": round(return_2024, 4),
        "return_2025": round(return_2025, 4),
        "corr_momentum": round(ortho["corr_momentum"], 4),
        "corr_vol": round(ortho["corr_vol"], 4),
        "corr_mean_reversion": round(ortho["corr_mean_reversion"], 4),
        "baseline_yfinance_IC": BASELINE_YFINANCE_IC,
        "askar_IC_delta_vs_yfinance": round(float(ic_test) - BASELINE_YFINANCE_IC, 4),
        "n_train_bars": int(train_mask.sum()),
        "n_test_bars": int(test_mask.sum()),
        "_strat": strat,
    }


# -------------------------------------------------------------------- #
# Sensitivity & walk-forward
# -------------------------------------------------------------------- #


def run_sensitivity(
    returns: pd.DataFrame,
    target: str,
    thresholds: tuple[float, ...],
    windows: tuple[int, ...],
    split_ts: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Train-only sensitivity grid — IC computed on train slice only."""
    results: list[dict[str, Any]] = []
    for w in windows:
        for th in thresholds:
            try:
                sig = build_signal(returns, target, w, th)
            except ValueError:
                continue
            train = sig[sig.index < split_ts]
            mask = train["combo"].notna() & train["fwd_1"].notna()
            if mask.sum() < 50:
                continue
            rho, _ = spearmanr(train.loc[mask, "combo"], train.loc[mask, "fwd_1"])
            results.append({"window": w, "threshold": th, "IC_train": round(float(rho), 4)})
    return results


def run_walkforward_5fold(
    returns: pd.DataFrame,
    target: str,
    window: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Expanding-window walk-forward across 5 equal test blocks."""
    sig = build_signal(returns, target, window, threshold)
    n = len(sig)
    fold_size = n // (N_WALKFORWARD_FOLDS + 1)  # first fold reserved as warmup
    folds: list[dict[str, Any]] = []
    for k in range(N_WALKFORWARD_FOLDS):
        train_end = fold_size * (k + 1)
        test_start = train_end
        test_end = min(n, fold_size * (k + 2))
        if test_end - test_start < 20:
            continue
        train = sig.iloc[:train_end]
        test = sig.iloc[test_start:test_end]
        mask_tr = train["combo"].notna() & train["fwd_1"].notna()
        mask_te = test["combo"].notna() & test["fwd_1"].notna()
        if mask_te.sum() < 20:
            continue
        ic_tr, _ = spearmanr(train.loc[mask_tr, "combo"], train.loc[mask_tr, "fwd_1"])
        ic_te, _ = spearmanr(test.loc[mask_te, "combo"], test.loc[mask_te, "fwd_1"])
        positions = quintile_position(sig["combo"])
        strat = positions.shift(1) * sig["fwd_1"]
        strat = strat.fillna(0.0)
        test_strat = strat.iloc[test_start:test_end]
        folds.append(
            {
                "fold": k + 1,
                "train_end": str(train.index[-1]),
                "test_start": str(test.index[0]),
                "test_end": str(test.index[-1]),
                "IC_train": round(float(ic_tr), 4),
                "IC_test": round(float(ic_te), 4),
                "sharpe_test": round(sharpe(test_strat, 252.0), 3),
                "n_train": int(train_end),
                "n_test": int(test_end - test_start),
            }
        )
    return folds


# -------------------------------------------------------------------- #
# Plots
# -------------------------------------------------------------------- #


def plot_equity(
    runs: list[tuple[str, pd.Series]],
    title: str,
    out: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    for label, series in runs:
        cum = series.cumsum()
        ax.plot(
            cum.index,
            np.asarray(cum.to_numpy(), dtype=float),
            label=label,
            linewidth=1.2,
        )
    ax.axhline(0.0, color="black", lw=0.5)
    ax.set_title(title)
    ax.set_ylabel("cumulative log-return")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def run() -> dict[str, Any]:
    panels = load_panels()
    print(
        f"Universe: hourly={panels.hourly.shape}  "
        f"daily={panels.daily.shape}  fx={panels.fx_hourly.shape}"
    )

    returns_daily = log_returns(panels.daily)
    returns_hourly = log_returns(panels.hourly)
    returns_fx = log_returns(panels.fx_hourly)

    print(
        f"Returns: daily={returns_daily.shape}  "
        f"hourly={returns_hourly.shape}  fx={returns_fx.shape}"
    )

    # --- DAILY BASELINE (apples-to-apples with original GeoSync) ---
    print("[daily] building signal...")
    daily_sig = build_signal(returns_daily, TARGET_EQUITY, DAILY_WINDOW, DAILY_THRESHOLD)
    daily_metrics = compute_block_metrics(
        daily_sig,
        TRAIN_END,
        DAILY_COST_BPS,
        bars_per_year=252.0,
        returns_target=returns_daily[TARGET_EQUITY],
        window=DAILY_WINDOW,
    )
    print(
        f"[daily] IC_test={daily_metrics['IC_raw_signal']:.4f}  "
        f"Sharpe={daily_metrics['sharpe_test']:.3f}  "
        f"p={daily_metrics['permutation_p']:.3f}"
    )

    # --- HOURLY NATIVE ---
    print("[hourly] building signal (this takes a minute)...")
    hourly_sig = build_signal(returns_hourly, TARGET_EQUITY, HOURLY_WINDOW, HOURLY_THRESHOLD)
    hourly_metrics = compute_block_metrics(
        hourly_sig,
        TRAIN_END,
        HOURLY_COST_BPS,
        bars_per_year=252.0 * 8,
        returns_target=returns_hourly[TARGET_EQUITY],
        window=HOURLY_WINDOW,
    )
    print(
        f"[hourly] IC_test={hourly_metrics['IC_raw_signal']:.4f}  "
        f"Sharpe={hourly_metrics['sharpe_test']:.3f}  "
        f"p={hourly_metrics['permutation_p']:.3f}"
    )

    # --- FX-ONLY (EURUSD target) ---
    print("[fx] building signal...")
    fx_sig = build_signal(returns_fx, TARGET_FX, FX_WINDOW, FX_THRESHOLD)
    fx_metrics = compute_block_metrics(
        fx_sig,
        TRAIN_END,
        FX_COST_BPS,
        bars_per_year=252.0 * 24,
        returns_target=returns_fx[TARGET_FX],
        window=FX_WINDOW,
    )
    print(
        f"[fx] IC_test={fx_metrics['IC_raw_signal']:.4f}  "
        f"Sharpe={fx_metrics['sharpe_test']:.3f}  "
        f"p={fx_metrics['permutation_p']:.3f}"
    )

    # --- SENSITIVITY ---
    print("[sensitivity] daily grid...")
    sens_daily = run_sensitivity(
        returns_daily,
        TARGET_EQUITY,
        SENSITIVITY_THRESHOLDS,
        SENSITIVITY_WINDOWS_DAILY,
        TRAIN_END,
    )

    # --- WALK-FORWARD 5-FOLD ---
    print("[walkforward] daily 5-fold...")
    walkforward = run_walkforward_5fold(returns_daily, TARGET_EQUITY, DAILY_WINDOW, DAILY_THRESHOLD)

    # --- Verdict ---
    askar_ic = daily_metrics["IC_raw_signal"]
    perm_p = daily_metrics["permutation_p"]
    if askar_ic > BASELINE_YFINANCE_IC and perm_p < 0.05:
        verdict = "IMPROVEMENT"
    elif abs(askar_ic - BASELINE_YFINANCE_IC) < 0.02:
        verdict = "SAME"
    else:
        verdict = "DEGRADED"

    # --- Plots ---
    plot_equity(
        [
            (f"combo IC={daily_metrics['IC_raw_signal']:+.4f}", daily_metrics["_strat"]),
            ("SPY (hold)", returns_daily[TARGET_EQUITY].fillna(0.0)),
        ],
        "Askar daily — GeoSync baseline (test period)",
        RESULTS_DIR / "askar_full_daily_equity.png",
    )
    plot_equity(
        [
            (
                f"combo IC={hourly_metrics['IC_raw_signal']:+.4f}",
                hourly_metrics["_strat"],
            ),
            ("SPY hourly (hold)", returns_hourly[TARGET_EQUITY].fillna(0.0)),
        ],
        "Askar hourly native — GeoSync baseline (test period)",
        RESULTS_DIR / "askar_full_hourly_equity.png",
    )
    plot_equity(
        [
            (f"combo IC={fx_metrics['IC_raw_signal']:+.4f}", fx_metrics["_strat"]),
            ("EURUSD (hold)", returns_fx[TARGET_FX].fillna(0.0)),
        ],
        "Askar FX-only — EURUSD target",
        RESULTS_DIR / "askar_full_fx_equity.png",
    )

    # Strip non-serialisable series before JSON dump
    for m in (daily_metrics, hourly_metrics, fx_metrics):
        m.pop("_strat", None)

    report: dict[str, Any] = {
        "data_source": "OTS Capital L2 hourly — Askar",
        "universe_size": panels.manifest["panel_hourly"]["n_assets"],
        "universe_assets": panels.manifest["panel_hourly"]["assets"],
        "fx_universe_size": panels.manifest["panel_fx_hourly"]["n_assets"],
        "fx_universe_assets": panels.manifest["panel_fx_hourly"]["assets"],
        "period_train": f"{panels.manifest['panel_daily']['start'][:10]} -> {TRAIN_END.date()}",
        "period_test": f"{TRAIN_END.date()} -> {panels.manifest['panel_daily']['end'][:10]}",
        "target_equity": TARGET_EQUITY,
        "target_fx": TARGET_FX,
        "daily_resample": daily_metrics,
        "hourly_native": hourly_metrics,
        "fx_only": fx_metrics,
        "sensitivity_daily": sens_daily,
        "walkforward_5fold": walkforward,
        "verdict": verdict,
    }

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    out = RESULTS_DIR / "askar_full_validation.json"
    with out.open("w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps({k: v for k, v in report.items() if k != "universe_assets"}, indent=2))
    return report


if __name__ == "__main__":
    run()
