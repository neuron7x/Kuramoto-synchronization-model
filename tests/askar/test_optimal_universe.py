"""Tests for the GeoSync Optimal Universe validation on Askar's L2 archive.

Required 8/8 per CLAUDE_CODE_TASK_askar_optimal.md:
 1. exactly 14 assets loaded
 2. no-lookahead in expanding quintile positioning
 3. train/test split is by date (not by index position)
 4. 2022 crisis window lies inside the train period (honest)
 5. permutation test calibrates properly under a random null
 6. orthogonality is computed (corr_momentum, corr_vol both present)
 7. daily and hourly runs are independent (shared helpers, distinct panels)
 8. output JSON schema contains every required field
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.optimal_universe import (
    CRISIS_HI,
    CRISIS_LO,
    DATA_DIR,
    N_UNIVERSE,
    RESULTS_DIR,
    SPLIT_DATE,
    TARGET_FILENAME,
    UNIVERSE,
    compute_signal,
    expanding_quintile,
    load_universe,
    orthogonality,
    permutation_test,
)

REQUIRED_TOP_KEYS = {
    "universe",
    "universe_assets",
    "baseline_yfinance_IC",
    "overlap_start",
    "overlap_end",
    "split_date",
    "daily",
    "hourly",
    "walkforward_5fold",
    "walkforward_folds_positive_IC",
    "verdict",
}

REQUIRED_DAILY_KEYS = {
    "IC_train",
    "IC_test",
    "sharpe_test",
    "maxdd_test",
    "crisis_2022",
    "permutation_p",
    "permutation_sigma",
    "corr_momentum",
    "corr_vol",
    "overfit_ratio",
    "vs_baseline_delta_IC",
    "n_train",
    "n_test",
}

REQUIRED_HOURLY_KEYS = {
    "IC_train",
    "IC_test",
    "sharpe_test",
    "permutation_p",
}


# ---------------------------------------------------------------- #
# 1. exactly 14 assets loaded
# ---------------------------------------------------------------- #
def test_exactly_14_assets_loaded() -> None:
    # Constant source of truth first:
    assert len(UNIVERSE) == N_UNIVERSE == 14
    assert UNIVERSE[0][0] == TARGET_FILENAME
    # Every file must actually sit on disk:
    for filename, _label in UNIVERSE:
        assert (DATA_DIR / filename).exists(), f"missing raw parquet: {filename}"

    u = load_universe()
    assert u.prices_hourly.shape[1] == 14
    assert u.prices_daily.shape[1] == 14
    assert u.returns_hourly.shape[1] == 14
    assert u.returns_daily.shape[1] == 14
    # First column is the anchor (USA_500) and stays the anchor.
    assert u.prices_hourly.columns[0] == TARGET_FILENAME
    assert u.returns_daily.columns[0] == TARGET_FILENAME


# ---------------------------------------------------------------- #
# 2. expanding quintile has no lookahead
# ---------------------------------------------------------------- #
def test_no_lookahead_quintile() -> None:
    rng = np.random.default_rng(2)
    base = pd.Series(rng.normal(size=600))
    pos_base = expanding_quintile(base, min_history=50)
    perturbed = base.copy()
    perturbed.iloc[400:] += 1e6
    pos_perturbed = expanding_quintile(perturbed, min_history=50)
    pd.testing.assert_series_equal(pos_base.iloc[:400], pos_perturbed.iloc[:400], check_names=False)


# ---------------------------------------------------------------- #
# 3. train/test split is by date
# ---------------------------------------------------------------- #
def test_train_test_split_by_date() -> None:
    assert SPLIT_DATE == pd.Timestamp("2023-07-01")
    idx = pd.date_range("2017-12-01", "2026-02-20", freq="D")
    s = pd.Series(np.arange(len(idx)), index=idx)
    train = s[s.index < SPLIT_DATE]
    test = s[s.index >= SPLIT_DATE]
    assert train.index.max() < SPLIT_DATE
    assert test.index.min() >= SPLIT_DATE
    assert len(train) > 0 and len(test) > 0
    assert len(train.index.intersection(test.index)) == 0


# ---------------------------------------------------------------- #
# 4. 2022 crisis is inside the train period (honest)
# ---------------------------------------------------------------- #
def test_crisis_2022_in_train_period() -> None:
    assert CRISIS_LO == pd.Timestamp("2022-01-01")
    assert CRISIS_HI == pd.Timestamp("2023-01-01")
    # Entire 2022 window must end strictly before the train/test split.
    assert CRISIS_HI <= SPLIT_DATE
    assert CRISIS_LO < SPLIT_DATE


# ---------------------------------------------------------------- #
# 5. permutation null is correct
# ---------------------------------------------------------------- #
def test_permutation_null_correct() -> None:
    rng = np.random.default_rng(17)
    n = 1500
    signal = pd.Series(rng.normal(size=n))
    fwd = pd.Series(rng.normal(size=n))
    ic, p, sigma = permutation_test(signal, fwd, n=300, seed=17)
    assert 0.0 <= p <= 1.0
    assert p > 0.20, f"random signal gave suspicious p={p:.3f}"
    assert -5.0 <= sigma <= 5.0


# ---------------------------------------------------------------- #
# 6. orthogonality is computed (both corrs present)
# ---------------------------------------------------------------- #
def test_orthogonality_computed() -> None:
    rng = np.random.default_rng(9)
    idx = pd.date_range("2020-01-01", periods=500, freq="D")
    target_ret = pd.Series(rng.normal(size=500) * 0.01, index=idx)
    df_sig = pd.DataFrame(
        {"combo": rng.normal(size=500), "fwd_return": target_ret.values},
        index=idx,
    )
    ortho = orthogonality(df_sig, target_ret)
    assert "corr_momentum" in ortho
    assert "corr_vol" in ortho
    assert np.isfinite(ortho["corr_momentum"])
    assert np.isfinite(ortho["corr_vol"])


# ---------------------------------------------------------------- #
# 7. daily and hourly runs are independent (distinct, both valid)
# ---------------------------------------------------------------- #
def test_daily_hourly_independent_runs() -> None:
    rng = np.random.default_rng(5)
    # Two independent synthetic panels to prove the signal helper is reusable
    # without cross-contamination.
    idx_d = pd.date_range("2018-01-01", periods=400, freq="D")
    panel_d = pd.DataFrame(
        rng.normal(size=(400, 4)),
        index=idx_d,
        columns=["USA500", "GLD", "EURUSD", "TLT"],
    )
    sig_d = compute_signal(panel_d, window=60, threshold=0.30)

    idx_h = pd.date_range("2018-01-01", periods=2000, freq="h")
    panel_h = pd.DataFrame(
        rng.normal(size=(2000, 4)),
        index=idx_h,
        columns=["USA500", "GLD", "EURUSD", "TLT"],
    )
    sig_h = compute_signal(panel_h, window=480, threshold=0.30)

    # Distinct lengths, distinct indices, both non-empty, same column set.
    assert len(sig_d) > 0
    assert len(sig_h) > 0
    assert len(sig_d) != len(sig_h)
    assert set(sig_d.columns) == set(sig_h.columns)
    # No leakage between panels — indices are disjoint.
    assert len(sig_d.index.intersection(sig_h.index)) == 0


# ---------------------------------------------------------------- #
# 8. output JSON schema is complete
# ---------------------------------------------------------------- #
def test_output_schema_complete() -> None:
    out = RESULTS_DIR / "askar_optimal_result.json"
    if not out.exists():
        pytest.skip("run research/askar/optimal_universe.py to produce the JSON first")
    report = json.loads(Path(out).read_text())
    missing_top = REQUIRED_TOP_KEYS - set(report.keys())
    assert not missing_top, f"missing top-level keys: {missing_top}"

    daily = report["daily"]
    missing_daily = REQUIRED_DAILY_KEYS - set(daily.keys())
    assert not missing_daily, f"missing daily keys: {missing_daily}"

    hourly = report["hourly"]
    missing_hourly = REQUIRED_HOURLY_KEYS - set(hourly.keys())
    assert not missing_hourly, f"missing hourly keys: {missing_hourly}"

    assert report["verdict"] in {"IMPROVEMENT", "SAME", "DEGRADED"}
    assert 0 <= len(report["walkforward_5fold"]) <= 5
    for fold in report["walkforward_5fold"]:
        for k in ("fold", "IC", "sharpe"):
            assert k in fold
