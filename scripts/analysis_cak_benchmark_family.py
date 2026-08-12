"""Phase 4 · Benchmark family expansion.

All benchmarks share:
  - the same execution lag (1 bar) as the frozen Kuramoto strategy, and
  - the same nonzero cost model (`cost_bps * |Δw| / 10_000`) —
unless a benchmark is pure buy-and-hold by construction, in which case
turnover is zero by definition and cost is zero; this exception is
flagged explicitly in the CSV (`cost_model` column).

No parameter search. No lookback search. All BF parameters fixed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]

from core.cross_asset_kuramoto import (  # noqa: E402
    build_panel,
    build_returns_panel,
    classify_regimes,
    compute_log_returns,
    compute_metrics,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.invariants import load_parameter_lock  # noqa: E402

LOCK = REPO / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
OUT_DIR = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"
PARAMS = load_parameter_lock(LOCK)

MOMENTUM_LOOKBACK = 20  # fixed
LAG = PARAMS.execution_lag_bars
CLIP = PARAMS.return_clip_abs
BPY = PARAMS.bars_per_year
COST_BPS = PARAMS.cost_bps


def _apply_costs(
    weights: pd.DataFrame, rets: pd.DataFrame, cost_bps: float
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Apply execution_lag_bars shift + cost on |Δw| turnover.

    Returns (net_ret, gross_ret, turnover)."""
    r_clip = rets.clip(lower=-CLIP, upper=CLIP)
    W_shift = weights.shift(LAG).fillna(0.0)
    gross = (W_shift * r_clip).sum(axis=1)
    turnover = W_shift.diff().fillna(W_shift).abs().sum(axis=1)
    cost = turnover * (cost_bps / 10_000.0)
    net = gross - cost
    return net, gross, turnover


def _sharpe(series: pd.Series) -> float:
    r = series.dropna().to_numpy()
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    if sd <= 0:
        return 0.0
    return float(r.mean() / sd * np.sqrt(BPY))


def _equal_weight_buy_hold(rets: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """BF1: daily rebalance to 1/N equal-weight long-only.

    Pure buy-and-hold-by-construction: the weights are constant 1/N
    between rebalances. Per addendum §3, this benchmark **is** pure
    buy-and-hold-by-construction on a daily-rebalance grid, BUT the
    daily rebalance itself creates small turnover when asset returns
    diverge. We therefore apply the frozen cost model to keep lag+cost
    parity; documented in ``cost_model`` column."""
    k = rets.shape[1]
    W = pd.DataFrame(1.0 / k, index=rets.index, columns=rets.columns)
    return _apply_costs(W, rets, COST_BPS)


def _btc_buy_hold(rets: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """BF2: pure BTC buy-and-hold. Cost=0 by construction (no rebalance)."""
    if "BTC" not in rets.columns:
        return (
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            pd.Series(dtype=float),
        )
    r_clip = rets["BTC"].clip(lower=-CLIP, upper=CLIP)
    net = r_clip.copy()
    gross = r_clip.copy()
    tov = pd.Series(0.0, index=rets.index)
    return net, gross, tov


def _momentum_baseline(rets: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """BF3: 20-bar time-series momentum, long-top / short-bottom halves,
    equal-weight within each half. Lag + cost parity with the frozen strategy."""
    lb = rets.rolling(window=MOMENTUM_LOOKBACK, min_periods=MOMENTUM_LOOKBACK).sum()
    W = pd.DataFrame(0.0, index=rets.index, columns=rets.columns)
    k = rets.shape[1]
    half = max(1, k // 2)
    for t in range(len(rets)):
        row = lb.iloc[t]
        if row.isna().any():
            continue
        order = np.argsort(row.to_numpy())
        shorts = order[:half]
        longs = order[-half:]
        w = np.zeros(k)
        if len(longs):
            w[longs] = 1.0 / len(longs)
        if len(shorts):
            w[shorts] = -1.0 / len(shorts)
        W.iloc[t] = w
    return _apply_costs(W, rets, COST_BPS)


def _vol_targeted_equal_weight(
    rets: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """BF4: BF1 scaled by expanding-window realized vol of BF1 → 15 % target.

    Uses realized vol of the equal-weight portfolio itself up to t-1
    (strict expanding-window past only). Cap at 1.5× leverage to mirror
    the frozen strategy's cap."""
    bf1_net, _, _ = _equal_weight_buy_hold(rets)
    # Expanding-window realized annualised vol of BF1 up to t-1
    ewma = bf1_net.shift(1).expanding(min_periods=20).std()
    ann_vol = ewma * np.sqrt(BPY)
    lev = (PARAMS.vol_target_annualised / ann_vol).clip(upper=PARAMS.vol_cap_leverage).fillna(0.0)
    k = rets.shape[1]
    W = pd.DataFrame(np.outer(lev.values, np.ones(k)) / k, index=rets.index, columns=rets.columns)
    return _apply_costs(W, rets, COST_BPS)


def main() -> int:
    rets = build_returns_panel(PARAMS.strategy_assets, SPIKE_DATA, PARAMS.ffill_limit_bdays)

    # Reproduce Kuramoto strategy for same index
    panel = build_panel(PARAMS.regime_assets, SPIKE_DATA, PARAMS.ffill_limit_bdays)
    log_r = compute_log_returns(panel)
    phases = extract_phase(log_r, PARAMS.detrend_window_bdays).dropna()
    r_series = kuramoto_order(phases, PARAMS.r_window_bdays).dropna()
    regimes = classify_regimes(
        r_series,
        PARAMS.regime_threshold_train_frac,
        PARAMS.regime_quantile_low,
        PARAMS.regime_quantile_high,
    )
    strat = simulate_rp_strategy(
        rets,
        regimes,
        PARAMS.regime_buckets,
        PARAMS.vol_window_bdays,
        PARAMS.vol_target_annualised,
        PARAMS.vol_cap_leverage,
        COST_BPS,
        CLIP,
        BPY,
        LAG,
    )
    n = len(strat)
    split = int(n * PARAMS.backtest_train_test_split_frac)
    strat_test = strat["net_ret"].iloc[split:]
    strat_sharpe = _sharpe(strat_test)
    strat_metrics = compute_metrics(strat_test, BPY)

    # Align benchmarks to strat index
    rets_on_strat = rets.reindex(strat.index)

    benchmarks: list[tuple[str, str, pd.Series, pd.Series]] = []
    net, _, tov = _equal_weight_buy_hold(rets_on_strat)
    benchmarks.append(("equal_weight_buy_hold", "cost=10bps (daily rebalance turnover)", net, tov))
    net, _, tov = _btc_buy_hold(rets_on_strat)
    benchmarks.append(("btc_benchmark", "pure buy-and-hold, cost=0 by construction", net, tov))
    net, _, tov = _momentum_baseline(rets_on_strat)
    benchmarks.append(("momentum_baseline", "20-bar TS momentum, cost=10bps, lag=1", net, tov))
    net, _, tov = _vol_targeted_equal_weight(rets_on_strat)
    benchmarks.append(
        ("vol_targeted_equal_weight", "BF1 × target=15 % ann vol, cap=1.5×, cost=10bps", net, tov)
    )

    rows: list[dict] = []
    # Add the frozen strategy as reference
    rows.append(
        {
            "benchmark_id": "kuramoto_strategy",
            "cost_model": "cost=10bps, lag=1 (frozen)",
            "oos_sharpe": round(strat_sharpe, 4),
            "max_dd": round(strat_metrics["max_drawdown"], 4),
            "ann_return": round(strat_metrics["ann_return"], 4),
            "ann_vol": round(strat_metrics["ann_vol"], 4),
            "turnover_mean_daily": round(float(strat["turnover"].iloc[split:].mean()), 4),
            "kuramoto_sharpe_excess": 0.0,
        }
    )
    for bid, cost_model, net_series, tov_series in benchmarks:
        test_net = net_series.iloc[split:] if not net_series.empty else net_series
        if test_net.empty:
            rows.append(
                {
                    "benchmark_id": bid,
                    "cost_model": cost_model,
                    "oos_sharpe": float("nan"),
                    "max_dd": float("nan"),
                    "ann_return": float("nan"),
                    "ann_vol": float("nan"),
                    "turnover_mean_daily": float("nan"),
                    "kuramoto_sharpe_excess": float("nan"),
                }
            )
            continue
        m = compute_metrics(test_net, BPY)
        bm_sharpe = m["sharpe"]
        excess = strat_sharpe - bm_sharpe
        rows.append(
            {
                "benchmark_id": bid,
                "cost_model": cost_model,
                "oos_sharpe": round(bm_sharpe, 4),
                "max_dd": round(m["max_drawdown"], 4),
                "ann_return": round(m["ann_return"], 4),
                "ann_vol": round(m["ann_vol"], 4),
                "turnover_mean_daily": (
                    round(float(tov_series.iloc[split:].mean()), 4)
                    if not tov_series.empty
                    else float("nan")
                ),
                "kuramoto_sharpe_excess": round(excess, 4),
            }
        )
    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "benchmark_family.csv", index=False, lineterminator="\n")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
