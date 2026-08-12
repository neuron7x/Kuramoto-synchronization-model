"""T2 · required offline-robustness CSVs exist with declared columns."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"

SCHEMAS = {
    "leave_one_asset_out.csv": {
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
    },
    "data_treatment_audit.csv": {
        "treatment",
        "oos_sharpe",
        "max_dd",
        "ann_return",
        "aligned_bar_count",
        "dropped_bar_count",
        "strategy_usable_bar_count",
        "delta_sharpe_vs_frozen",
        "operationally_admissible",
        "reason",
    },
    "asset_contribution.csv": {
        "asset",
        "net_contrib_log_return",
        "gross_contrib_log_return",
        "cost_contrib_log_return",
        "pct_of_portfolio_net",
        "turnover_sum",
        "bars_active",
        "hit_rate_when_active",
    },
    "drawdown_anatomy.csv": {
        "dd_rank",
        "start_date",
        "trough_date",
        "depth",
        "asset",
        "window_log_return_asset",
        "share_of_window_loss",
    },
    "benchmark_family.csv": {
        "benchmark_id",
        "cost_model",
        "oos_sharpe",
        "max_dd",
        "ann_return",
        "ann_vol",
        "turnover_mean_daily",
        "kuramoto_sharpe_excess",
    },
    "envelope_stress.csv": {
        "horizon_bars",
        "n_paths",
        "block_length",
        "seed",
        "breach_freq_below_p05",
        "breach_freq_below_p25",
        "median_cumret_log",
        "p05_cumret_log",
        "p95_cumret_log",
        "max_dd_median",
        "max_dd_p95",
        "early_dip_paths",
        "recovery_prob_after_early_dip",
    },
}


def test_all_required_csvs_exist() -> None:
    missing = [name for name in SCHEMAS if not (OUT / name).is_file()]
    assert not missing, f"missing CSVs: {missing}"


def test_schemas_match() -> None:
    for name, expected in SCHEMAS.items():
        df = pd.read_csv(OUT / name)
        assert (
            set(df.columns) == expected
        ), f"{name}: columns {set(df.columns)} != expected {expected}"
