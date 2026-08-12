"""Risk-parity regime strategy — backtest simulator and performance metrics.

Copy-ported from ``~/spikes/cross_asset_sync_regime/backtest_v2.py``
with type annotations added. Numerics preserved bit-for-bit against the
spike. No imports from ``backtest/``, ``execution/``, or ``strategies/``;
this module is self-contained above ``core/``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import numpy as np
import pandas as pd

from .invariants import CAKInvariantError
from .types import BacktestResult

__all__ = [
    "BacktestResult",
    "compute_metrics",
    "drawdown_series",
    "result_from_dataframe",
    "rolling_vol",
    "simulate_rp_strategy",
]


def rolling_vol(returns: pd.DataFrame, window: int, bars_per_year: int) -> pd.DataFrame:
    """Annualised rolling standard deviation of log returns."""
    std = returns.rolling(window=window, min_periods=window).std()
    return cast(pd.DataFrame, std * np.sqrt(bars_per_year))


def simulate_rp_strategy(
    returns: pd.DataFrame,
    regimes: pd.Series,
    regime_buckets: Mapping[str, tuple[str, ...]],
    vol_window: int,
    vol_target: float,
    vol_cap: float,
    cost_bps: float,
    return_clip_abs: float,
    bars_per_year: int,
    execution_lag_bars: int = 1,
) -> pd.DataFrame:
    """Daily risk-parity-in-bucket + vol-target strategy, no look-ahead.

    Mirrors ``backtest_v2.simulate_rp_strategy`` step-for-step:

    1. Lag ``regimes`` by ``execution_lag_bars`` to obtain the regime
       visible at rebalance time.
    2. Inverse-volatility risk-parity weights within the bucket assigned
       to the visible regime (``regime_buckets``).
    3. Vol-target overlay: scale total exposure to reach ``vol_target``
       annualised, capped at ``vol_cap``.
    4. Turnover cost applied on absolute weight change.
    5. Per-bar log returns clipped to ``[-return_clip_abs, +return_clip_abs]``.

    ``cost_bps`` is the round-trip bps applied to one unit of turnover
    (consistent with spike definition). Setting ``cost_bps=0`` is allowed
    but the caller is responsible for surfacing it to the user — the
    module-level invariants register this as a warn-worthy event.
    """
    regimes_lag = regimes.shift(execution_lag_bars)
    common_idx = returns.index.intersection(regimes_lag.index)
    rets = returns.loc[common_idx]
    regs = regimes_lag.loc[common_idx].dropna()
    rets = rets.loc[regs.index]
    if rets.empty:
        raise CAKInvariantError("empty strategy window after regime lag")

    asset_vols = rolling_vol(rets, vol_window, bars_per_year)
    asset_vols_lag = asset_vols.shift(1)  # strict no-look-ahead

    assets_all = list(rets.columns)
    col_idx = {a: i for i, a in enumerate(assets_all)}
    n = len(rets)

    gross = np.zeros(n)
    net = np.zeros(n)
    turnover = np.zeros(n)
    leverage = np.zeros(n)
    regime_used: list[str] = []
    prev_weights = np.zeros(len(assets_all))

    for t in range(n):
        regime = regs.iloc[t]
        w = np.zeros(len(assets_all))
        if regime in regime_buckets:
            bucket = regime_buckets[regime]
            vols_today = asset_vols_lag.iloc[t]
            inv_vols: list[float] = []
            valid_assets: list[str] = []
            for a in bucket:
                v = vols_today.get(a, np.nan)
                if np.isfinite(v) and v > 0:
                    inv_vols.append(1.0 / v)
                    valid_assets.append(a)
            if inv_vols:
                inv_arr = np.asarray(inv_vols, dtype=float)
                rp_weights = inv_arr / inv_arr.sum()
                for a, rw in zip(valid_assets, rp_weights, strict=True):
                    w[col_idx[a]] = rw

        vols_vec = asset_vols_lag.iloc[t].to_numpy()
        vols_vec = np.nan_to_num(vols_vec, nan=1e9)
        port_vol = float(np.sqrt(np.sum((w * vols_vec) ** 2)))
        lev = min(vol_target / port_vol, vol_cap) if port_vol > 0 else 0.0
        leverage[t] = lev
        w_scaled = w * lev

        tov = float(np.abs(w_scaled - prev_weights).sum())
        turnover[t] = tov
        r_vec = rets.iloc[t].to_numpy()
        r_vec = np.clip(r_vec, -return_clip_abs, return_clip_abs)
        g = float((w_scaled * r_vec).sum())
        gross[t] = g
        cost = tov * (cost_bps / 10_000.0)
        net[t] = g - cost
        prev_weights = w_scaled
        regime_used.append(regime)

    out = pd.DataFrame(
        {
            "gross_ret": gross,
            "net_ret": net,
            "turnover": turnover,
            "leverage": leverage,
            "regime": regime_used,
        },
        index=rets.index,
    )
    return out


def compute_metrics(net_returns: pd.Series, bars_per_year: int) -> dict[str, float]:
    """Annualised performance metrics for a net-return series (log space)."""
    r = net_returns.dropna().to_numpy()
    if len(r) == 0:
        return {}
    ann_ret = float(np.mean(r) * bars_per_year)
    ann_vol = float(np.std(r, ddof=1) * np.sqrt(bars_per_year))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else float("nan")
    downside = r[r < 0]
    dd_dev = (
        float(np.std(downside, ddof=1) * np.sqrt(bars_per_year))
        if len(downside) > 1
        else float("nan")
    )
    sortino = ann_ret / dd_dev if dd_dev and dd_dev > 0 else float("nan")
    eq = np.exp(np.cumsum(r))
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(dd.min())
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else float("nan")
    hit_rate = float((r > 0).mean())
    total_log_ret = float(r.sum())
    total_mult = float(np.exp(total_log_ret))
    return {
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "hit_rate": hit_rate,
        "total_log_return": total_log_ret,
        "total_multiplier": total_mult,
        "n_days": int(len(r)),
    }


def drawdown_series(net_returns: pd.Series) -> pd.Series:
    """(equity - peak) / peak on the supplied log-return series."""
    eq = np.exp(net_returns.fillna(0.0).cumsum())
    peak = eq.cummax()
    return cast(pd.Series, (eq - peak) / peak)


def result_from_dataframe(df: pd.DataFrame) -> BacktestResult:
    """Convert a spike-shaped strategy DataFrame to a frozen container."""
    return BacktestResult(
        gross_ret=tuple(df["gross_ret"].to_list()),
        net_ret=tuple(df["net_ret"].to_list()),
        turnover=tuple(df["turnover"].to_list()),
        leverage=tuple(df["leverage"].to_list()),
        regime=tuple(df["regime"].astype(str).to_list()),
        index_iso=tuple(df.index.map(lambda ts: ts.isoformat()).to_list()),
    )
