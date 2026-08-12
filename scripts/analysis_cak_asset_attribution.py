"""Phase 3 · Per-asset contribution and drawdown anatomy.

Reproduces the frozen strategy once, then attributes cumulative net
return and top-3 drawdown loss by asset. Uses the exact weight path
produced by the frozen ``simulate_rp_strategy`` — reconstructed here
so per-asset contribution is derivable (the engine does not return
weights directly, so we shadow the same inv-vol-in-bucket logic; the
reconstruction is asserted against the engine's scalar outputs for
consistency).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]

from core.cross_asset_kuramoto import (  # noqa: E402
    build_panel,
    build_returns_panel,
    classify_regimes,
    compute_log_returns,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.engine import rolling_vol  # noqa: E402
from core.cross_asset_kuramoto.invariants import load_parameter_lock  # noqa: E402

LOCK = REPO / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
OUT_DIR = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"

PARAMS = load_parameter_lock(LOCK)
WF_SPLITS = json.loads(LOCK.read_text())["walk_forward_splits_expanding_window"]


def _reconstruct_weights(
    rets: pd.DataFrame,
    regimes_lag: pd.Series,
) -> pd.DataFrame:
    """Shadow the engine's weight construction to get per-asset weights per bar."""
    asset_vols_lag = rolling_vol(rets, PARAMS.vol_window_bdays, PARAMS.bars_per_year).shift(1)
    assets = list(rets.columns)
    col_idx = {a: i for i, a in enumerate(assets)}
    n = len(rets)
    W = np.zeros((n, len(assets)))
    leverage = np.zeros(n)
    for t in range(n):
        regime = regimes_lag.iloc[t]
        if not isinstance(regime, str) or regime not in PARAMS.regime_buckets:
            continue
        bucket = PARAMS.regime_buckets[regime]
        vols_today = asset_vols_lag.iloc[t]
        inv_vols: list[float] = []
        valid_assets: list[str] = []
        for a in bucket:
            v = vols_today.get(a, np.nan)
            if np.isfinite(v) and v > 0:
                inv_vols.append(1.0 / float(v))
                valid_assets.append(a)
        if not inv_vols:
            continue
        arr = np.asarray(inv_vols)
        rp = arr / arr.sum()
        w = np.zeros(len(assets))
        for a, rw in zip(valid_assets, rp, strict=True):
            w[col_idx[a]] = rw
        vols_vec = vols_today.to_numpy()
        vols_vec = np.nan_to_num(vols_vec, nan=1e9)
        port_vol = float(np.sqrt(np.sum((w * vols_vec) ** 2)))
        lev = (
            min(PARAMS.vol_target_annualised / port_vol, PARAMS.vol_cap_leverage)
            if port_vol > 0
            else 0.0
        )
        leverage[t] = lev
        W[t] = w * lev
    return pd.DataFrame(W, index=rets.index, columns=assets)


def main() -> int:
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
    rets = build_returns_panel(PARAMS.strategy_assets, SPIKE_DATA, PARAMS.ffill_limit_bdays)
    strat = simulate_rp_strategy(
        rets,
        regimes,
        PARAMS.regime_buckets,
        PARAMS.vol_window_bdays,
        PARAMS.vol_target_annualised,
        PARAMS.vol_cap_leverage,
        PARAMS.cost_bps,
        PARAMS.return_clip_abs,
        PARAMS.bars_per_year,
        PARAMS.execution_lag_bars,
    )

    # The engine already lags regimes by 1 bar when building weights;
    # weights W[t] were derived from regime[t-1] via that in-engine shift.
    # Therefore for attribution we use W[t] directly against r[t] (no extra shift).
    regimes_lag = regimes.shift(PARAMS.execution_lag_bars).reindex(strat.index)
    W = _reconstruct_weights(rets.loc[strat.index], regimes_lag)
    r_mat = rets.reindex(strat.index).reindex(columns=list(PARAMS.strategy_assets))
    r_clip = r_mat.clip(lower=-PARAMS.return_clip_abs, upper=PARAMS.return_clip_abs)

    gross_contrib = W * r_clip  # per-asset gross log-return per bar
    # Per-asset turnover = |W[t] − W[t−1]| (engine's prev_weights path)
    per_asset_turnover = W.diff().fillna(W).abs()
    per_asset_cost = per_asset_turnover * (PARAMS.cost_bps / 10_000.0)
    per_asset_net = gross_contrib - per_asset_cost

    # Consistency check: engine net_ret ≈ sum over assets
    rec_total = per_asset_net.sum(axis=1)
    diff = float(np.max(np.abs(rec_total.values - strat["net_ret"].values)))
    assert diff < 1e-9, f"weight reconstruction mismatch: {diff:.3e}"

    # --- OOS 70/30 split ---
    n = len(strat)
    split = int(n * PARAMS.backtest_train_test_split_frac)
    oos = per_asset_net.iloc[split:]
    total_oos = float(strat["net_ret"].iloc[split:].sum())

    # --- Per-asset contribution CSV ---
    rows: list[dict] = []
    for a in PARAMS.strategy_assets:
        asset_oos = oos[a]
        total_net = float(asset_oos.sum())
        gross_a = float(gross_contrib[a].iloc[split:].sum())
        cost_a = float(per_asset_cost[a].iloc[split:].sum())
        tov_a = float(per_asset_turnover[a].iloc[split:].sum())
        active_mask = W[a].iloc[split:].abs() > 1e-12
        active_count = int(active_mask.sum())
        if active_count > 0:
            hit_rate = float((asset_oos[active_mask] > 0).mean())
        else:
            hit_rate = float("nan")
        rows.append(
            {
                "asset": a,
                "net_contrib_log_return": round(total_net, 6),
                "gross_contrib_log_return": round(gross_a, 6),
                "cost_contrib_log_return": round(-cost_a, 6),
                "pct_of_portfolio_net": (
                    round(total_net / total_oos, 6) if abs(total_oos) > 1e-12 else float("nan")
                ),
                "turnover_sum": round(tov_a, 6),
                "bars_active": active_count,
                "hit_rate_when_active": round(hit_rate, 4) if np.isfinite(hit_rate) else None,
            }
        )
    df_contrib = pd.DataFrame(rows).sort_values("net_contrib_log_return", ascending=False)
    (OUT_DIR / "asset_contribution.csv").write_text(
        df_contrib.to_csv(index=False, lineterminator="\n")
    )

    # --- Drawdown anatomy (top-3 on OOS portfolio equity) ---
    eq = np.exp(strat["net_ret"].iloc[split:].cumsum())
    peak = eq.cummax()
    dd = 1.0 - eq / peak

    # Walk peak→trough runs on OOS
    in_dd = False
    start_i: int | None = None
    episodes: list[tuple[int, int, float]] = []
    for i in range(len(dd)):
        if not in_dd and eq.iloc[i] < peak.iloc[i]:
            in_dd = True
            # Find the peak that began this dd
            # (first index with peak == peak.iloc[i])
            start_i = int(np.searchsorted(peak.values, eq.iloc[i]))
        elif in_dd and eq.iloc[i] >= peak.iloc[i]:
            in_dd = False
            if start_i is not None:
                slab = dd.iloc[start_i : i + 1]
                trough_i = int(slab.values.argmax()) + start_i
                episodes.append((start_i, trough_i, float(dd.iloc[trough_i])))
            start_i = None
    if in_dd and start_i is not None:
        slab = dd.iloc[start_i:]
        trough_i = int(slab.values.argmax()) + start_i
        episodes.append((start_i, trough_i, float(dd.iloc[trough_i])))
    episodes.sort(key=lambda t: t[2], reverse=True)

    dd_rows: list[dict] = []
    for rank, (si, ti, depth) in enumerate(episodes[:3], start=1):
        window_contrib = oos.iloc[si : ti + 1].sum(axis=0)
        total_window = float(window_contrib.sum())
        for asset in PARAMS.strategy_assets:
            share = (
                round(float(window_contrib[asset]) / total_window, 6)
                if total_window != 0
                else float("nan")
            )
            dd_rows.append(
                {
                    "dd_rank": rank,
                    "start_date": str(eq.index[si].date()),
                    "trough_date": str(eq.index[ti].date()),
                    "depth": round(depth, 6),
                    "asset": asset,
                    "window_log_return_asset": round(float(window_contrib[asset]), 6),
                    "share_of_window_loss": share,
                }
            )
    pd.DataFrame(dd_rows).to_csv(OUT_DIR / "drawdown_anatomy.csv", index=False, lineterminator="\n")

    # --- Fold-level attribution summary (embedded as side sheet) ---
    fold_rows: list[dict] = []
    for cfg in WF_SPLITS:
        s_ts = pd.Timestamp(cfg["test_start"], tz="UTC")
        e_ts = pd.Timestamp(cfg["test_end"], tz="UTC")
        mask = (per_asset_net.index >= s_ts) & (per_asset_net.index < e_ts)
        slab = per_asset_net.loc[mask]
        if slab.empty:
            continue
        tot = float(slab.sum().sum())
        for a in PARAMS.strategy_assets:
            fold_rows.append(
                {
                    "fold_id": cfg["split"],
                    "test_start": cfg["test_start"],
                    "test_end": cfg["test_end"],
                    "asset": a,
                    "asset_net_log_return": round(float(slab[a].sum()), 6),
                    "share_of_fold_total": round(
                        float(slab[a].sum()) / tot if tot != 0 else float("nan"), 6
                    ),
                }
            )
    pd.DataFrame(fold_rows).to_csv(
        OUT_DIR / "fold_asset_attribution.csv", index=False, lineterminator="\n"
    )

    print(df_contrib.to_string(index=False))
    print("\nTop-3 DD episodes (OOS window):")
    print(
        pd.DataFrame(dd_rows).pivot_table(
            index=["dd_rank", "start_date", "trough_date", "depth"],
            columns="asset",
            values="share_of_window_loss",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
