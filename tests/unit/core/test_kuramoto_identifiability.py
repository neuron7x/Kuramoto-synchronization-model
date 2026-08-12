# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``core.kuramoto.identifiability`` (upgrade lineage #2).

The graded identifiability front-gate is reliability / instrument-honesty
infrastructure on the *already-calibrated* swing estimator. These tests
pin its theory-derived constants (no-peek), its monotonicity properties
(Hypothesis), the bounded-range invariant, and the additive contract
(point estimates bit-identical when the new field is ignored).

No physics invariant (R, K, δ, F, V, κ) is asserted here — this is the
self-knowledge layer, not the estimator; the estimator's physics is
covered by ``test_kuramoto_coupling_estimator`` and the calibration
suite. The properties below are statistical/numerical contracts.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.coupling_estimator import estimate_swing_coupling
from core.kuramoto.identifiability import (
    PE_HARD_FLOOR,
    R2_FLOOR,
    REFUSE_SCORE,
    WALD_Z_0975,
    IdentifiabilityVerdict,
    front_gate_verdict,
    identifiability_score,
    precision_leg,
)

_PROVENANCE = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "calibration"
    / "grid_kuramoto"
    / "identifiability"
    / "THRESHOLD_PROVENANCE.md"
)


# ---------------------------------------------------------------------------
# No-peek: code constants must equal the pre-committed theory values
# ---------------------------------------------------------------------------


def test_threshold_provenance_no_peek() -> None:
    """Code constants equal the theory values in THRESHOLD_PROVENANCE.md.

    This is the gate-peek detector: the REFUSE threshold and the R²
    adequacy floor are derived from numerical/statistical theory and
    pre-committed *before* any calibration validation. Changing either
    the code or the doc without the other fails here.
    """
    # z_{0.975} standard-normal quantile (theory constant).
    assert WALD_Z_0975 == 1.959963984540054
    # REFUSE_SCORE = z / (1 + z), recomputed independently.
    assert REFUSE_SCORE == WALD_Z_0975 / (1.0 + WALD_Z_0975)
    # R² adequacy floor = 1/2 (explained == unexplained variance).
    assert R2_FLOOR == 0.5
    # Hard PE floor = sqrt(eps_float64) (half-mantissa loss).
    assert PE_HARD_FLOOR == float(np.sqrt(np.finfo(np.float64).eps))

    text = _PROVENANCE.read_text(encoding="utf-8")
    # The exact REFUSE_SCORE value is committed in the provenance.
    assert f"{REFUSE_SCORE:.16f}"[:18] in text, (
        f"THRESHOLD_PROVENANCE.md drifted from code: REFUSE_SCORE "
        f"{REFUSE_SCORE!r} not found verbatim"
    )
    # The R2_FLOOR = 1/2 derivation is committed.
    assert re.search(r"R2_FLOOR\s*=\s*0\.5", text)
    # The z constant is committed verbatim.
    assert "1.959963984540054" in text
    # The √eps numerical floor is committed verbatim.
    assert "1.4901161193847656e-08" in text


# ---------------------------------------------------------------------------
# Bounded-range + leg algebra (algebraic, exact)
# ---------------------------------------------------------------------------


def test_score_bounded_unit_interval() -> None:
    """IDENTIFIABILITY = min(s_A, s_B) ∈ [0, 1] for any inputs."""
    rng = np.random.default_rng(0)
    for _ in range(200):
        w = np.abs(rng.normal(size=rng.integers(1, 8))) * rng.uniform(0, 50)
        r2 = float(rng.uniform(-0.5, 1.5))  # R² can be negative / >1 pre-clip
        s = identifiability_score(np.asarray(w, dtype=np.float64), r2)
        assert 0.0 <= s <= 1.0, f"score {s} out of [0,1] for r2={r2}"


def test_precision_leg_infinite_when_all_determined() -> None:
    """All-+inf Wald ratios ⇒ precision leg → 1 (perfectly determined)."""
    w = np.array([np.inf, np.inf], dtype=np.float64)
    assert precision_leg(w) == 1.0


def test_score_is_minimum_of_legs() -> None:
    """The combined score is exactly the min of the two legs."""
    w = np.array([10.0, 10.0], dtype=np.float64)  # s_A = 10/11 ≈ 0.909
    s_a = precision_leg(w)
    # Adequacy leg binding (low R²).
    assert identifiability_score(w, 0.30) == pytest.approx(0.30)
    # Precision leg binding (high R²).
    assert identifiability_score(w, 0.99) == pytest.approx(s_a)
    # Negative R² clips to 0 (worst case).
    assert identifiability_score(w, -0.4) == 0.0


# ---------------------------------------------------------------------------
# Hypothesis property: score monotone-decreasing in noise σ
# ---------------------------------------------------------------------------


def _make_pm(traj: np.ndarray, dt: float) -> PhaseMatrix:
    w = np.mod(traj, 2.0 * np.pi)
    w = np.clip(w, 0.0, np.nextafter(2.0 * np.pi, 0.0))
    return PhaseMatrix(
        theta=w,
        timestamps=np.arange(w.shape[0], dtype=np.float64) * dt,
        asset_ids=("a", "b", "c"),
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )


def _integrate(
    k: np.ndarray,
    p: np.ndarray,
    m: np.ndarray,
    d: np.ndarray,
    dt: float,
    n: int,
    theta0: np.ndarray,
) -> np.ndarray:
    nn = k.shape[0]
    th = theta0.astype(np.float64).copy()
    v = np.zeros(nn, dtype=np.float64)
    out = np.empty((n + 1, nn), dtype=np.float64)
    out[0] = th

    def accel(x: np.ndarray, w: np.ndarray) -> np.ndarray:
        diff = x[:, None] - x[None, :]
        coupling = (k * np.sin(diff)).sum(axis=1)
        return np.asarray((p - coupling - d * w) / m, dtype=np.float64)

    for t in range(n):
        a1 = accel(th, v)
        a2 = accel(th + 0.5 * dt * v, v + 0.5 * dt * a1)
        a3 = accel(th + 0.5 * dt * (v + 0.5 * dt * a1), v + 0.5 * dt * a2)
        a4 = accel(th + dt * (v + 0.5 * dt * a2), v + dt * a3)
        th = th + dt * v + (dt * dt / 6.0) * (a1 + 2 * a2 + 2 * a3)
        v = v + (dt / 6.0) * (a1 + 2 * a2 + 2 * a3 + a4)
        out[t + 1] = th
    return out


_K = np.array([[0.0, 0.9, 0.5], [0.9, 0.0, 0.7], [0.5, 0.7, 0.0]], dtype=np.float64)
_P = np.array([0.6, -0.1, -0.5], dtype=np.float64) - np.mean([0.6, -0.1, -0.5])
_M = np.array([0.4, 0.5, 0.3], dtype=np.float64)
_D = np.array([0.25, 0.3, 0.2], dtype=np.float64)


@pytest.mark.slow
@settings(max_examples=5, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_property_clean_accepts_any_noise_refuses(seed: int) -> None:
    """Coarse-separation property (the reliability contract).

    On the estimator's matched-recovery design regime: the noiseless
    fit scores **above** ``REFUSE_SCORE`` (instrument in envelope), and
    *any* non-trivial added measurement noise collapses the score
    **below** ``REFUSE_SCORE`` (instrument self-reports out of
    envelope). Strict monotonicity in σ does **not** hold for a
    differentiated-target regression (provenance § 2, empirically
    corrected); this coarse separation is what is verified and what the
    front-gate needs.
    """
    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(-0.8, 0.8, size=3).astype(np.float64)
    theta0 -= theta0.mean()
    base = _integrate(_K, _P, _M, _D, 0.005, 8000, theta0)

    clean = estimate_swing_coupling(
        _make_pm(base, 0.005),
        _M,
        _D,
        dt=0.005,
        savgol_window=7,
        savgol_polyorder=4,
        pe_guard=False,
        identifiability_gate=True,
    )
    assert clean.identifiability is not None
    assert clean.identifiability.score > REFUSE_SCORE, (
        f"noiseless matched fit must score above REFUSE "
        f"({clean.identifiability.score:.4f} ≤ {REFUSE_SCORE:.4f})"
    )
    assert clean.identifiability.verdict is IdentifiabilityVerdict.ACCEPT

    for sigma in (1e-3, 5e-3, 2e-2):
        nz = base + rng.normal(0.0, sigma, base.shape)
        est = estimate_swing_coupling(
            _make_pm(nz, 0.005),
            _M,
            _D,
            dt=0.005,
            savgol_window=7,
            savgol_polyorder=4,
            pe_guard=False,
            identifiability_gate=True,
        )
        assert est.identifiability is not None
        assert est.identifiability.score < REFUSE_SCORE, (
            f"σ={sigma}: noisy differentiated-target fit must collapse "
            f"below REFUSE ({est.identifiability.score:.4f} ≥ "
            f"{REFUSE_SCORE:.4f}) — instrument must self-report out of "
            f"envelope"
        )
        assert est.identifiability.verdict is IdentifiabilityVerdict.REFUSE


@pytest.mark.slow
@settings(max_examples=4, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_property_record_length_keeps_clean_accepted(seed: int) -> None:
    """A longer *clean* matched record never flips ACCEPT → REFUSE.

    Property: under persistent excitation, adding more matched
    noiseless data does not push an in-envelope fit out of envelope
    (the verified directional record-length property; provenance § 2).
    """
    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(-0.8, 0.8, size=3).astype(np.float64)
    theta0 -= theta0.mean()
    long_traj = _integrate(_K, _P, _M, _D, 0.005, 8000, theta0)

    for n in (2000, 4000, 8000):
        seg = long_traj[: n + 1]
        est = estimate_swing_coupling(
            _make_pm(seg, 0.005),
            _M,
            _D,
            dt=0.005,
            savgol_window=7,
            savgol_polyorder=4,
            pe_guard=False,
            identifiability_gate=True,
        )
        assert est.identifiability is not None
        assert est.identifiability.verdict is IdentifiabilityVerdict.ACCEPT, (
            f"clean matched record of length {n} must stay ACCEPT "
            f"(score {est.identifiability.score:.4f}); a longer record "
            f"under persistent excitation must not flip to REFUSE"
        )


# ---------------------------------------------------------------------------
# REFUSE fires on a constructed phase-locked trajectory (with PE guard off
# so the graded layer — not the hard error — is exercised)
# ---------------------------------------------------------------------------


def test_refuse_on_phase_locked_trajectory() -> None:
    """A rigidly-rotating cluster ⇒ REFUSE from the graded layer.

    With ``pe_guard=False`` the hard ``PersistentExcitationError`` does
    not fire; the graded front-gate must still declare the instrument
    out of envelope (no persistent excitation ⇒ the sine regressors are
    constant, the fit is degenerate, the weakest edge's CRLB band
    straddles zero / the model is inadequate).
    """
    t_len = 600
    phi = np.array([0.0, 0.4, -0.3], dtype=np.float64)
    t = np.arange(t_len, dtype=np.float64) * 0.01
    traj = phi[None, :] + 0.2 * t[:, None]
    pm = _make_pm(traj, 0.01)
    est = estimate_swing_coupling(
        pm,
        np.ones(3, dtype=np.float64),
        np.full(3, 0.2, dtype=np.float64),
        dt=0.01,
        pe_guard=False,
        identifiability_gate=True,
    )
    assert est.identifiability is not None
    assert est.identifiability.verdict is IdentifiabilityVerdict.REFUSE
    assert est.identifiability.score < REFUSE_SCORE
    assert not est.identifiability.accepted


# ---------------------------------------------------------------------------
# Additive contract: point estimates bit-identical when field ignored
# ---------------------------------------------------------------------------


def test_identifiability_gate_is_additive_bit_stable() -> None:
    """Point estimates are bit-identical with/without the gate.

    The new ``identifiability`` field is strictly additive: enabling it
    must not perturb ``K`` / ``injection`` / ``omega`` /
    ``min_singular_ratio`` by a single ULP (no-regression contract).
    """
    rng = np.random.default_rng(11)
    theta0 = rng.uniform(-0.8, 0.8, size=3).astype(np.float64)
    theta0 -= theta0.mean()
    traj = _integrate(_K, _P, _M, _D, 0.005, 4000, theta0)
    pm = _make_pm(traj, 0.005)

    off = estimate_swing_coupling(pm, _M, _D, dt=0.005, savgol_window=7, savgol_polyorder=4)
    on = estimate_swing_coupling(
        pm,
        _M,
        _D,
        dt=0.005,
        savgol_window=7,
        savgol_polyorder=4,
        identifiability_gate=True,
    )
    assert off.identifiability is None
    assert on.identifiability is not None
    np.testing.assert_array_equal(off.K, on.K)
    np.testing.assert_array_equal(off.injection, on.injection)
    np.testing.assert_array_equal(off.omega, on.omega)
    assert off.min_singular_ratio == on.min_singular_ratio


def test_covariance_returns_finite_lower_bound() -> None:
    """linearised_edge_covariance returns finite SE + R² on a good fit."""
    rng = np.random.default_rng(3)
    theta0 = rng.uniform(-0.8, 0.8, size=3).astype(np.float64)
    theta0 -= theta0.mean()
    traj = _integrate(_K, _P, _M, _D, 0.005, 4000, theta0)
    pm = _make_pm(traj, 0.005)
    est = estimate_swing_coupling(
        pm,
        _M,
        _D,
        dt=0.005,
        savgol_window=7,
        savgol_polyorder=4,
        identifiability_gate=True,
    )
    rep = est.identifiability
    assert rep is not None
    assert np.isfinite(rep.residual_variance)
    assert np.isfinite(rep.r_squared)
    for e in rep.edges:
        assert e.std_error >= 0.0
        assert np.isfinite(e.std_error)
        assert e.ci_low <= e.ci_high


def test_front_gate_verdict_pure_function_refuse_on_wide_ci() -> None:
    """Direct front_gate_verdict: a fat-CI edge with low R² ⇒ REFUSE."""
    k_hat = np.array(
        [[0.0, 0.10, 0.0], [0.10, 0.0, 0.0], [0.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    edges = [(0, 1), (0, 2), (1, 2)]
    # Edge (0,1): |K|=0.10, SE=0.20 ⇒ Wald 0.5 < z, CI straddles 0.
    se = np.array([0.20, 0.01, 0.01], dtype=np.float64)
    rep = front_gate_verdict(
        k_hat,
        edges,
        se,
        reciprocal_condition=0.3,
        residual_variance=1.0,
        r_squared=0.10,  # noise-dominated fit
    )
    assert rep.verdict is IdentifiabilityVerdict.REFUSE
    assert rep.binding_edge.ci_contains_zero
    assert "REFUSE" in rep.reason


def test_front_gate_verdict_accept_on_sharp_edges() -> None:
    """Direct front_gate_verdict: sharp edges + high R² ⇒ ACCEPT."""
    k_hat = np.array(
        [[0.0, 5.0, 3.0], [5.0, 0.0, 4.0], [3.0, 4.0, 0.0]],
        dtype=np.float64,
    )
    edges = [(0, 1), (0, 2), (1, 2)]
    se = np.array([0.05, 0.05, 0.05], dtype=np.float64)
    rep = front_gate_verdict(
        k_hat,
        edges,
        se,
        reciprocal_condition=0.5,
        residual_variance=1e-4,
        r_squared=0.99,
    )
    assert rep.verdict is IdentifiabilityVerdict.ACCEPT
    assert rep.accepted
    for e in rep.edges:
        assert not e.ci_contains_zero
