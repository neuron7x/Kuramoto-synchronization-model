"""Phase 1 · Leave-one-asset-out robustness on the frozen Kuramoto module.

Two independent sweeps:

- REGIME_LOO  — omit one of 8 regime-panel assets; R(t) is recomputed
                on the remaining 7; tradable universe unchanged.
- TRADABLE_LOO — omit one of 5 tradable-panel assets; regime-panel
                R(t) unchanged; `regime_buckets` filtered to remove
                the omitted asset from every bucket that contained it;
                returns panel has 4 columns instead of 5.
                inv-vol risk parity within bucket naturally renormalises.

For tradable LOO, benchmark definitions remain unchanged unless they
depend directly on the omitted tradable asset universe. If a benchmark
depends on tradable membership we recompute deterministically on the
reduced tradable set and flag ``benchmark_recomputed=yes``. (Benchmark
in this LOO phase is BTC buy-and-hold only, which is independent of
the tradable-universe composition, so recomputed=no throughout.)

Everything else is frozen: module parameters, fold boundaries,
cost model, lag, fill policy.
"""

from __future__ import annotations

import json
from pathlib import Path

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
OUT_CSV = OUT_DIR / "leave_one_asset_out.csv"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"

PARAMS = load_parameter_lock(LOCK)
WF_SPLITS = json.loads(LOCK.read_text())["walk_forward_splits_expanding_window"]


def _slice(s: pd.Series, start: str, end: str) -> pd.Series:
    s_ts = pd.Timestamp(start, tz="UTC")
    e_ts = pd.Timestamp(end, tz="UTC")
    return s.loc[(s.index >= s_ts) & (s.index < e_ts)]


def _run(
    regime_assets: tuple[str, ...],
    tradable_assets: tuple[str, ...],
    regime_buckets: dict[str, tuple[str, ...]],
) -> tuple[pd.DataFrame, dict[str, float]]:
    panel = build_panel(regime_assets, SPIKE_DATA, PARAMS.ffill_limit_bdays)
    log_r = compute_log_returns(panel)
    phases = extract_phase(log_r, PARAMS.detrend_window_bdays).dropna()
    r_series = kuramoto_order(phases, PARAMS.r_window_bdays).dropna()
    regimes = classify_regimes(
        r_series,
        PARAMS.regime_threshold_train_frac,
        PARAMS.regime_quantile_low,
        PARAMS.regime_quantile_high,
    )
    rets = build_returns_panel(tradable_assets, SPIKE_DATA, PARAMS.ffill_limit_bdays)
    strat = simulate_rp_strategy(
        rets,
        regimes,
        regime_buckets,
        PARAMS.vol_window_bdays,
        PARAMS.vol_target_annualised,
        PARAMS.vol_cap_leverage,
        PARAMS.cost_bps,
        PARAMS.return_clip_abs,
        PARAMS.bars_per_year,
        PARAMS.execution_lag_bars,
    )
    # Per-fold Sharpe on the 5 WF splits
    fold_sharpes: dict[str, float] = {}
    for cfg in WF_SPLITS:
        test = _slice(strat["net_ret"], cfg["test_start"], cfg["test_end"])
        if len(test) < 60:
            fold_sharpes[f"fold{cfg['split']}"] = float("nan")
            continue
        m = compute_metrics(test, PARAMS.bars_per_year)
        fold_sharpes[f"fold{cfg['split']}"] = m["sharpe"]
    # OOS 70/30
    n = len(strat)
    split = int(n * PARAMS.backtest_train_test_split_frac)
    m_oos = compute_metrics(strat["net_ret"].iloc[split:], PARAMS.bars_per_year)
    agg = {
        "oos_sharpe": m_oos["sharpe"],
        "max_dd": m_oos["max_drawdown"],
        "ann_return": m_oos["ann_return"],
        "turnover": float(strat["turnover"].iloc[split:].mean()) * PARAMS.bars_per_year,
        **fold_sharpes,
    }
    return strat, agg


def main() -> int:
    # Full baseline
    _, base = _run(PARAMS.regime_assets, PARAMS.strategy_assets, PARAMS.regime_buckets)
    base_sharpe = base["oos_sharpe"]
    base_mdd = base["max_dd"]
    rows: list[dict] = []
    rows.append(
        {
            "loo_type": "baseline_full",
            "omitted_asset": "",
            "benchmark_recomputed": "no",
            **{k: round(v, 6) for k, v in base.items() if isinstance(v, float)},
            "delta_sharpe_vs_full": 0.0,
            "delta_max_dd_vs_full": 0.0,
            "notes": "8-asset regime, 5-asset tradable, frozen buckets.",
        }
    )

    # REGIME LOO — omit one regime-panel member
    for omit in PARAMS.regime_assets:
        regime = tuple(a for a in PARAMS.regime_assets if a != omit)
        try:
            _, agg = _run(regime, PARAMS.strategy_assets, PARAMS.regime_buckets)
        except Exception as exc:
            rows.append(
                {
                    "loo_type": "regime",
                    "omitted_asset": omit,
                    "benchmark_recomputed": "no",
                    "oos_sharpe": float("nan"),
                    "max_dd": float("nan"),
                    "ann_return": float("nan"),
                    "turnover": float("nan"),
                    "fold1": float("nan"),
                    "fold2": float("nan"),
                    "fold3": float("nan"),
                    "fold4": float("nan"),
                    "fold5": float("nan"),
                    "delta_sharpe_vs_full": float("nan"),
                    "delta_max_dd_vs_full": float("nan"),
                    "notes": f"regime LOO FAILED: {exc!r}",
                }
            )
            continue
        rows.append(
            {
                "loo_type": "regime",
                "omitted_asset": omit,
                "benchmark_recomputed": "no",
                **{k: round(v, 6) for k, v in agg.items() if isinstance(v, float)},
                "delta_sharpe_vs_full": round(agg["oos_sharpe"] - base_sharpe, 6),
                "delta_max_dd_vs_full": round(agg["max_dd"] - base_mdd, 6),
                "notes": f"R(t) recomputed on {len(regime)} assets; tradable unchanged.",
            }
        )

    # TRADABLE LOO — omit one tradable asset; filter buckets accordingly
    for omit in PARAMS.strategy_assets:
        tradable = tuple(a for a in PARAMS.strategy_assets if a != omit)
        buckets_red = {
            k: tuple(a for a in v if a != omit) for k, v in PARAMS.regime_buckets.items()
        }
        try:
            _, agg = _run(PARAMS.regime_assets, tradable, buckets_red)
        except Exception as exc:
            rows.append(
                {
                    "loo_type": "tradable",
                    "omitted_asset": omit,
                    "benchmark_recomputed": "no",
                    "oos_sharpe": float("nan"),
                    "max_dd": float("nan"),
                    "ann_return": float("nan"),
                    "turnover": float("nan"),
                    "fold1": float("nan"),
                    "fold2": float("nan"),
                    "fold3": float("nan"),
                    "fold4": float("nan"),
                    "fold5": float("nan"),
                    "delta_sharpe_vs_full": float("nan"),
                    "delta_max_dd_vs_full": float("nan"),
                    "notes": f"tradable LOO FAILED: {exc!r}",
                }
            )
            continue
        rows.append(
            {
                "loo_type": "tradable",
                "omitted_asset": omit,
                "benchmark_recomputed": "no",
                **{k: round(v, 6) for k, v in agg.items() if isinstance(v, float)},
                "delta_sharpe_vs_full": round(agg["oos_sharpe"] - base_sharpe, 6),
                "delta_max_dd_vs_full": round(agg["max_dd"] - base_mdd, 6),
                "notes": (
                    f"tradable={tradable}; buckets filtered; inv-vol risk-parity "
                    "naturally renormalises within remaining bucket members."
                ),
            }
        )

    cols = [
        "loo_type",
        "omitted_asset",
        "benchmark_recomputed",
        "oos_sharpe",
        "delta_sharpe_vs_full",
        "max_dd",
        "delta_max_dd_vs_full",
        "ann_return",
        "turnover",
        "fold1",
        "fold2",
        "fold3",
        "fold4",
        "fold5",
        "notes",
    ]
    df = pd.DataFrame(rows)
    df = df.reindex(columns=cols)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, lineterminator="\n")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
