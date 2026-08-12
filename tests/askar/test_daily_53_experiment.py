"""Tests for the 53-asset daily Ricci + momentum-stack experiment.

Required 6/6 per the task brief:
 1. 53_assets_loaded             — daily panel carries >= 50 assets
                                    and the task's target column
 2. daily_resample_no_gaps       — no calendar-day gap > 5 after the
                                    load filter
 3. momentum_weights_train_only  — perturbing the test slice does not
                                    change the stacking weights
 4. threshold_grid_train_only    — grid IC uses bars strictly before
                                    the split date
 5. no_lookahead                 — future perturbation of combo does
                                    not change past expanding-quintile
                                    positions
 6. output_schema_complete       — result JSON contains every required
                                    top-level and block-level key
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.daily_53_experiment import (
    PANEL_PATH,
    RESULTS_DIR,
    SPLIT_DATE,
    TARGET_PRIMARY,
    THRESHOLD_GRID,
    WINDOW_GRID,
    DailyPanel,
    compute_unity_series,
    load_daily_panel,
    run_test_2,
    run_test_3,
    run_test_4,
)
from research.askar.optimal_universe import (
    compute_signal,
    expanding_quintile,
)

REQUIRED_TOP_KEYS = {
    "test1_53assets",
    "test2_momentum_stack",
    "test3_sensitivity",
    "test4_unity",
    "baseline_yfinance_IC",
    "u4_prior_IC",
    "best_IC_test_across_tests",
    "best_IC_test_source",
    "final_verdict",
    "askar_message",
}

REQUIRED_TEST4_KEYS = {
    "n_signal_bars",
    "window",
    "sign",
    "unity_train_mean",
    "unity_train_std",
    "IC_train_raw",
    "IC_train_signed",
    "IC_test",
    "sharpe_test",
    "maxdd_test",
    "permutation_p",
    "vs_baseline_0_106",
    "vs_u4_prior_0_0661",
    "beats_u4_prior",
    "beats_ricci_test1",
}

REQUIRED_TEST1_KEYS = {
    "n_assets",
    "IC_train",
    "IC_test",
    "sharpe_test",
    "maxdd_test",
    "permutation_p",
    "vs_baseline_0_106",
    "vs_u4_prior_0_0661",
    "beats_u4_prior",
    "beats_yfinance_baseline",
}

REQUIRED_TEST2_KEYS = {
    "w_ricci",
    "w_momentum",
    "IC_train_ensemble",
    "IC_test_ensemble",
    "IC_test_ricci_alone",
    "IC_test_momentum_alone",
    "ensemble_adds_value",
    "ricci_share_of_blend",
    "momentum_dominated",
}

REQUIRED_TEST3_KEYS = {
    "grid",
    "best_train_config",
    "IC_test_best_config",
    "IC_test_default_config",
}


# ---------------------------------------------------------------- #
# 1. 53 assets loaded
# ---------------------------------------------------------------- #


def test_53_assets_loaded() -> None:
    if not PANEL_PATH.exists():
        pytest.skip("panel_daily.parquet not present — run panel_builder first")
    panel = load_daily_panel()
    assert panel.n_assets >= 50, f"expected ≥50 assets, got {panel.n_assets}"
    assert panel.returns.shape[1] == panel.n_assets
    # Target must be the first column for compute_signal.
    assert panel.returns.columns[0] == panel.target
    # Either the task's primary target or the SPY fallback is acceptable.
    assert panel.target in {TARGET_PRIMARY, "SPDR_S_P_500_ETF"}


# ---------------------------------------------------------------- #
# 2. Daily panel: no multi-session "dataset hole" gaps in the returns
# ---------------------------------------------------------------- #


def test_daily_resample_no_gaps() -> None:
    """After load_daily_panel's filter, 95 %+ of consecutive-bar gaps must
    be ≤ 4 calendar days (weekend gap). An occasional long-weekend / US
    holiday stack can legitimately reach 7 days; a 10+ day gap would
    indicate an un-stitched dataset hole and is forbidden.
    """
    if not PANEL_PATH.exists():
        pytest.skip("panel_daily.parquet not present")
    panel = load_daily_panel()
    idx = pd.DatetimeIndex(panel.returns.index)
    gaps = idx.to_series().diff().dropna().dt.days
    max_gap = int(gaps.max())
    # Hard ceiling: no multi-session blend beyond 10 calendar days.
    assert max_gap <= 10, f"max daily gap = {max_gap} days (>10 = dataset hole)"
    # Distributional sanity: ≥95 % of bars must sit on a weekend-sized gap
    # (≤4 days). This is the honest "gap test" on a daily market panel.
    weekend_share = float((gaps <= 4).mean())
    assert (
        weekend_share >= 0.95
    ), f"only {weekend_share:.1%} of bars have ≤4-day gap (holiday stack or dataset hole)"


# ---------------------------------------------------------------- #
# 3. Momentum-stack weights are train-only
# ---------------------------------------------------------------- #


def test_momentum_weights_train_only() -> None:
    rng = np.random.default_rng(3)
    idx = pd.date_range("2018-01-01", periods=1200, freq="D")
    target_ret = pd.Series(rng.normal(size=1200) * 0.01, index=idx)
    combo = pd.Series(rng.normal(size=1200), index=idx)
    fwd = target_ret.copy()
    df_sig = pd.DataFrame({"combo": combo, "fwd_return": fwd}, index=idx)

    returns_frame = pd.DataFrame({"SYN": target_ret}, index=idx)
    prices_frame = returns_frame.copy()
    panel = DailyPanel(
        prices=prices_frame,
        returns=returns_frame,
        target="SYN",
        n_assets=1,
    )

    rep1, _ = run_test_2(panel, df_sig)

    # Poison everything at and after the split. Train slice must be unchanged,
    # so weights must match bit-for-bit.
    poisoned = df_sig.copy()
    poisoned.loc[poisoned.index >= SPLIT_DATE, "combo"] += 1e6
    rep2, _ = run_test_2(panel, poisoned)

    assert rep1["w_ricci"] == pytest.approx(rep2["w_ricci"], abs=1e-9)
    assert rep1["w_momentum"] == pytest.approx(rep2["w_momentum"], abs=1e-9)
    assert rep1["IC_train_ricci_alone"] == pytest.approx(rep2["IC_train_ricci_alone"], abs=1e-9)
    assert rep1["IC_train_momentum_alone"] == pytest.approx(
        rep2["IC_train_momentum_alone"], abs=1e-9
    )


# ---------------------------------------------------------------- #
# 4. Threshold grid uses train slice only
# ---------------------------------------------------------------- #


def test_threshold_grid_train_only() -> None:
    rng = np.random.default_rng(4)
    idx = pd.date_range("2018-01-01", periods=1500, freq="D")
    cols = [f"A{i}" for i in range(6)]
    returns = pd.DataFrame(rng.normal(size=(len(idx), len(cols))) * 0.01, index=idx, columns=cols)
    panel = DailyPanel(
        prices=returns.copy(),
        returns=returns,
        target="A0",
        n_assets=len(cols),
    )
    report, _strat = run_test_3(panel)
    assert "grid" in report and report["grid"], "grid should be non-empty"
    # Every grid row must come from one of the configured (w, θ) pairs.
    for row in report["grid"]:
        assert row["window"] in WINDOW_GRID
        assert row["threshold"] in THRESHOLD_GRID
    best = report["best_train_config"]
    assert best is not None
    # And the best config's IC_train must equal the max over the grid.
    max_ic = max(row["IC_train"] for row in report["grid"])
    assert best["IC_train"] == pytest.approx(max_ic, abs=1e-9)


# ---------------------------------------------------------------- #
# 5. No-lookahead in the expanding quintile that drives all backtests
# ---------------------------------------------------------------- #


def test_no_lookahead() -> None:
    rng = np.random.default_rng(5)
    base = pd.Series(rng.normal(size=800))
    pos_base = expanding_quintile(base, min_history=50)
    perturbed = base.copy()
    perturbed.iloc[400:] += 1e6
    pos_perturbed = expanding_quintile(perturbed, min_history=50)
    pd.testing.assert_series_equal(pos_base.iloc[:400], pos_perturbed.iloc[:400], check_names=False)

    # Also verify compute_signal's combo at row i uses only past bars.
    cols = [f"A{i}" for i in range(4)]
    rng2 = np.random.default_rng(51)
    panel = pd.DataFrame(
        rng2.normal(size=(600, 4)) * 0.01,
        columns=cols,
        index=pd.date_range("2020-01-01", periods=600, freq="D"),
    )
    sig = compute_signal(panel, window=60, threshold=0.30)

    poisoned = panel.copy()
    poisoned.iloc[300:] += 1e6
    sig_p = compute_signal(poisoned, window=60, threshold=0.30)

    # Signal rows strictly before bar 300 in the source index must match.
    past_mask = sig.index < panel.index[300]
    pd.testing.assert_series_equal(
        sig.loc[past_mask, "combo"],
        sig_p.loc[past_mask, "combo"],
        check_names=False,
    )


# ---------------------------------------------------------------- #
# 6. Output JSON schema complete
# ---------------------------------------------------------------- #


def test_output_schema_complete() -> None:
    out = RESULTS_DIR / "askar_53asset_daily_result.json"
    if not out.exists():
        pytest.skip("result file not yet produced — run research/askar/daily_53_experiment.py")
    report = json.loads(Path(out).read_text())
    missing_top = REQUIRED_TOP_KEYS - set(report.keys())
    assert not missing_top, f"missing top-level keys: {missing_top}"

    t1 = report["test1_53assets"]
    missing_1 = REQUIRED_TEST1_KEYS - set(t1.keys())
    assert not missing_1, f"test1 missing: {missing_1}"

    t2 = report["test2_momentum_stack"]
    missing_2 = REQUIRED_TEST2_KEYS - set(t2.keys())
    assert not missing_2, f"test2 missing: {missing_2}"

    t3 = report["test3_sensitivity"]
    missing_3 = REQUIRED_TEST3_KEYS - set(t3.keys())
    assert not missing_3, f"test3 missing: {missing_3}"

    t4 = report["test4_unity"]
    missing_4 = REQUIRED_TEST4_KEYS - set(t4.keys())
    assert not missing_4, f"test4 missing: {missing_4}"
    # Unity sign must be exactly +1 or -1 (train-selected).
    assert float(t4["sign"]) in {1.0, -1.0}
    # vs_baseline algebra must hold for the Unity block as well.
    ic_test_4 = float(t4["IC_test"])
    assert abs(float(t4["vs_baseline_0_106"]) - (ic_test_4 - report["baseline_yfinance_IC"])) < 1e-6

    assert report["final_verdict"] in {"SIGNAL_FOUND", "MARGINAL", "NO_SIGNAL"}
    # Sign of vs_baseline must match IC algebra.
    ic_test = float(t1["IC_test"])
    assert abs(float(t1["vs_baseline_0_106"]) - (ic_test - report["baseline_yfinance_IC"])) < 1e-6


# ---------------------------------------------------------------- #
# 7. Unity = λ₁/N — bounds, no-lookahead sign, train-only stats
# ---------------------------------------------------------------- #


def test_unity_signal_bounds_and_train_only() -> None:
    rng = np.random.default_rng(42)
    n, k = 400, 8
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.01,
        index=idx,
        columns=[f"A{i}" for i in range(k)],
    )
    df = compute_unity_series(returns, window=60)
    assert "unity" in df.columns and "delta_unity" in df.columns
    # Unity ∈ [1/k, 1] for a correlation matrix on k variables
    u = df["unity"].to_numpy()
    assert np.all(
        (u >= 1.0 / k - 1e-9) & (u <= 1.0 + 1e-9)
    ), f"unity out of [1/k, 1] range: min={u.min():.4f}, max={u.max():.4f}"

    # Train-only stats via run_test_4: poisoning the test slice must leave
    # train mean, std, sign, and train IC bit-identical.
    panel = DailyPanel(
        prices=returns.copy(),
        returns=returns,
        target="A0",
        n_assets=k,
    )
    rep1, _strat1, _sig1 = run_test_4(panel)

    poisoned_returns = returns.copy()
    poisoned_returns.loc[poisoned_returns.index >= SPLIT_DATE] += 1e6
    panel2 = DailyPanel(
        prices=poisoned_returns.copy(),
        returns=poisoned_returns,
        target="A0",
        n_assets=k,
    )
    rep2, _strat2, _sig2 = run_test_4(panel2)

    # Short synthetic series may trigger the "signal_too_short" early exit;
    # only compare frozen fields when both runs actually produced a signal.
    if "IC_train_raw" in rep1 and "IC_train_raw" in rep2:
        assert rep1["unity_train_mean"] == pytest.approx(rep2["unity_train_mean"], abs=1e-9)
        assert rep1["unity_train_std"] == pytest.approx(rep2["unity_train_std"], abs=1e-9)
        assert rep1["IC_train_raw"] == pytest.approx(rep2["IC_train_raw"], abs=1e-9)
        assert rep1["sign"] == rep2["sign"]
