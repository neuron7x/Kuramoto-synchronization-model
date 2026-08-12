"""T6: costs are applied when cost_bps > 0, and zero-cost Sharpe differs
from costed Sharpe (INV-CAK5 side condition)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.cross_asset_kuramoto import (
    build_panel,
    build_returns_panel,
    classify_regimes,
    compute_log_returns,
    compute_metrics,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.invariants import load_parameter_lock

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"


@pytest.fixture(scope="module")
def fixtures():
    if not SPIKE_DATA.is_dir():
        pytest.skip("spike data not present")
    params = load_parameter_lock(LOCK_PATH)
    panel = build_panel(params.regime_assets, SPIKE_DATA, params.ffill_limit_bdays)
    log_r = compute_log_returns(panel)
    phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
    r = kuramoto_order(phases, params.r_window_bdays).dropna()
    regimes = classify_regimes(
        r,
        params.regime_threshold_train_frac,
        params.regime_quantile_low,
        params.regime_quantile_high,
    )
    rets = build_returns_panel(params.strategy_assets, SPIKE_DATA, params.ffill_limit_bdays)
    return params, rets, regimes


def _sim(params, rets, regimes, cost_bps):
    return simulate_rp_strategy(
        rets,
        regimes,
        params.regime_buckets,
        params.vol_window_bdays,
        params.vol_target_annualised,
        params.vol_cap_leverage,
        cost_bps,
        params.return_clip_abs,
        params.bars_per_year,
        params.execution_lag_bars,
    )


def test_zero_cost_differs_from_positive_cost(fixtures) -> None:
    params, rets, regimes = fixtures
    s0 = _sim(params, rets, regimes, 0.0)
    s10 = _sim(params, rets, regimes, 10.0)
    # Gross returns identical (cost does not affect gross)
    assert np.allclose(s0["gross_ret"].to_numpy(), s10["gross_ret"].to_numpy())
    # Net returns differ on any bar with non-zero turnover
    diff = s10["net_ret"].to_numpy() - s0["net_ret"].to_numpy()
    assert np.any(diff < 0), "cost must reduce net return on at least one bar"


def test_sharpe_decreases_with_higher_cost(fixtures) -> None:
    params, rets, regimes = fixtures
    s10 = _sim(params, rets, regimes, 10.0)
    s20 = _sim(params, rets, regimes, 20.0)
    sh10 = compute_metrics(s10["net_ret"], params.bars_per_year)["sharpe"]
    sh20 = compute_metrics(s20["net_ret"], params.bars_per_year)["sharpe"]
    # Monotone non-increase
    assert sh20 <= sh10 + 1e-12


def test_turnover_nonnegative(fixtures) -> None:
    params, rets, regimes = fixtures
    s = _sim(params, rets, regimes, params.cost_bps)
    assert (s["turnover"].to_numpy() >= 0.0).all()


def test_cost_drag_matches_turnover_formula(fixtures) -> None:
    """Arithmetic check: gross - net == turnover * cost_bps / 10_000 per bar."""
    params, rets, regimes = fixtures
    s = _sim(params, rets, regimes, params.cost_bps)
    drag = s["gross_ret"].to_numpy() - s["net_ret"].to_numpy()
    expected = s["turnover"].to_numpy() * params.cost_bps / 10_000.0
    assert np.allclose(drag, expected, rtol=1e-12, atol=1e-15)
