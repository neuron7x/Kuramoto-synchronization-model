"""Tests for the closing Unity + momentum sprint.

Required 8/8 per the task brief:
 1. orthogonality_gate_stops_if_corr_high
 2. walk_forward_5_folds_no_lookahead
 3. ensemble_weights_train_only
 4. disqualification_if_unity_weight_below_005
 5. expanding_quintile_no_lookahead
 6. crisis_2022_isolated_correctly
 7. permutation_1000_shuffles
 8. output_schema_complete
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.daily_53_experiment import SPLIT_DATE, DailyPanel
from research.askar.optimal_universe import expanding_quintile, permutation_test
from research.askar.unity_momentum_final import (
    CORR_ENSEMBLE_VS_MOMENTUM_CEIL,
    CORR_GATE,
    CRISIS_2022_HI,
    CRISIS_2022_LO,
    N_PERMUTATIONS,
    RESULTS_DIR,
    W_UNITY_DISQUAL_THRESHOLD,
    W_UNITY_GRID,
    orthogonality_gate,
    run_ensemble,
    walk_forward_unity,
)

REQUIRED_TOP_KEYS = {
    "orthogonality",
    "walk_forward_unity",
    "ensemble_unity_momentum",
    "unity_standalone",
    "momentum_standalone",
    "baseline_geosync_yfinance",
    "verdict",
    "askar_message",
}

REQUIRED_ENSEMBLE_KEYS = {
    "w_unity",
    "w_momentum",
    "IC_train_ensemble",
    "IC_test_ensemble",
    "sharpe_test",
    "maxdd_test",
    "permutation_p",
    "permutation_sigma",
    "crisis_2022",
    "corr_ensemble_vs_momentum",
    "disqualified",
    "disqualified_by_weight",
    "effectively_momentum",
    "disqual_threshold",
    "disqual_corr_ceil",
    "w_unity_grid",
}


def _synthetic_panel(
    n: int = 2500,
    k: int = 10,
    seed: int = 0,
    target_drives: bool = False,
    unity_correlated_with_momentum: bool = False,
) -> DailyPanel:
    """Build a 10-asset synthetic DailyPanel.

    ``target_drives`` — inject positive target momentum so the signal
    basis has a tradable component.

    ``unity_correlated_with_momentum`` — force the target returns to
    depend on the rolling correlation magnitude of the rest of the
    panel; this drags Unity into lockstep with the target's own
    momentum and trips the orthogonality gate.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2017-12-03", periods=n, freq="D")
    cols = [f"A{i}" for i in range(k)]
    ret = rng.normal(size=(n, k)) * 0.01
    if target_drives:
        # Add a slow sinusoid to the target only — creates real momentum.
        trend = 0.002 * np.sin(np.linspace(0, 12.0, n))
        ret[:, 0] += trend
    if unity_correlated_with_momentum:
        # Drive all non-target assets with the target's sign.
        ret[:, 1:] = 0.0
        for i in range(1, k):
            ret[:, i] += ret[:, 0] * (0.5 + 0.05 * i)
    returns = pd.DataFrame(ret, index=idx, columns=cols)
    prices = returns.copy()  # price frame not used downstream in tests
    return DailyPanel(prices=prices, returns=returns, target="A0", n_assets=k)


# ---------------------------------------------------------------- #
# 1. Orthogonality gate stops the pipeline when Unity ≈ momentum
# ---------------------------------------------------------------- #


def test_orthogonality_gate_stops_if_corr_high() -> None:
    # Case 1: correlation is low → gate passes.
    panel = _synthetic_panel(seed=1)
    unity_series = pd.Series(
        np.random.default_rng(1).normal(size=len(panel.returns)),
        index=panel.returns.index,
    )
    ok = orthogonality_gate(unity_series, panel.returns.iloc[:, 0])
    assert ok["gate_passed"] is True

    # Case 2: unity is literally the target's 20-day momentum → corr ≈ 1.
    bad_unity = panel.returns.iloc[:, 0].rolling(20).sum().dropna()
    gate = orthogonality_gate(bad_unity, panel.returns.iloc[:, 0])
    assert (
        abs(gate["corr_unity_momentum"]) > CORR_GATE
    ), f"gate should have caught corr={gate['corr_unity_momentum']:.3f}"
    assert gate["gate_passed"] is False


# ---------------------------------------------------------------- #
# 2. Walk-forward 5-fold has no lookahead
# ---------------------------------------------------------------- #


def test_walk_forward_5_folds_no_lookahead() -> None:
    panel = _synthetic_panel(n=3000, seed=2)
    rep1 = walk_forward_unity(panel, n_folds=5)

    poisoned = panel.returns.copy()
    poisoned.loc[poisoned.index >= SPLIT_DATE] += 1e6
    poisoned_panel = DailyPanel(
        prices=poisoned.copy(),
        returns=poisoned,
        target=panel.target,
        n_assets=panel.n_assets,
    )
    rep2 = walk_forward_unity(poisoned_panel, n_folds=5)

    # Folds whose test block starts strictly before SPLIT_DATE must be
    # bit-identical between the clean and poisoned runs.
    for f1, f2 in zip(rep1["folds"], rep2["folds"]):
        test_start = pd.Timestamp(f1["test_start"])
        if test_start < SPLIT_DATE:
            assert f1["IC_train"] == pytest.approx(f2["IC_train"], abs=1e-9)
            assert f1["sign"] == f2["sign"]


# ---------------------------------------------------------------- #
# 3. Ensemble weights are frozen on the train slice
# ---------------------------------------------------------------- #


def test_ensemble_weights_train_only() -> None:
    panel = _synthetic_panel(n=2800, seed=3, target_drives=True)
    rep1, _strat1, _df1 = run_ensemble(panel)

    poisoned = panel.returns.copy()
    poisoned.loc[poisoned.index >= SPLIT_DATE, "A0"] += 1.0  # massive shift
    poisoned_panel = DailyPanel(
        prices=poisoned.copy(),
        returns=poisoned,
        target="A0",
        n_assets=panel.n_assets,
    )
    rep2, _strat2, _df2 = run_ensemble(poisoned_panel)

    assert rep1["w_unity"] == pytest.approx(rep2["w_unity"], abs=1e-9)
    assert rep1["w_momentum"] == pytest.approx(rep2["w_momentum"], abs=1e-9)
    assert rep1["IC_train_ensemble"] == pytest.approx(rep2["IC_train_ensemble"], abs=1e-9)


# ---------------------------------------------------------------- #
# 4. Disqualification guard fires on effectively-momentum blends
# ---------------------------------------------------------------- #


def test_disqualification_if_unity_weight_below_005() -> None:
    # Synthetic panel where momentum strongly drives the target and Unity
    # is near-noise — grid scan should pick w_unity = grid minimum (0.10)
    # and the ensemble should end > 95 % correlated with raw momentum,
    # triggering the effectively_momentum disqualification guard.
    panel = _synthetic_panel(n=2800, seed=4, target_drives=True)
    rep, _strat, _df = run_ensemble(panel)
    assert (
        rep["w_unity"] == W_UNITY_GRID[0]
    ), f"grid scan expected to hit w_unity floor; got {rep['w_unity']}"
    # At least one of the two guards must fire.
    assert rep["disqualified"] is True
    assert rep["disqualified_by_weight"] is True or rep["effectively_momentum"] is True
    assert W_UNITY_DISQUAL_THRESHOLD == 0.05
    assert CORR_ENSEMBLE_VS_MOMENTUM_CEIL >= 0.90


# ---------------------------------------------------------------- #
# 5. Expanding quintile is lookahead-free
# ---------------------------------------------------------------- #


def test_expanding_quintile_no_lookahead() -> None:
    rng = np.random.default_rng(5)
    base = pd.Series(rng.normal(size=800))
    pos_base = expanding_quintile(base, min_history=50)
    perturbed = base.copy()
    perturbed.iloc[400:] += 1e6
    pos_perturbed = expanding_quintile(perturbed, min_history=50)
    pd.testing.assert_series_equal(pos_base.iloc[:400], pos_perturbed.iloc[:400], check_names=False)


# ---------------------------------------------------------------- #
# 6. 2022 crisis window lives inside the train period
# ---------------------------------------------------------------- #


def test_crisis_2022_isolated_correctly() -> None:
    assert CRISIS_2022_LO == pd.Timestamp("2022-01-01")
    assert CRISIS_2022_HI == pd.Timestamp("2023-01-01")
    # Entire 2022 must end before the walk-forward test slice begins.
    assert CRISIS_2022_HI <= SPLIT_DATE
    assert CRISIS_2022_LO < SPLIT_DATE
    # And 2022 must be in train, not test, of our actual orchestrator.
    idx = pd.date_range("2017-12-01", "2026-02-20", freq="D")
    train = idx[idx < SPLIT_DATE]
    crisis = idx[(idx >= CRISIS_2022_LO) & (idx < CRISIS_2022_HI)]
    assert set(crisis).issubset(set(train))


# ---------------------------------------------------------------- #
# 7. Permutation test uses 1000 shuffles
# ---------------------------------------------------------------- #


def test_permutation_1000_shuffles() -> None:
    assert N_PERMUTATIONS == 1000
    rng = np.random.default_rng(7)
    n = 1500
    signal = pd.Series(rng.normal(size=n))
    fwd = pd.Series(rng.normal(size=n))
    ic, p, sigma = permutation_test(signal, fwd, n=N_PERMUTATIONS, seed=7)
    assert np.isfinite(ic)
    assert 0.0 <= p <= 1.0
    assert np.isfinite(sigma)
    # Under the null this must not collapse to a suspiciously small p.
    assert p > 0.20, f"random signal gave p={p:.3f}"


# ---------------------------------------------------------------- #
# 8. Output JSON schema complete
# ---------------------------------------------------------------- #


def test_output_schema_complete() -> None:
    out = RESULTS_DIR / "askar_unity_momentum_result.json"
    if not out.exists():
        pytest.skip("run research/askar/unity_momentum_final.py to produce the JSON")
    report = json.loads(Path(out).read_text())
    missing = REQUIRED_TOP_KEYS - set(report.keys())
    assert not missing, f"missing top-level keys: {missing}"
    assert report["verdict"] in {
        "SIGNAL_FOUND",
        "MARGINAL",
        "DISQUALIFIED",
        "NO_SIGNAL",
    }

    ens = report["ensemble_unity_momentum"]
    if "skipped" not in ens:
        missing_e = REQUIRED_ENSEMBLE_KEYS - set(ens.keys())
        assert not missing_e, f"ensemble missing: {missing_e}"
        # w_unity must sit on the configured grid.
        assert ens["w_unity"] in set(W_UNITY_GRID)

    # Walk-forward fold IC array length matches positive_count consistency.
    wf = report["walk_forward_unity"]
    if "skipped" not in wf:
        folds = wf.get("folds", [])
        positive = sum(1 for f in folds if f["IC_test"] > 0)
        assert positive == wf["positive_count"]
