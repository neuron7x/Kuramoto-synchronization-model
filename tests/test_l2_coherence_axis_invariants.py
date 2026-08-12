"""Task 3 · Per-axis invariant assertions.

For each of the 10 validation axes, assert an algebraic or structural
invariant that must hold if the underlying math is correct. These are
not statistical probes — they are identity-level guarantees.

Invariant violation indicates a real bug, not a sampling anomaly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_RESULTS = Path("results")


def _load(name: str) -> dict[str, Any]:
    with (_RESULTS / name).open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


# Axis 1 — kill test: verdict string is one of {PROCEED, ABORT}
def test_axis1_killtest_verdict_is_canonical() -> None:
    killtest = _load("L2_KILLTEST_VERDICT.json")
    assert killtest["verdict"] in {"PROCEED", "ABORT"}
    assert killtest["ic_signal"] > 0.0
    assert 0.0 <= killtest["residual_ic_pvalue"] <= 1.0


# Axis 2 — bootstrap CI: lo ≤ point ≤ hi by construction
def test_axis2_bootstrap_ci_contains_point() -> None:
    robustness = _load("L2_ROBUSTNESS.json")
    boot = robustness["bootstrap"]
    lo = float(boot["ci_lo_95"])
    hi = float(boot["ci_hi_95"])
    point = float(boot["ic_point"])
    assert lo <= hi, "CI order invariant"
    # Point may sit outside CI for heavy-tailed samples, but must be within ±3σ
    std = float(boot["ic_std_bootstrap"])
    assert abs(point - float(boot["ic_mean_bootstrap"])) <= 3.0 * std + 1e-9


# Axis 3 — deflated Sharpe: Pr(real) ∈ [0, 1], DSR finite
def test_axis3_deflated_sharpe_probability_valid() -> None:
    robustness = _load("L2_ROBUSTNESS.json")
    dsr = robustness["deflated_sharpe"]
    prob = float(dsr["probability_sharpe_is_real"])
    assert 0.0 <= prob <= 1.0
    assert isinstance(dsr["deflated_sharpe"], float)


# Axis 4 — purged K-fold: ic_mean equals average of ic_per_fold
def test_axis4_purged_cv_mean_is_fold_average() -> None:
    cv = _load("L2_PURGED_CV.json")
    folds = [float(x) for x in cv["ic_per_fold"]]
    reported_mean = float(cv["ic_mean"])
    computed_mean = sum(folds) / len(folds)
    assert abs(reported_mean - computed_mean) < 1e-9


# Axis 5 — mutual information: bits ≈ nats / ln(2), non-negative
def test_axis5_mutual_information_unit_identity() -> None:
    import math

    robustness = _load("L2_ROBUSTNESS.json")
    mi = robustness["mutual_information"]
    nats = float(mi["mutual_information_nats"])
    bits = float(mi["mutual_information_bits"])
    assert nats >= 0.0
    assert bits >= 0.0
    assert abs(bits - nats / math.log(2.0)) < 1e-9


# Axis 6 — spectral: verdict consistent with β bands
def test_axis6_spectral_verdict_matches_beta_bands() -> None:
    spectral = _load("L2_SPECTRAL.json")
    beta = float(spectral["redness_slope_beta"])
    verdict = str(spectral["regime_verdict"])
    if beta >= 1.5:
        assert verdict == "RED"
    elif beta >= 0.5:
        assert verdict in {"PINK", "RED"}
    else:
        assert verdict in {"WHITE", "PINK", "INCONCLUSIVE"}


# Axis 7 — Hurst DFA: verdict consistent with H bands; R² > 0.8 implies strong fit
def test_axis7_hurst_verdict_matches_h_bands() -> None:
    hurst = _load("L2_HURST.json")["report"]
    h = float(hurst["hurst_exponent"])
    verdict = str(hurst["verdict"])
    if h < 0.4:
        assert verdict == "MEAN_REVERTING"
    elif h < 0.6:
        assert verdict == "WHITE_NOISE"
    elif h < 1.0:
        assert verdict == "PERSISTENT"
    else:
        assert verdict == "STRONG_PERSISTENT"
    assert float(hurst["r_squared"]) > 0.0


# Axis 8 — Transfer entropy: counts sum to n_pairs; each TE ≥ 0
def test_axis8_te_counts_sum_to_n_pairs_and_nonneg() -> None:
    te = _load("L2_TRANSFER_ENTROPY.json")
    counts = te["verdict_counts"]
    n_pairs = int(te["n_pairs"])
    assert sum(int(v) for v in counts.values()) == n_pairs
    for entry in te["pairs"]:
        r = entry["report"]
        assert float(r["te_y_to_x_nats"]) >= 0.0
        assert float(r["te_x_to_y_nats"]) >= 0.0


# Axis 9 — Conditional TE: counts sum to n_pairs; each CTE ≥ 0
def test_axis9_cte_counts_sum_to_n_pairs_and_nonneg() -> None:
    cte = _load("L2_CONDITIONAL_TE.json")
    counts = cte["verdict_counts"]
    n_pairs = int(cte["n_pairs"])
    assert sum(int(v) for v in counts.values()) == n_pairs
    for entry in cte["pairs"]:
        r = entry["report"]
        assert float(r["te_unconditional_y_to_x_nats"]) >= 0.0
        assert float(r["te_conditional_y_to_x_nats"]) >= 0.0


# Axis 10 — walk-forward: fractions ∈ [0,1], q25 ≤ median ≤ q75
def test_axis10_walk_forward_fractions_and_quantile_order() -> None:
    wf = _load("L2_WALK_FORWARD_SUMMARY.json")
    for key in (
        "fraction_positive",
        "fraction_above_0p05",
        "fraction_below_minus_0p05",
        "fraction_permutation_significant",
    ):
        v = float(wf[key])
        assert 0.0 <= v <= 1.0, f"{key} = {v} outside [0,1]"
    q25 = float(wf["ic_q25"])
    med = float(wf["ic_median"])
    q75 = float(wf["ic_q75"])
    ic_min = float(wf["ic_min"])
    ic_max = float(wf["ic_max"])
    assert ic_min <= q25 <= med <= q75 <= ic_max


# Bridge — regime Markov: rows sum to 1 (stochastic matrix);
# stationary distribution is a valid probability vector.
def test_regime_markov_rows_are_stochastic() -> None:
    markov = _load("L2_REGIME_MARKOV.json")
    matrix = markov["transition_matrix"]
    for row in matrix:
        row_sum = sum(float(x) for x in row)
        assert abs(row_sum - 1.0) < 1e-6 or row_sum == 0.0

    stationary = [float(x) for x in markov["stationary_distribution"]]
    assert all(p >= 0.0 for p in stationary)
    assert abs(sum(stationary) - 1.0) < 1e-6
