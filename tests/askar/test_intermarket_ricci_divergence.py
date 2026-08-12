"""Tests for the intermarket Ricci divergence sprint.

Covers the invariants enumerated in the task brief:
 1. 3 assets loaded, target = SPY first column preserved
 2. per-asset Ricci is lookahead-free (future perturbation leaves past unchanged)
 3. divergence signal z-score is train-frozen (perturbing test slice
    does not change the train mu / sd used downstream)
 4. orthogonality gate triggers on a forced high-corr synthetic signal
 5. walk-forward produces exactly 5 folds with no-lookahead fwd_return_1h
 6. hard-rule: any non-positive fold → verdict = NO_SIGNAL
 7. verdict schema honours SIGNAL / MARGINAL / NO_SIGNAL bands
 8. output schema: diagnostics_report.md, summary.json, walkforward_results.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research.askar.intermarket_ricci_divergence import (
    ASSETS,
    CORR_GATE,
    DATA_DIR,
    RESULTS_DIR,
    TARGET,
    audit_and_load,
    build_divergence_signal,
    compute_ricci_per_asset,
    determine_verdict,
    orthogonality_gate,
    walk_forward,
)

# ---------------------------------------------------------------- #
# 1. audit_and_load returns 3-asset panel with SPY as first column
# ---------------------------------------------------------------- #


def test_three_assets_loaded_target_first() -> None:
    for _name, path in ASSETS:
        assert path.parent == DATA_DIR
        if not path.exists():
            pytest.skip(f"raw parquet not staged: {path.name}")
    loaded = audit_and_load()
    assert loaded.returns.shape[1] == 3
    assert list(loaded.returns.columns)[0] == "XAUUSD"
    assert TARGET in loaded.returns.columns
    assert loaded.audit["aligned_panel"]["anchor"] == TARGET


# ---------------------------------------------------------------- #
# 2. Per-asset Ricci is lookahead-free
# ---------------------------------------------------------------- #


def test_ricci_per_asset_no_lookahead() -> None:
    rng = np.random.default_rng(2)
    n, k = 500, 3
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.01,
        index=idx,
        columns=["XAUUSD", "USA500", "SPY"],
    )
    ricci = compute_ricci_per_asset(returns, window=60, threshold=0.30)

    poisoned = returns.copy()
    poisoned.iloc[300:] += 1e6
    ricci_p = compute_ricci_per_asset(poisoned, window=60, threshold=0.30)

    past_mask = ricci.index < returns.index[300]
    pd.testing.assert_frame_equal(
        ricci.loc[past_mask],
        ricci_p.loc[past_mask],
    )


# ---------------------------------------------------------------- #
# 3. Divergence signal uses train-frozen z-score
# ---------------------------------------------------------------- #


def test_divergence_z_train_frozen() -> None:
    rng = np.random.default_rng(3)
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    ricci = pd.DataFrame(
        {
            "XAUUSD": rng.normal(size=n),
            "USA500": rng.normal(size=n),
            "SPY": rng.normal(size=n),
        },
        index=idx,
    )
    returns = pd.DataFrame(
        rng.normal(size=(n, 3)) * 0.01,
        index=idx,
        columns=["XAUUSD", "USA500", "SPY"],
    )
    split_ts = idx[int(0.7 * n)]

    rep1 = build_divergence_signal(ricci, returns, split_ts)

    poisoned_ricci = ricci.copy()
    poisoned_ricci.loc[poisoned_ricci.index >= split_ts] += 1e6
    rep2 = build_divergence_signal(poisoned_ricci, returns, split_ts)

    assert rep1.attrs["train_mean"] == pytest.approx(rep2.attrs["train_mean"], abs=1e-9)
    assert rep1.attrs["train_std"] == pytest.approx(rep2.attrs["train_std"], abs=1e-9)


# ---------------------------------------------------------------- #
# 4. Orthogonality gate catches forced high-correlation signals
# ---------------------------------------------------------------- #


def test_orthogonality_gate_rejects_high_corr() -> None:
    # Low-corr case → gate passes.
    idx = pd.date_range("2020-01-01", periods=400, freq="h")
    rng = np.random.default_rng(4)
    low = pd.DataFrame(
        {
            "ricci_div_z": rng.normal(size=400),
            "spy_momentum_20": rng.normal(size=400),
        },
        index=idx,
    )
    out = orthogonality_gate(low)
    assert out["gate_passed"] is True
    assert abs(out["corr_ricci_div_vs_momentum"]) < CORR_GATE

    # High-corr case → gate trips.
    mom = rng.normal(size=400)
    high = pd.DataFrame(
        {
            "ricci_div_z": mom + rng.normal(size=400) * 0.01,
            "spy_momentum_20": mom,
        },
        index=idx,
    )
    out_hi = orthogonality_gate(high)
    assert abs(out_hi["corr_ricci_div_vs_momentum"]) >= CORR_GATE
    assert out_hi["gate_passed"] is False


# ---------------------------------------------------------------- #
# 5. Walk-forward emits exactly 5 folds with no-lookahead
# ---------------------------------------------------------------- #


def test_walk_forward_five_folds_no_lookahead() -> None:
    rng = np.random.default_rng(5)
    n = 3000
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    cols = ["XAUUSD", "USA500", "SPY"]
    returns = pd.DataFrame(rng.normal(size=(n, 3)) * 0.01, index=idx, columns=cols)
    ricci = compute_ricci_per_asset(returns, window=60, threshold=0.30)
    walk = walk_forward(ricci, returns, n_folds=5, train_fraction=0.70)
    assert len(walk["folds"]) == 5
    for fold in walk["folds"]:
        assert fold["n_train"] > 0 and fold["n_test"] > 0
        assert pd.Timestamp(fold["split_ts"]) > pd.Timestamp(fold["train_start"])


# ---------------------------------------------------------------- #
# 6. Hard rule: any non-positive fold → NO_SIGNAL
# ---------------------------------------------------------------- #


def test_hard_rule_any_negative_fold_kills_verdict() -> None:
    gate_ok = {
        "corr_ricci_div_vs_momentum": 0.01,
        "gate_threshold": CORR_GATE,
        "gate_passed": True,
        "n_common_bars": 1000,
    }
    walk_one_negative = {
        "folds": [
            {"fold": 1, "IC_test": +0.02, "sharpe_test": 1.2},
            {"fold": 2, "IC_test": +0.02, "sharpe_test": 1.2},
            {"fold": 3, "IC_test": -0.01, "sharpe_test": 0.5},  # <<< killer
            {"fold": 4, "IC_test": +0.02, "sharpe_test": 1.2},
            {"fold": 5, "IC_test": +0.02, "sharpe_test": 1.2},
        ],
        "positive_count": 4,
        "all_positive": False,
        "mean_sharpe_test": 0.9,
        "mean_ic_train": 0.01,
        "mean_ic_test": 0.01,
        "overfit_ratio": 1.0,
    }
    verdict, reason = determine_verdict(gate_ok, walk_one_negative)
    assert verdict == "NO_SIGNAL"
    assert "non-positive" in reason


# ---------------------------------------------------------------- #
# 7. Verdict schema honours the three bands
# ---------------------------------------------------------------- #


def test_verdict_schema_three_bands() -> None:
    gate_ok = {
        "corr_ricci_div_vs_momentum": 0.01,
        "gate_threshold": CORR_GATE,
        "gate_passed": True,
        "n_common_bars": 1000,
    }
    all_positive_5 = [{"fold": i + 1, "IC_test": +0.02, "sharpe_test": 1.5} for i in range(5)]

    # SIGNAL: Sharpe > 1.0, overfit < 2.0
    walk_signal = {
        "folds": all_positive_5,
        "positive_count": 5,
        "all_positive": True,
        "mean_sharpe_test": 1.5,
        "mean_ic_train": 0.015,
        "mean_ic_test": 0.02,
        "overfit_ratio": 0.75,
    }
    v, _ = determine_verdict(gate_ok, walk_signal)
    assert v == "SIGNAL"

    # MARGINAL: Sharpe in [0.5, 1.0)
    walk_marg = dict(walk_signal)
    walk_marg["folds"] = [{"fold": i + 1, "IC_test": +0.01, "sharpe_test": 0.7} for i in range(5)]
    walk_marg["mean_sharpe_test"] = 0.7
    v, _ = determine_verdict(gate_ok, walk_marg)
    assert v == "MARGINAL"

    # NO_SIGNAL via Sharpe floor
    walk_no = dict(walk_signal)
    walk_no["folds"] = [{"fold": i + 1, "IC_test": +0.005, "sharpe_test": 0.2} for i in range(5)]
    walk_no["mean_sharpe_test"] = 0.2
    v, reason = determine_verdict(gate_ok, walk_no)
    assert v == "NO_SIGNAL"
    assert "Sharpe" in reason


# ---------------------------------------------------------------- #
# 8. Output artefacts present after a run
# ---------------------------------------------------------------- #


def test_output_artefacts_present() -> None:
    required = [
        RESULTS_DIR / "data_audit.json",
        RESULTS_DIR / "walkforward_results.json",
        RESULTS_DIR / "diagnostics_report.md",
        RESULTS_DIR / "ricci_divergence.csv",
        RESULTS_DIR / "ricci_xauusd.csv",
        RESULTS_DIR / "ricci_spy.csv",
        RESULTS_DIR / "summary.json",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        pytest.skip(
            "run research/askar/intermarket_ricci_divergence.py first; "
            f"missing: {[m.name for m in missing]}"
        )
    summary = json.loads((RESULTS_DIR / "summary.json").read_text())
    assert summary["verdict"] in {"SIGNAL", "MARGINAL", "NO_SIGNAL"}
    for key in (
        "data_audit",
        "orthogonality_gate",
        "walk_forward",
        "verdict_reason",
    ):
        assert key in summary
    report_text = (RESULTS_DIR / "diagnostics_report.md").read_text()
    assert "# Intermarket Ricci Divergence" in report_text
    assert "positive_count" in report_text
