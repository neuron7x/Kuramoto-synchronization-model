# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the DRO-ARA calibration rigor module."""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.dro_ara_calibration.rigor import (
    baseline_buy_hold_sharpe,
    baseline_random_gate_sharpe,
    bootstrap_sharpe_ci,
    deflated_sharpe_wrapper,
    min_detectable_sharpe,
    surrogate_null_sharpe,
)
from experiments.dro_ara_calibration.rigor_report import (
    benjamini_hochberg,
    rigor_for_grid,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_returns_degenerate_for_tiny_sample() -> None:
    """n < 3 folds → CI fields NaN, no crash."""
    rep = bootstrap_sharpe_ci(np.array([1.0, -1.0], dtype=np.float64))
    assert rep.n_bootstraps == 0
    assert not rep.significant_at_95


def test_bootstrap_ci_contains_point_for_iid_sample() -> None:
    """For i.i.d. sample the 95 % CI is centred near the mean."""
    rng = np.random.default_rng(42)
    sample = rng.normal(0.5, 0.2, size=60)
    rep = bootstrap_sharpe_ci(sample, n_bootstraps=500, block_size=3)
    assert rep.ci_lo_95 <= rep.sharpe_point <= rep.ci_hi_95
    assert rep.ci_lo_95 > 0.0  # 0.5 ± 0.2 on 60 draws should exclude 0


def test_bootstrap_zero_mean_ci_spans_zero() -> None:
    """Zero-mean sample should have a CI that straddles 0 (not significant)."""
    rng = np.random.default_rng(17)
    sample = rng.normal(0.0, 1.0, size=40)
    rep = bootstrap_sharpe_ci(sample, n_bootstraps=500, block_size=3)
    assert not rep.significant_at_95


# ---------------------------------------------------------------------------
# Surrogate null
# ---------------------------------------------------------------------------


def test_surrogate_null_p_value_large_for_small_effect() -> None:
    """When observed mean ≈ 0, sign-flip null gives p-value close to 1."""
    rng = np.random.default_rng(3)
    sample = rng.normal(0.0, 1.0, size=30)
    rep = surrogate_null_sharpe(sample, n_surrogates=500)
    assert rep.p_value_two_sided > 0.1


def test_surrogate_null_p_value_small_for_large_effect() -> None:
    """With uniformly positive sample, the sign-flip null rejects H0."""
    sample = np.ones(20, dtype=np.float64)
    rep = surrogate_null_sharpe(sample, n_surrogates=500)
    # P(mean(sign-flipped) >= 1.0) = P(all +1) = 2/2^20 ≈ 2e-6
    assert rep.p_value_two_sided < 1e-4


# ---------------------------------------------------------------------------
# Deflated Sharpe
# ---------------------------------------------------------------------------


def test_deflated_sharpe_positive_grows_with_n_trials() -> None:
    """Expected max under N independent trials grows with N."""
    a = deflated_sharpe_wrapper(0.5, n_trials=10, n_observations=100)
    b = deflated_sharpe_wrapper(0.5, n_trials=1000, n_observations=100)
    assert b.expected_max_sharpe_under_null > a.expected_max_sharpe_under_null


def test_deflated_sharpe_probability_real_bounded_0_1() -> None:
    rep = deflated_sharpe_wrapper(2.0, n_trials=50, n_observations=200)
    assert 0.0 <= rep.probability_edge_is_real <= 1.0


# ---------------------------------------------------------------------------
# Power analysis
# ---------------------------------------------------------------------------


def test_min_detectable_sharpe_shrinks_with_more_observations() -> None:
    """More observations → smaller minimum detectable effect."""
    a = min_detectable_sharpe(0.0, n_observations=50, sigma_per_obs=0.01)
    b = min_detectable_sharpe(0.0, n_observations=500, sigma_per_obs=0.01)
    assert b.min_detectable_sharpe_annualised < a.min_detectable_sharpe_annualised


def test_min_detectable_sharpe_handles_degenerate() -> None:
    rep = min_detectable_sharpe(0.0, n_observations=2, sigma_per_obs=0.0)
    assert not rep.is_adequately_powered


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_buy_hold_sharpe_positive_on_upward_drift() -> None:
    """Monotonically upward prices yield a clearly positive Sharpe."""
    prices = np.linspace(100.0, 110.0, 200)
    sh = baseline_buy_hold_sharpe(prices)
    assert sh > 0.0


def test_buy_hold_sharpe_zero_on_constant() -> None:
    sh = baseline_buy_hold_sharpe(np.full(50, 100.0))
    assert sh == 0.0


def test_random_gate_sharpe_runs_and_is_finite() -> None:
    rng = np.random.default_rng(7)
    prices = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 200)))
    signal = np.sign(rng.normal(0.0, 1.0, 200))
    sh = baseline_random_gate_sharpe(signal, prices, gate_rate=0.3, n_draws=15, seed=1)
    assert np.isfinite(sh)


# ---------------------------------------------------------------------------
# Benjamini-Hochberg FDR
# ---------------------------------------------------------------------------


def test_benjamini_hochberg_accepts_clearly_significant() -> None:
    p = np.array([0.001, 0.001, 0.5, 0.6, 0.7])
    mask = benjamini_hochberg(p, alpha=0.05)
    assert mask[0] and mask[1]
    assert not mask[2] and not mask[3] and not mask[4]


def test_benjamini_hochberg_rejects_all_if_all_large() -> None:
    p = np.array([0.4, 0.5, 0.6, 0.7, 0.8])
    mask = benjamini_hochberg(p, alpha=0.05)
    assert not mask.any()


def test_benjamini_hochberg_handles_nan() -> None:
    p = np.array([0.01, np.nan, 0.5])
    mask = benjamini_hochberg(p, alpha=0.05)
    assert mask[0]
    assert not mask[1]  # NaN → fails
    assert not mask[2]


# ---------------------------------------------------------------------------
# End-to-end on synthetic grid CSV
# ---------------------------------------------------------------------------


def test_rigor_for_grid_produces_expected_columns() -> None:
    """Grid → rigor pipeline on a hand-built synthetic fold set."""
    rng = np.random.default_rng(42)
    records = []
    for H_val in [0.40, 0.50]:
        for rs_val in [0.10, 0.20]:
            for fold_id in range(20):
                records.append(
                    {
                        "H": H_val,
                        "rs": rs_val,
                        "fold_id": fold_id,
                        "fold_start": "2020-01-01",
                        "sharpe_oos": float(rng.normal(0.1, 0.5)),
                        "max_drawdown": float(abs(rng.normal(0.05, 0.02))),
                        "ic": 0.0,
                        "n_trades": int(rng.integers(0, 30)),
                        "gate_on": True,
                        "H_train": 0.42,
                        "rs_train": 0.15,
                        "pnl": 0.0,
                    }
                )
    grid_df = pd.DataFrame(records)
    rigor_df = rigor_for_grid(grid_df)
    expected_cols = {
        "H",
        "rs",
        "active_folds",
        "mean_sharpe",
        "mean_trades",
        "worst_dd",
        "sharpe_ci_lo",
        "sharpe_ci_hi",
        "significant_at_95",
        "p_value_null",
        "deflated_sharpe_stat",
        "expected_max_under_null",
        "probability_edge_real",
        "min_detectable_sharpe",
        "is_adequately_powered",
    }
    assert expected_cols <= set(rigor_df.columns)
    assert len(rigor_df) == 4  # 2 × 2 grid
    for _, row in rigor_df.iterrows():
        assert int(row["active_folds"]) == 20
        assert np.isfinite(row["sharpe_ci_lo"])
        assert np.isfinite(row["sharpe_ci_hi"])
        assert 0.0 <= float(row["probability_edge_real"]) <= 1.0
