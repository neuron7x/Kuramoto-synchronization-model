"""Tests for PRIME_ARCHITECT_vX adversarial audit primitives.

The audit does NOT need tests that assert "passes the gate" — the whole
point of the module is to fail loudly on an insufficient substrate. We
test the primitives for correctness, the gate logic, and the artefact
contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.prime_architect_vx import (
    ARTEFACT_DIR,
    CRR_GATE,
    GAMMA_TARGET,
    GAMMA_TOL,
    IC_GATE,
    PERM_P_GATE,
    R2_GATE,
    SHARPE_GATE,
    _fiedler_lambda2,
    _gamma_psd,
    _gate,
    _ic,
    _r2,
    find_stage,
    reproduce_stage,
    reproduce_stage_regime_gated,
)

# ---------------------------------------------------------------- #
# Fiedler λ₂ has the correct bounds and spectral behaviour
# ---------------------------------------------------------------- #


def test_fiedler_lambda2_identity_graph() -> None:
    # Perfectly correlated 3-asset window → adj = 1 everywhere off-diagonal
    # → complete graph on 3 nodes → λ₂ of Laplacian == 3.
    n = 60
    base = np.random.default_rng(0).normal(size=n)
    window = np.stack([base, base, base], axis=1)
    lam2 = _fiedler_lambda2(window, threshold=0.1)
    assert abs(lam2 - 3.0) < 1e-6

    # Uncorrelated random window → adj all zero below threshold → λ₂ = 0
    rng = np.random.default_rng(1)
    window2 = rng.normal(size=(120, 3))
    lam2_zero = _fiedler_lambda2(window2, threshold=0.95)
    assert lam2_zero == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- #
# γ_PSD slope recovery on a known signal
# ---------------------------------------------------------------- #


def test_gamma_psd_white_and_red_noise() -> None:
    rng = np.random.default_rng(42)
    # White noise → γ ≈ 0
    white = rng.normal(size=4096)
    gamma_white = _gamma_psd(white)
    assert abs(gamma_white) < 0.3

    # Integrated (1/f² / random walk) → γ ≈ 2
    red = np.cumsum(rng.normal(size=4096))
    gamma_red = _gamma_psd(red)
    assert 1.4 < gamma_red < 2.6


# ---------------------------------------------------------------- #
# IC and R² primitives are finite on non-degenerate input
# ---------------------------------------------------------------- #


def test_ic_and_r2_primitives() -> None:
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(size=500))
    y_correlated = x + rng.normal(size=500) * 0.1
    y_noise = pd.Series(rng.normal(size=500))

    ic_strong = _ic(x, y_correlated)
    ic_weak = _ic(x, y_noise)
    assert ic_strong > 0.8
    assert abs(ic_weak) < 0.2

    r2_strong = _r2(x, y_correlated)
    r2_weak = _r2(x, y_noise)
    assert r2_strong > 0.5
    assert r2_weak < 0.05


# ---------------------------------------------------------------- #
# Gate logic: direction "greater_than", "less_than", "equal_to"
# ---------------------------------------------------------------- #


def test_gate_logic_covers_three_directions() -> None:
    g_gt_pass = _gate("ic", 0.15, IC_GATE, "greater_than")
    g_gt_fail = _gate("ic", 0.05, IC_GATE, "greater_than")
    g_lt_pass = _gate("p", 0.001, PERM_P_GATE, "less_than")
    g_lt_fail = _gate("p", 0.10, PERM_P_GATE, "less_than")
    g_eq_pass = _gate("gamma", 1.01, GAMMA_TARGET, "equal_to")
    g_eq_fail = _gate("gamma", 1.40, GAMMA_TARGET, "equal_to")
    assert g_gt_pass.passed is True
    assert g_gt_fail.passed is False
    assert g_lt_pass.passed is True
    assert g_lt_fail.passed is False
    assert g_eq_pass.passed is True
    assert g_eq_fail.passed is False
    # NaN input always fails.
    assert _gate("x", float("nan"), 0.1, "greater_than").passed is False


def test_gate_thresholds_match_directive() -> None:
    # Hard-coded directive thresholds — pinned so future edits that loosen
    # them require an explicit test update.
    assert PERM_P_GATE == pytest.approx(0.01)
    assert R2_GATE == pytest.approx(0.05)
    assert IC_GATE == pytest.approx(0.12)
    assert SHARPE_GATE == pytest.approx(1.70)
    assert CRR_GATE == pytest.approx(2.50)
    assert GAMMA_TARGET == pytest.approx(1.00)
    assert GAMMA_TOL == pytest.approx(0.05)


# ---------------------------------------------------------------- #
# Regime-gated reproduce survives small synthetic inputs without crashing
# ---------------------------------------------------------------- #


def test_reproduce_stage_regime_gated_handles_insufficient_data() -> None:
    n = 120
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    combo = pd.Series(np.random.default_rng(5).normal(size=n), index=idx)
    fwd = pd.Series(np.random.default_rng(6).normal(size=n) * 0.001, index=idx)
    lam2 = pd.Series(np.zeros(n), index=idx)  # all frozen → no active bars
    rep = reproduce_stage_regime_gated(combo, fwd, lam2, idx[int(0.7 * n)])
    assert rep["insufficient_active_bars"] is True or rep["n_test_active"] <= 0


def test_reproduce_stage_nominal() -> None:
    n = 800
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    rng = np.random.default_rng(9)
    combo = pd.Series(rng.normal(size=n), index=idx)
    fwd = pd.Series(rng.normal(size=n) * 0.001, index=idx)
    rep = reproduce_stage(combo, fwd, idx[int(0.7 * n)])
    for k in (
        "ic_train",
        "ic_test",
        "sharpe_test",
        "maxdd_test",
        "ann_return_test",
        "crr_test",
    ):
        assert k in rep


# ---------------------------------------------------------------- #
# FIND stage returns a Fiedler series with finite values
# ---------------------------------------------------------------- #


def test_find_stage_returns_finite_series() -> None:
    rng = np.random.default_rng(11)
    n, k = 400, 3
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.01,
        index=idx,
        columns=["A", "B", "C"],
    )
    lam2, diag = find_stage(returns, window=60, threshold=0.30)
    assert len(lam2) == n - 60
    assert np.isfinite(lam2.to_numpy()).all()
    assert diag["n_bars"] == len(lam2)
    assert 0.0 <= diag["fraction_below_1e-8"] <= 1.0


# ---------------------------------------------------------------- #
# Artefact schema test — optional, only runs when the audit has been emitted
# ---------------------------------------------------------------- #


REQUIRED_TOP_KEYS = {
    "prime_architect_version",
    "target",
    "narrow",
    "wide",
    "prime_architect_pass_any",
    "tradable_configurations",
}

REQUIRED_BLOCK_KEYS = {
    "substrate",
    "find_stage",
    "prove_stage",
    "measure_stage",
    "reproduce_stage",
    "reproduce_stage_regime_gated",
    "gates",
    "gated_gates",
    "prime_architect_pass",
    "prime_architect_pass_regime_gated",
}


def test_audit_log_schema_complete() -> None:
    out = ARTEFACT_DIR / "audit_log_vX.json"
    if not out.exists():
        pytest.skip("run research/askar/prime_architect_vx.py to emit audit_log_vX.json")
    audit = json.loads(Path(out).read_text())
    missing_top = REQUIRED_TOP_KEYS - set(audit.keys())
    assert not missing_top, f"audit top-level keys missing: {missing_top}"
    for block in ("narrow", "wide"):
        block_missing = REQUIRED_BLOCK_KEYS - set(audit[block].keys())
        assert not block_missing, f"{block} missing: {block_missing}"
    assert isinstance(audit["tradable_configurations"], list)
    assert isinstance(audit["prime_architect_pass_any"], bool)
