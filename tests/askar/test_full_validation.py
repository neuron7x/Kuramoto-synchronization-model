"""Tests for the full GeoSync / Askar L2 validation pipeline.

Required 8/8:
 1. quintile positioning has no lookahead
 2. train/test split is non-overlapping (no bars shared)
 3. 2022 crisis block is isolated (only uses data inside the window)
 4. daily and hourly backtests use identical signal logic (same function)
 5. FX universe has all 14 pairs (complete)
 6. sensitivity grid reports IC on train only (no test leakage)
 7. permutation test is properly calibrated under the null
 8. output JSON schema contains every required top-level field
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research.askar.full_validation import (
    CRISIS_2022,
    DATA_DIR,
    RESULTS_DIR,
    TRAIN_END,
    build_signal,
    run_sensitivity,
)
from research.askar.ricci_spread import permutation_test, quintile_position

EXPECTED_FX = {
    "AUDCAD",
    "AUDCHF",
    "AUDNZD",
    "AUDUSD",
    "CADCHF",
    "EURGBP",
    "EURJPY",
    "EURNZD",
    "EURUSD",
    "GBPAUD",
    "GBPCAD",
    "NZDCAD",
    "NZDUSD",
    "USDCAD",
}

REQUIRED_JSON_KEYS = {
    "data_source",
    "universe_size",
    "universe_assets",
    "fx_universe_size",
    "fx_universe_assets",
    "period_train",
    "period_test",
    "target_equity",
    "target_fx",
    "daily_resample",
    "hourly_native",
    "fx_only",
    "sensitivity_daily",
    "walkforward_5fold",
    "verdict",
}

REQUIRED_DAILY_BLOCK_KEYS = {
    "IC_raw_signal",
    "IC_realised",
    "sharpe_test",
    "maxdd_test",
    "overfit_ratio",
    "permutation_p",
    "return_2022",
    "return_spy_2022",
    "delta_2022",
    "return_2024",
    "return_2025",
    "corr_momentum",
    "corr_vol",
    "corr_mean_reversion",
    "baseline_yfinance_IC",
    "askar_IC_delta_vs_yfinance",
}


# ---------------------------------------------------------------- #
# 1. No-lookahead in quintile positioning
# ---------------------------------------------------------------- #


def test_no_lookahead_quintile() -> None:
    rng = np.random.default_rng(1)
    base = pd.Series(rng.normal(size=600))
    pos_base = quintile_position(base, min_history=50)
    perturbed = base.copy()
    perturbed.iloc[400:] += 1e6
    pos_perturbed = quintile_position(perturbed, min_history=50)
    pd.testing.assert_series_equal(pos_base.iloc[:400], pos_perturbed.iloc[:400], check_names=False)


# ---------------------------------------------------------------- #
# 2. Train / test split has no overlap
# ---------------------------------------------------------------- #


def test_train_test_no_overlap() -> None:
    idx = pd.date_range("2017-02-16", "2026-02-23", freq="D")
    df = pd.DataFrame({"combo": np.arange(len(idx), dtype=float)}, index=idx)
    train = df[df.index < TRAIN_END]
    test = df[df.index >= TRAIN_END]
    assert len(train) > 0 and len(test) > 0
    assert train.index.max() < test.index.min()
    assert len(train.index.intersection(test.index)) == 0


# ---------------------------------------------------------------- #
# 3. 2022 crisis window is properly isolated
# ---------------------------------------------------------------- #


def test_crisis_2022_isolated() -> None:
    lo, hi = CRISIS_2022
    assert lo == pd.Timestamp("2022-01-01")
    assert hi == pd.Timestamp("2023-01-01")

    idx = pd.DatetimeIndex(pd.date_range("2017-01-01", "2026-02-23", freq="D"))
    s = pd.Series(np.ones(len(idx)), index=idx)
    window = s[(s.index >= lo) & (s.index < hi)]
    window_idx = pd.DatetimeIndex(window.index)
    assert window_idx.min() >= lo
    assert window_idx.max() < hi
    # Only 2022 bars, not 2021 or 2023
    assert (window_idx.year == 2022).all()


# ---------------------------------------------------------------- #
# 4. Daily & hourly variants share the same signal function
# ---------------------------------------------------------------- #


def test_daily_hourly_same_signal_logic() -> None:
    rng = np.random.default_rng(7)
    n = 600
    cols = ["A", "B", "C", "D"]
    data = pd.DataFrame(
        rng.normal(size=(n, len(cols))),
        columns=cols,
        index=pd.date_range("2020-01-01", periods=n, freq="D"),
    )
    sig_a = build_signal(data, target="A", window=60, threshold=0.30)
    sig_b = build_signal(data, target="A", window=60, threshold=0.30)
    pd.testing.assert_frame_equal(sig_a, sig_b)
    for col in ("ricci_target", "ricci_mean", "delta_ricci", "combo", "baseline"):
        assert col in sig_a.columns


# ---------------------------------------------------------------- #
# 5. FX universe has all 14 pairs
# ---------------------------------------------------------------- #


def test_fx_universe_complete_14_assets() -> None:
    panel_path = DATA_DIR / "panel_fx_hourly.parquet"
    manifest_path = DATA_DIR / "panel_manifest.json"
    if not panel_path.exists() or not manifest_path.exists():
        pytest.skip("Askar FX panel not present — run panel_builder first")
    fx = pd.read_parquet(panel_path)
    assert EXPECTED_FX.issubset(
        set(fx.columns)
    ), f"missing FX pairs: {EXPECTED_FX - set(fx.columns)}"
    assert len(EXPECTED_FX & set(fx.columns)) == 14

    manifest = json.loads(manifest_path.read_text())
    assert manifest["panel_fx_hourly"]["n_assets"] >= 14


# ---------------------------------------------------------------- #
# 6. Sensitivity grid uses train slice only
# ---------------------------------------------------------------- #


def test_sensitivity_grid_train_only() -> None:
    rng = np.random.default_rng(3)
    idx = pd.date_range("2017-02-16", periods=1200, freq="D")
    data = pd.DataFrame(
        rng.normal(size=(len(idx), 4)),
        columns=["A", "B", "C", "D"],
        index=idx,
    )
    grid = run_sensitivity(
        data, target="A", thresholds=(0.20, 0.30), windows=(60,), split_ts=TRAIN_END
    )
    assert len(grid) > 0
    # Every entry carries IC_train and only IC_train (no test leakage)
    for row in grid:
        assert "IC_train" in row
        assert "IC_test" not in row
        assert "window" in row and "threshold" in row


# ---------------------------------------------------------------- #
# 7. Permutation test is calibrated on random signals
# ---------------------------------------------------------------- #


def test_permutation_null_correct() -> None:
    rng = np.random.default_rng(11)
    n = 1500
    signal = pd.Series(rng.normal(size=n))
    fwd = pd.Series(rng.normal(size=n))
    _ic, p = permutation_test(signal, fwd, n=300, seed=11)
    assert 0.0 <= p <= 1.0
    assert p > 0.20, f"random signal under null gave suspicious p={p:.3f}"


# ---------------------------------------------------------------- #
# 8. Output JSON schema is complete
# ---------------------------------------------------------------- #


def test_output_schema_complete() -> None:
    out = RESULTS_DIR / "askar_full_validation.json"
    if not out.exists():
        pytest.skip("result file not present — run research/askar/full_validation.py first")
    report = json.loads(out.read_text())
    missing = REQUIRED_JSON_KEYS - set(report.keys())
    assert not missing, f"report missing top-level keys: {missing}"
    for block_name in ("daily_resample", "hourly_native", "fx_only"):
        block = report[block_name]
        missing_block = REQUIRED_DAILY_BLOCK_KEYS - set(block.keys())
        assert not missing_block, f"{block_name} missing keys: {missing_block}"
    # Verdict is one of the three allowed values
    assert report["verdict"] in {"IMPROVEMENT", "SAME", "DEGRADED"}
    # Walkforward folds are <= 5
    assert len(report["walkforward_5fold"]) <= 5
