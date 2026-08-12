"""Phase 2 · Data-treatment dependency audit.

Everything frozen (signal, params, cost, lag, folds) except the
missing-data treatment at panel construction. Four treatments:

- strict_drop_missing               — inner-join native rows, no ffill
- forward_fill_limit_1              — bday grid, ffill(limit=1), drop rest
- forward_fill_limit_3              — frozen convention
- no_forward_fill_aligned_subset    — bday grid, no ffill, drop any row
                                      with a NaN (= effectively strict on bday grid)

CSV also records ``aligned_bar_count`` and ``dropped_bar_count`` per
the mid-protocol addendum so treatment effect is not confounded with
usable-sample geometry.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]

from core.cross_asset_kuramoto import (  # noqa: E402
    classify_regimes,
    compute_metrics,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.invariants import load_parameter_lock  # noqa: E402
from core.cross_asset_kuramoto.signal import load_asset_close  # noqa: E402

LOCK = REPO / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
OUT_DIR = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"
OUT_CSV = OUT_DIR / "data_treatment_audit.csv"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"

PARAMS = load_parameter_lock(LOCK)


def _build_panel(assets: tuple[str, ...], treatment: str) -> tuple[pd.DataFrame, int, int]:
    """Return (panel, aligned_bar_count, dropped_bar_count)."""
    series = OrderedDict()
    for a in assets:
        series[a] = load_asset_close(a, SPIKE_DATA)
    native = pd.concat([series[a] for a in assets], axis=1, keys=list(assets))
    bdays = pd.date_range(native.index.min(), native.index.max(), freq="B", tz="UTC")
    if treatment == "strict_drop_missing":
        # Inner-join on native (non-business-day grid); use the common index
        panel = native.dropna()
    elif treatment == "forward_fill_limit_1":
        reind = native.reindex(bdays)
        panel = reind.ffill(limit=1).dropna()
    elif treatment == "forward_fill_limit_3":
        reind = native.reindex(bdays)
        panel = reind.ffill(limit=3).dropna()
    elif treatment == "no_forward_fill_aligned_subset_only":
        reind = native.reindex(bdays)
        panel = reind.dropna()  # zero forward fill on bday grid
    else:
        raise ValueError(f"unknown treatment {treatment!r}")
    aligned = int(len(panel))
    # "dropped" = count of (potential) rows on the bday grid that were not
    # usable after the given treatment; reports sample-geometry cost.
    dropped = int(len(bdays) - aligned)
    return panel, aligned, dropped


def _run_treatment(
    regime_assets: tuple[str, ...],
    tradable_assets: tuple[str, ...],
    treatment: str,
) -> dict:
    reg_panel, reg_bars, reg_dropped = _build_panel(regime_assets, treatment)
    log_r = np.log(reg_panel / reg_panel.shift(1)).dropna()
    phases = extract_phase(log_r, PARAMS.detrend_window_bdays).dropna()
    r_series = kuramoto_order(phases, PARAMS.r_window_bdays).dropna()
    regimes = classify_regimes(
        r_series,
        PARAMS.regime_threshold_train_frac,
        PARAMS.regime_quantile_low,
        PARAMS.regime_quantile_high,
    )
    trad_panel, trad_bars, trad_dropped = _build_panel(tradable_assets, treatment)
    rets = np.log(trad_panel / trad_panel.shift(1)).dropna()
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
    n = len(strat)
    split = int(n * PARAMS.backtest_train_test_split_frac)
    m = compute_metrics(strat["net_ret"].iloc[split:], PARAMS.bars_per_year)
    usable = n
    return {
        "oos_sharpe": m["sharpe"],
        "max_dd": m["max_drawdown"],
        "ann_return": m["ann_return"],
        "regime_aligned_bar_count": reg_bars,
        "regime_dropped_bar_count": reg_dropped,
        "tradable_aligned_bar_count": trad_bars,
        "tradable_dropped_bar_count": trad_dropped,
        "strategy_usable_bar_count": usable,
    }


def main() -> int:
    treatments = [
        (
            "strict_drop_missing",
            False,
            "Native rows only; no calendar regrid, no ffill; only days where every asset has a native bar. "
            "Loses TradFi-holiday days where crypto has bars but equities do not.",
        ),
        (
            "forward_fill_limit_1",
            True,
            "Bday grid, forward-fill up to 1 day; approximate 1-day-stale tolerance.",
        ),
        (
            "forward_fill_limit_3",
            True,
            "Bday grid, forward-fill up to 3 days; FROZEN spike convention.",
        ),
        (
            "no_forward_fill_aligned_subset_only",
            False,
            "Bday grid, no forward-fill; drops any bday row where any asset missing. "
            "Measures sample geometry without fill.",
        ),
    ]
    rows: list[dict] = []
    frozen_sharpe: float | None = None
    for tid, admissible, reason in treatments:
        print(f"[data_treatment] {tid} …")
        try:
            res = _run_treatment(PARAMS.regime_assets, PARAMS.strategy_assets, tid)
        except Exception as exc:
            rows.append(
                {
                    "treatment": tid,
                    "oos_sharpe": float("nan"),
                    "max_dd": float("nan"),
                    "ann_return": float("nan"),
                    "aligned_bar_count": "n/a",
                    "dropped_bar_count": "n/a",
                    "strategy_usable_bar_count": 0,
                    "delta_sharpe_vs_frozen": float("nan"),
                    "operationally_admissible": "no",
                    "reason": f"FAILED: {exc!r}",
                }
            )
            continue
        if tid == "forward_fill_limit_3":
            frozen_sharpe = res["oos_sharpe"]
        rows.append(
            {
                "treatment": tid,
                "oos_sharpe": round(res["oos_sharpe"], 6),
                "max_dd": round(res["max_dd"], 6),
                "ann_return": round(res["ann_return"], 6),
                # aligned/dropped: report tradable panel (the one driving strategy),
                # plus regime panel counts in reason column for transparency.
                "aligned_bar_count": res["tradable_aligned_bar_count"],
                "dropped_bar_count": res["tradable_dropped_bar_count"],
                "strategy_usable_bar_count": res["strategy_usable_bar_count"],
                "delta_sharpe_vs_frozen": float("nan"),  # filled below
                "operationally_admissible": "yes" if admissible else "no",
                "reason": (
                    f"{reason} (regime panel aligned={res['regime_aligned_bar_count']}, "
                    f"dropped={res['regime_dropped_bar_count']})"
                ),
            }
        )

    # Second pass: fill delta_sharpe_vs_frozen
    if frozen_sharpe is not None:
        for r in rows:
            if isinstance(r["oos_sharpe"], float) and np.isfinite(r["oos_sharpe"]):
                r["delta_sharpe_vs_frozen"] = round(r["oos_sharpe"] - frozen_sharpe, 6)

    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, lineterminator="\n")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
