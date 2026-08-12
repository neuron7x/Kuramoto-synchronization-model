"""T2: INV-CAK3 determinism — two runs on identical inputs produce
identical signal and strategy outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.cross_asset_kuramoto import (
    build_panel,
    classify_regimes,
    compute_log_returns,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.invariants import assert_cak3_deterministic, load_parameter_lock

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"


@pytest.fixture(scope="module")
def params():
    return load_parameter_lock(LOCK_PATH)


@pytest.fixture(scope="module")
def regime_panel(params):
    if not SPIKE_DATA.is_dir():
        pytest.skip("spike data directory not present")
    return build_panel(
        params.regime_assets,
        SPIKE_DATA,
        params.ffill_limit_bdays,
    )


def test_r_series_is_deterministic(params, regime_panel) -> None:
    log_r = compute_log_returns(regime_panel)
    phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
    r1 = kuramoto_order(phases, params.r_window_bdays).dropna().to_numpy()
    r2 = kuramoto_order(phases, params.r_window_bdays).dropna().to_numpy()
    assert_cak3_deterministic(r1, r2)


def test_regime_classification_is_deterministic(params, regime_panel) -> None:
    log_r = compute_log_returns(regime_panel)
    phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
    r = kuramoto_order(phases, params.r_window_bdays).dropna()
    a = classify_regimes(
        r,
        params.regime_threshold_train_frac,
        params.regime_quantile_low,
        params.regime_quantile_high,
    )
    b = classify_regimes(
        r,
        params.regime_threshold_train_frac,
        params.regime_quantile_low,
        params.regime_quantile_high,
    )
    pd.testing.assert_series_equal(a, b, check_names=True)


def test_strategy_is_deterministic(params, regime_panel) -> None:
    from core.cross_asset_kuramoto import build_returns_panel

    log_r = compute_log_returns(regime_panel)
    phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
    r = kuramoto_order(phases, params.r_window_bdays).dropna()
    regimes = classify_regimes(
        r,
        params.regime_threshold_train_frac,
        params.regime_quantile_low,
        params.regime_quantile_high,
    )
    strat_rets = build_returns_panel(
        params.strategy_assets,
        SPIKE_DATA,
        params.ffill_limit_bdays,
    )
    s1 = simulate_rp_strategy(
        strat_rets,
        regimes,
        params.regime_buckets,
        params.vol_window_bdays,
        params.vol_target_annualised,
        params.vol_cap_leverage,
        params.cost_bps,
        params.return_clip_abs,
        params.bars_per_year,
        params.execution_lag_bars,
    )
    s2 = simulate_rp_strategy(
        strat_rets,
        regimes,
        params.regime_buckets,
        params.vol_window_bdays,
        params.vol_target_annualised,
        params.vol_cap_leverage,
        params.cost_bps,
        params.return_clip_abs,
        params.bars_per_year,
        params.execution_lag_bars,
    )
    assert_cak3_deterministic(s1["net_ret"].to_numpy(), s2["net_ret"].to_numpy())
    assert_cak3_deterministic(s1["gross_ret"].to_numpy(), s2["gross_ret"].to_numpy())
    assert_cak3_deterministic(s1["turnover"].to_numpy(), s2["turnover"].to_numpy())
    assert_cak3_deterministic(s1["leverage"].to_numpy(), s2["leverage"].to_numpy())
