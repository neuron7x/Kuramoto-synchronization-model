# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for CALIB-GRID-001 — external ground-truth Kuramoto calibration.

Covers: embedded-grid contract invariants, the Dörfler–Bullo reduction
formulae (exact at float precision), the K→∞ tight-sync recovery
property (Hypothesis), calibration-loop determinism, pre-registration ↔
code agreement (fail-closed), the identifiability sweep that proves the
instrument itself is sound, and the stable NEGATIVE verdict ledger.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
    PersistentExcitationError,
    estimate_swing_coupling,
)
from research.calibration.grid_kuramoto import (
    NOISELESS_GATES,
    NOISY_GATES,
    SimConfig,
    coupling_from_susceptance,
    dorfler_bullo_critical_coupling,
    evaluate_gates,
    ieee_39_new_england,
    natural_frequency_from_injection,
    overall_verdict,
    run_calibration,
    wscc_9_bus,
)
from research.calibration.grid_kuramoto.run import build_ledger, build_r1_ledger

_PREREG = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "calibration"
    / "grid_kuramoto"
    / "PREREGISTRATION.md"
)


# ---------------------------------------------------------------------------
# Embedded-grid contract invariants
# ---------------------------------------------------------------------------


def test_wscc9_contract_invariants() -> None:
    """NON_PHYSICS: grid-fixture contract validation (shape/symmetry), not a registered physics invariant. WSCC-9 fixture is a valid 3-node symmetric lossless system."""
    sys = wscc_9_bus()
    assert sys.n == 3
    assert sys.susceptance.shape == (3, 3)
    np.testing.assert_allclose(sys.susceptance, sys.susceptance.T, atol=1e-12)
    assert np.all(np.diag(sys.susceptance) == 0.0)
    assert np.all(sys.voltage > 0.0)
    assert np.all(sys.inertia > 0.0)
    assert np.all(sys.damping > 0.0)
    # Injections are mean-centred (lossless reduced model balance).
    assert abs(float(np.mean(sys.injection))) < 1e-12


def test_ieee39_contract_invariants() -> None:
    """NON_PHYSICS: grid-fixture contract validation, not a registered physics invariant. IEEE-39 fixture is a valid 10-node symmetric system."""
    sys = ieee_39_new_england()
    assert sys.n == 10
    np.testing.assert_allclose(sys.susceptance, sys.susceptance.T, atol=1e-12)
    assert np.all(np.diag(sys.susceptance) == 0.0)
    assert np.all(sys.voltage > 0.0)
    assert abs(float(np.mean(sys.injection))) < 1e-12


@pytest.mark.parametrize("bad", ["susceptance", "voltage", "inertia"])
def test_gridsystem_rejects_malformed(bad: str) -> None:
    """NON_PHYSICS: GridSystem fail-closed input guard, not a registered physics invariant. GridSystem fails closed on contract violations."""
    sys = wscc_9_bus()
    kw: dict[str, Any] = {
        "name": sys.name,
        "bus_ids": sys.bus_ids,
        "susceptance": sys.susceptance.copy(),
        "voltage": sys.voltage.copy(),
        "injection": sys.injection.copy(),
        "inertia": sys.inertia.copy(),
        "damping": sys.damping.copy(),
        "citation": sys.citation,
    }
    if bad == "susceptance":
        s = kw["susceptance"]
        s[0, 1] = 99.0  # break symmetry
    elif bad == "voltage":
        kw["voltage"] = np.array([-1.0, 1.0, 1.0])
    else:
        kw["inertia"] = np.array([0.0, 1.0, 1.0])
    from research.calibration.grid_kuramoto import GridSystem

    with pytest.raises(ValueError):
        GridSystem(**kw)


# ---------------------------------------------------------------------------
# Reduction formulae — exact at float precision (INV-style algebraic)
# ---------------------------------------------------------------------------


def test_coupling_formula_exact() -> None:
    """NON_PHYSICS: Dorfler-Bullo coupling-reduction algebra (calibration formula), not a registered physics invariant. K_ij = |V_i||V_j|B_ij to float precision (Dörfler–Bullo Eq. (2))."""
    sys = wscc_9_bus()
    k = coupling_from_susceptance(sys.susceptance, sys.voltage)
    for i in range(sys.n):
        for j in range(sys.n):
            if i == j:
                assert k[i, j] == 0.0
            else:
                expected = sys.voltage[i] * sys.voltage[j] * sys.susceptance[i, j]
                assert abs(k[i, j] - expected) < 1e-12
    np.testing.assert_allclose(k, k.T, atol=1e-12)


def test_natural_frequency_mean_centred() -> None:
    """NON_PHYSICS: natural-frequency gauge reduction (calibration formula), not a registered physics invariant. ω_i = P_i/d_i, then mean-removed (rotating reference gauge)."""
    sys = wscc_9_bus()
    w = natural_frequency_from_injection(sys.injection, sys.damping)
    assert abs(float(np.mean(w))) < 1e-12
    # Relative ordering preserved (gauge does not change relative ω).
    raw = sys.injection / sys.damping
    assert np.argmax(w) == np.argmax(raw)


def test_dorfler_bullo_uniform_scale_invariance() -> None:
    """NON_PHYSICS: critical-coupling scale-invariance algebra (calibration formula), not a registered physics invariant. s_crit scales exactly as 1/s under uniform K↦sK (Eq. (3))."""
    sys = wscc_9_bus()
    k = coupling_from_susceptance(sys.susceptance, sys.voltage)
    w = natural_frequency_from_injection(sys.injection, sys.damping)
    s0 = dorfler_bullo_critical_coupling(k, w)
    for s in (2.0, 5.0, 10.0):
        s_scaled = dorfler_bullo_critical_coupling(s * k, w)
        assert abs(s_scaled - s0 / s) < 1e-9 * max(1.0, s0)


def test_dorfler_bullo_disconnected_fails_closed() -> None:
    """NON_PHYSICS: disconnected-graph fail-closed guard, not a registered physics invariant. Disconnected coupling graph → ValueError (no silent best-effort)."""
    k = np.zeros((4, 4), dtype=np.float64)
    k[0, 1] = k[1, 0] = 1.0  # {0,1} isolated from {2,3}
    w = np.array([0.1, -0.1, 0.2, -0.2], dtype=np.float64)
    with pytest.raises(ValueError, match="disconnected"):
        dorfler_bullo_critical_coupling(k, w)


# ---------------------------------------------------------------------------
# Hypothesis property — K→∞ tight-sync recovery on matched first-order data
# ---------------------------------------------------------------------------


def _first_order_traj(k: np.ndarray, w: np.ndarray, dt: float, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    th = np.asarray(rng.uniform(-0.4, 0.4, size=k.shape[0]), dtype=np.float64)
    out = np.empty((n + 1, k.shape[0]), dtype=np.float64)
    out[0] = th

    def f(x: np.ndarray) -> np.ndarray:
        d = x[None, :] - x[:, None]
        return np.asarray(w + (k * np.sin(d)).sum(axis=1), dtype=np.float64)

    for t in range(n):
        k1 = f(th)
        k2 = f(th + 0.5 * dt * k1)
        k3 = f(th + 0.5 * dt * k2)
        k4 = f(th + dt * k3)
        th = th + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        out[t + 1] = th
    return out


@pytest.mark.slow
@settings(max_examples=8, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_property_weak_coupling_topology_recovered(seed: int) -> None:
    """NON_PHYSICS: estimator topology-recovery soundness (calibration instrument), not a registered physics invariant.
    In the estimator's design regime (weak, non-locked, matched
    first-order model) the *topology support* of a 3-node chain is
    recovered: the present edge survives, the absent edge stays absent.

    This is the property that must hold for the calibration instrument
    to be sound — it isolates estimator behaviour from the second-order
    model mismatch documented in RESULTS.md.
    """
    k = np.array(
        [[0.0, 0.35, 0.0], [0.35, 0.0, 0.30], [0.0, 0.30, 0.0]],
        dtype=np.float64,
    )
    w = np.array([-1.4, 0.2, 1.2], dtype=np.float64)
    w = w - w.mean()
    traj = _first_order_traj(k, w, dt=0.01, n=5000, seed=seed)
    wrapped = np.mod(traj, 2.0 * np.pi)
    wrapped = np.clip(wrapped, 0.0, np.nextafter(2.0 * np.pi, 0.0))
    pm = PhaseMatrix(
        theta=wrapped,
        timestamps=np.arange(wrapped.shape[0], dtype=np.float64) * 0.01,
        asset_ids=("a", "b", "c"),
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )
    est = CouplingEstimator(CouplingEstimationConfig(penalty="mcp", lambda_reg=0.005, dt=0.01))
    k_hat = np.abs(0.5 * (est.estimate(pm).K + est.estimate(pm).K.T))
    scale = float(np.max(k_hat))
    assert scale > 0.0
    present = k_hat / scale
    # Present edges clearly above the absent (0,2) edge.
    assert present[0, 1] > present[0, 2]
    assert present[1, 2] > present[0, 2]


# ---------------------------------------------------------------------------
# Pre-registration ↔ code agreement (fail-closed)
# ---------------------------------------------------------------------------


def test_preregistration_matches_code() -> None:
    """NON_PHYSICS: pre-registration vs code agreement (admissibility infra), not a registered physics invariant. PREREGISTRATION.md gate table mirrors gates.py byte-for-numeric."""
    text = _PREREG.read_text(encoding="utf-8")
    for gate in (*NOISELESS_GATES, *NOISY_GATES):
        # The gate name and its threshold must both appear in the doc,
        # on a markdown table row containing the operator.
        pat = re.compile(
            re.escape(f"`{gate.name}`")
            + r".*?"
            + re.escape(gate.operator)
            + r".*?"
            + re.escape(f"`{gate.threshold}`")
        )
        assert pat.search(text), (
            f"PREREGISTRATION.md drifted from gates.py for {gate.name}: "
            f"expected operator {gate.operator} threshold {gate.threshold}"
        )


def test_gate_thresholds_are_frozen_values() -> None:
    """NON_PHYSICS: frozen-gate post-data-edit detector (admissibility infra), not a registered physics invariant. Lock the exact pre-registered numbers (post-data edit detector)."""
    nl = {g.name: (g.operator, g.threshold) for g in NOISELESS_GATES}
    ny = {g.name: (g.operator, g.threshold) for g in NOISY_GATES}
    assert nl == {
        "noiseless.frobenius": ("<=", 0.10),
        "noiseless.topology_f1": (">=", 0.95),
        "noiseless.critical_coupling": ("<=", 0.15),
    }
    assert ny == {
        "noisy.frobenius": ("<=", 0.25),
        "noisy.topology_f1": (">=", 0.90),
    }


# ---------------------------------------------------------------------------
# Calibration loop — determinism + stable NEGATIVE verdict
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_calibration_deterministic() -> None:
    """NON_PHYSICS: calibration-loop determinism (reproducibility infra), not a registered physics invariant. Seeded calibration is bit-reproducible across two runs."""
    sys = wscc_9_bus()
    cfg = SimConfig()
    a = run_calibration(sys, cfg, noisy=False)
    b = run_calibration(sys, cfg, noisy=False)
    assert a.frobenius_rel_error == b.frobenius_rel_error
    assert a.topology_f1 == b.topology_f1
    assert a.critical_coupling_rel_error == b.critical_coupling_rel_error


@pytest.mark.slow
def test_wscc9_verdict_is_negative_and_localized() -> None:
    """NON_PHYSICS: pinned NEGATIVE calibration verdict (admissibility ledger), not a registered physics invariant.
    The pre-registered WSCC-9 calibration lands a NEGATIVE artifact
    whose failing gates name a concrete refinement target.

    This asserts the *honest* outcome: topology support is recovered
    noiseless (F1≥0.95) but the signed-coupling Frobenius gate is
    missed — the estimator is a first-order identifier on second-order
    data (see RESULTS.md). No promotion language is implied by the
    test; it pins the NEGATIVE verdict so a future estimator change
    that closes the gap is detected as a deliberate, reviewed event.
    """
    sys = wscc_9_bus()
    cfg = SimConfig()
    nl = run_calibration(sys, cfg, noisy=False)
    ny = run_calibration(sys, cfg, noisy=True)
    results = evaluate_gates(nl, NOISELESS_GATES) + evaluate_gates(ny, NOISY_GATES)
    verdict = overall_verdict(results)
    assert verdict == "NEGATIVE"

    by_name = {r.name: r for r in results}
    # Topology support IS recovered noiseless (instrument is sound).
    assert by_name["noiseless.topology_f1"].passed
    # Signed-coupling Frobenius IS missed (the localized finding).
    assert not by_name["noiseless.frobenius"].passed
    assert "coupling_estimator" in by_name["noiseless.frobenius"].localises_to
    # Every failed gate carries a non-empty localisation string.
    for r in results:
        if not r.passed:
            assert r.localises_to.strip()


def test_ledger_is_machine_readable_and_sha_pinned() -> None:
    """NON_PHYSICS: sha-pinned ledger serialization (admissibility infra), not a registered physics invariant. build_ledger emits a JSON-serialisable, sha-pinned NEGATIVE ledger."""
    sys = wscc_9_bus()
    ledger = build_ledger(sys, SimConfig())
    blob = json.dumps(ledger, sort_keys=True)
    assert json.loads(blob)["verdict"] == "NEGATIVE"
    assert ledger["is_hypothesis"] is False
    assert len(ledger["ledger_sha256"]) == 64
    assert ledger["localized_refinement_targets"]


# ---------------------------------------------------------------------------
# Instrument-soundness diagnostic — recovery in the estimator design regime
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_identifiability_sweep_weak_regime() -> None:
    """NON_PHYSICS: estimator design-regime recovery (calibration instrument), not a registered physics invariant.
    The estimator *does* recover K in its design regime.

    Weak coupling on a *matched first-order* model keeps the trajectory
    non-phase-locked (persistently excited); the row design then has
    full rank and the Frobenius error is small. This proves the WSCC-9
    NEGATIVE verdict is a genuine model-class / excitation boundary,
    not a broken instrument.
    """
    k_base = np.array(
        [[0.0, 7.74, 5.17], [7.74, 0.0, 8.87], [5.17, 8.87, 0.0]],
        dtype=np.float64,
    )
    w = np.array([-1.5, 2.4, -0.9], dtype=np.float64)
    w = w - w.mean()
    k = 0.05 * k_base  # weak: K_max ≈ 0.44, system does not lock
    traj = _first_order_traj(k, w, dt=0.01, n=6000, seed=7)
    wrapped = np.mod(traj, 2.0 * np.pi)
    wrapped = np.clip(wrapped, 0.0, np.nextafter(2.0 * np.pi, 0.0))
    pm = PhaseMatrix(
        theta=wrapped,
        timestamps=np.arange(wrapped.shape[0], dtype=np.float64) * 0.01,
        asset_ids=("a", "b", "c"),
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )
    est = CouplingEstimator(CouplingEstimationConfig(penalty="mcp", lambda_reg=0.005, dt=0.01))
    k_hat = 0.5 * (est.estimate(pm).K + est.estimate(pm).K.T)
    rel = float(np.linalg.norm(k_hat - k) / np.linalg.norm(k))
    # Design-regime recovery: order-of-magnitude better than the
    # strongly-coupled WSCC-9 miss (~1.0). Bound is a soundness floor,
    # not a pre-registered gate.
    assert rel < 0.30, (
        f"instrument unsound: weak-regime Frobenius rel err {rel:.3f} "
        f"should be << 1.0; estimator must recover K when its "
        f"first-order persistently-excited assumptions hold"
    )


@pytest.mark.slow
def test_ieee39_calibration_runs_and_is_scored() -> None:
    """NON_PHYSICS: IEEE-39 calibration end-to-end smoke (instrument scaling), not a registered physics invariant.
    Heavy IEEE-39 fixture runs end-to-end and produces finite metrics.

    Not part of the pre-registered WSCC-9 verdict; this only checks the
    loop scales to a 10-machine system and the ledger stays well-formed.
    """
    sys = ieee_39_new_england()
    cfg = SimConfig()
    ledger = build_ledger(sys, cfg)
    assert ledger["system"] == "IEEE-39"
    assert ledger["verdict"] in {"PASS", "NEGATIVE"}
    for regime in ("noiseless", "noisy"):
        m = ledger["metrics"][regime]
        assert np.isfinite(m["frobenius_rel_error"])
        assert 0.0 <= m["topology_f1"] <= 1.0


# ---------------------------------------------------------------------------
# CALIB-GRID-001 R1 — second-order (swing) identification path
# ---------------------------------------------------------------------------


def _swing_traj(
    k: np.ndarray,
    p: np.ndarray,
    m: np.ndarray,
    d: np.ndarray,
    *,
    dt: float,
    n: int,
    theta0: np.ndarray,
) -> np.ndarray:
    """RK4 integration of the swing model m θ̈ + d θ̇ = P − Σ K sin(θ_i−θ_j).

    Returns the (n+1, N) unwrapped phase trajectory. Used to build a
    *matched* second-order data set for the swing estimator.
    """
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


def _wrap_pm(traj: np.ndarray, dt: float, ids: tuple[str, ...]) -> PhaseMatrix:
    wrapped = np.mod(traj, 2.0 * np.pi)
    wrapped = np.clip(wrapped, 0.0, np.nextafter(2.0 * np.pi, 0.0))
    return PhaseMatrix(
        theta=wrapped,
        timestamps=np.arange(wrapped.shape[0], dtype=np.float64) * dt,
        asset_ids=ids,
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )


@pytest.mark.slow
@settings(max_examples=6, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_property_swing_exact_recovery_matched_noiseless(seed: int) -> None:
    """NON_PHYSICS: swing-estimator recovery soundness (calibration instrument), not a registered physics invariant.
    Noiseless, *matched* full-swing data → tight (K, P, ω) recovery.

    On a well-excited (non-phase-locked) trajectory generated by the
    exact swing model, the swing-aware symmetric estimator recovers the
    signed coupling, injection and natural frequency to a small relative
    error. This is the recovery property that must hold for the R1 path
    to be a sound instrument; it isolates the estimator from the
    second-order *model-class* mismatch the parent artifact localized.
    """
    rng = np.random.default_rng(seed)
    k = np.array(
        [[0.0, 0.9, 0.5], [0.9, 0.0, 0.7], [0.5, 0.7, 0.0]],
        dtype=np.float64,
    )
    p = np.array([0.6, -0.1, -0.5], dtype=np.float64)
    p = p - p.mean()
    m = np.array([0.4, 0.5, 0.3], dtype=np.float64)
    d = np.array([0.25, 0.3, 0.2], dtype=np.float64)
    # A persistently exciting initial displacement (kept moderate so the
    # rotors ring rather than slew monotonically to the locked state).
    theta0 = rng.uniform(-0.8, 0.8, size=3).astype(np.float64)
    theta0 -= theta0.mean()
    traj = _swing_traj(k, p, m, d, dt=0.005, n=8000, theta0=theta0)
    pm = _wrap_pm(traj, 0.005, ("a", "b", "c"))

    # This property is scoped (docstring) to a *well-excited,
    # non-phase-locked* trajectory. A random θ₀ can occasionally produce
    # a draw that slews monotonically to the locked state — the swing
    # design is then rank-deficient and the estimator *correctly*
    # fail-closes with the typed PersistentExcitationError (that is the
    # right behaviour, not a recovery failure). Reject such draws so the
    # property tests what it claims: recovery *given* persistent
    # excitation. The fail-closed behaviour itself is covered by
    # test_swing_pe_guard_fires_on_phase_locked_input. No gate or
    # threshold is weakened.
    try:
        est = estimate_swing_coupling(pm, m, d, dt=0.005, savgol_window=7, savgol_polyorder=4)
    except PersistentExcitationError:
        # Unconditionally reject this (out-of-scope) draw.
        assume(False)
        raise AssertionError("unreachable: assume(False) rejects the draw")
    k_rel = float(np.linalg.norm(est.K - k) / np.linalg.norm(k))
    p_rel = float(np.linalg.norm(est.injection - p) / np.linalg.norm(p))
    assert est.K.shape == (3, 3)
    assert np.allclose(np.diag(est.K), 0.0)
    np.testing.assert_allclose(est.K, est.K.T, atol=1e-12)  # symmetric by construction
    assert k_rel < 0.10, f"swing K recovery too poor on matched data: {k_rel:.3f}"
    assert p_rel < 0.15, f"swing P recovery too poor on matched data: {p_rel:.3f}"


def test_swing_pe_guard_fires_on_phase_locked_input() -> None:
    """NON_PHYSICS: persistent-excitation fail-closed guard, not a registered physics invariant.
    A constructed phase-locked trajectory trips the PE guard.

    When every relative angle is constant the regressor columns
    ``sin(θ_i−θ_j)`` are constant: the design is rank-deficient and the
    swing path must fail closed with the typed
    :class:`PersistentExcitationError` rather than emit a biased ``K̂``.
    """
    t_len = 600
    # Rigidly rotating cluster: θ_i(t) = φ_i + Ω t (same Ω for all i),
    # so θ_i − θ_j ≡ φ_i − φ_j (constant) — zero persistent excitation.
    phi = np.array([0.0, 0.4, -0.3], dtype=np.float64)
    omega_common = 0.2
    t = np.arange(t_len, dtype=np.float64) * 0.01
    traj = phi[None, :] + omega_common * t[:, None]
    pm = _wrap_pm(traj, 0.01, ("a", "b", "c"))
    m = np.ones(3, dtype=np.float64)
    d = np.full(3, 0.2, dtype=np.float64)

    with pytest.raises(PersistentExcitationError) as exc:
        estimate_swing_coupling(pm, m, d, dt=0.01, pe_guard=True)
    assert exc.value.singular_ratio < exc.value.threshold

    # With the guard disabled the diagnostic is still reported (and the
    # estimate is returned for sweeps only — no silent failure).
    est = estimate_swing_coupling(pm, m, d, dt=0.01, pe_guard=False)
    assert est.min_singular_ratio < 1e-3


def test_swing_estimator_contract_fail_closed() -> None:
    """NON_PHYSICS: swing-estimator contract guard, not a registered physics invariant. Swing estimator rejects contract violations (no silent repair)."""
    pm = _wrap_pm(
        _swing_traj(
            np.array([[0.0, 0.5], [0.5, 0.0]]),
            np.array([0.1, -0.1]),
            np.array([0.4, 0.4]),
            np.array([0.2, 0.2]),
            dt=0.01,
            n=200,
            theta0=np.array([0.3, -0.3]),
        ),
        0.01,
        ("a", "b"),
    )
    with pytest.raises(ValueError, match="dt"):
        estimate_swing_coupling(pm, np.ones(2), np.full(2, 0.2), dt=0.0)
    with pytest.raises(ValueError, match="inertia"):
        estimate_swing_coupling(pm, np.zeros(2), np.full(2, 0.2), dt=0.01)
    with pytest.raises(ValueError, match="shape"):
        estimate_swing_coupling(pm, np.ones(3), np.full(3, 0.2), dt=0.01)
    with pytest.raises(ValueError, match="savgol"):
        estimate_swing_coupling(pm, np.ones(2), np.full(2, 0.2), dt=0.01, savgol_window=3)


@pytest.mark.slow
def test_r1_swing_path_closes_noiseless_frobenius_gate() -> None:
    """NON_PHYSICS: R1 gate fact-pin (admissibility ledger), not a registered physics invariant.
    R1 fact-pin: the swing path flips `noiseless.frobenius` to PASS.

    Estimator-only change, frozen gates. This pins the *measured* R1
    outcome so a future regression of the swing path is caught: the
    noiseless Frobenius gate now passes (parent: 1.046 fail) and the
    antisymmetric residual is eliminated, while the overall verdict is
    still NEGATIVE (critical-coupling and noisy regime still fail). No
    promotion language: this is a pinned numeric state, not a claim of
    validation.
    """
    sys = wscc_9_bus()
    cfg = SimConfig()
    nl = run_calibration(sys, cfg, noisy=False, estimator_path="swing")
    ny = run_calibration(sys, cfg, noisy=True, estimator_path="swing")
    res = evaluate_gates(nl, NOISELESS_GATES) + evaluate_gates(ny, NOISY_GATES)
    by_name = {r.name: r for r in res}

    # The localized R1 win: first-order/antisymmetric defect closed.
    assert by_name["noiseless.frobenius"].passed
    assert nl.frobenius_rel_error < 0.10
    assert nl.extra["antisymmetric_residual_fro"] < 1e-9
    assert by_name["noiseless.topology_f1"].passed
    # Honest residual: overall verdict stays NEGATIVE (next defects).
    assert not by_name["noiseless.critical_coupling"].passed
    assert not by_name["noisy.frobenius"].passed
    assert overall_verdict(res) == "NEGATIVE"


def test_r1_first_order_path_is_bit_stable() -> None:
    """NON_PHYSICS: frozen-artifact bit-stability detector (admissibility infra), not a registered physics invariant.
    The frozen first-order NEGATIVE artifact is unchanged by R1.

    The default `estimator_path="first_order"` must reproduce the
    pre-registered parent metrics so the frozen-gate drift discipline
    holds (R1 is strictly additive).
    """
    sys = wscc_9_bus()
    cfg = SimConfig()
    nl = run_calibration(sys, cfg, noisy=False)
    nl_explicit = run_calibration(sys, cfg, noisy=False, estimator_path="first_order")
    assert nl.frobenius_rel_error == nl_explicit.frobenius_rel_error
    assert nl.topology_f1 == nl_explicit.topology_f1
    # Parent ledger value (frozen): noiseless Frobenius ≈ 1.0459.
    assert abs(nl.frobenius_rel_error - 1.0459) < 1e-3


@pytest.mark.slow
def test_r1_ledger_is_machine_readable_and_sha_pinned() -> None:
    """NON_PHYSICS: R1 sha-pinned ledger serialization (admissibility infra), not a registered physics invariant.
    build_r1_ledger emits a JSON-serialisable, sha-pinned R1 ledger.

    Cites the frozen pre-registration and parent ledger sha; the gate
    thresholds are read (not redefined) so the verdict cannot drift.
    """
    sys = wscc_9_bus()
    ledger = build_r1_ledger(sys, SimConfig())
    blob = json.dumps(ledger, sort_keys=True)
    assert json.loads(blob)["verdict"] == "NEGATIVE"
    assert ledger["lineage"] == "R1"
    assert ledger["is_hypothesis"] is False
    assert (  # pragma: allowlist secret  (audited: parent prereg git sha, not a credential)
        ledger["frozen_preregistration_sha"]
        == "d170d48afa5066c13edeb40b2c1904b3fd708516"  # pragma: allowlist secret
    )
    # audited: parent calibration ledger content hash, not a credential
    assert (
        ledger["parent_ledger_sha256"]
        == "ed8d409b7b222eb053572d6bf9ab6e98c5f4918be1cae384864733a2b4d72aaf"  # pragma: allowlist secret
    )
    assert len(ledger["ledger_sha256"]) == 64
    assert ledger["localized_refinement_targets"]


def _deep_close(a: Any, b: Any, *, rel: float = 1e-6, abs_: float = 1e-9) -> bool:
    """Structure-exact, numeric-tolerant equality.

    These ``*_results_json_matches_committed_artifact`` checks are
    post-data-edit detectors, not numerical-precision assertions. BLAS
    thread-order reductions on ill-conditioned swing/regression metrics
    (e.g. CG-002 front-gate r²/Frobenius) jitter beyond 1e-9 *relative*
    on some CI runners — verified: cg002 reproduces locally yet diverges
    in the last ~3 digits on CI (pure nondeterminism, not a metric
    change). A genuine post-data edit shifts these metrics by orders of
    magnitude more than the chosen rel=1e-6 / abs=1e-9 window, so the
    detector stays sharp while no longer flaking on float-reduction
    order. Structure / keys / bools / ints stay exact. WHY-loosened per
    CLAUDE.md: bound widened with explicit cause (CI BLAS nondeterminism),
    not to paper over a real regression.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_deep_close(a[k], b[k], rel=rel, abs_=abs_) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_deep_close(x, y, rel=rel, abs_=abs_) for x, y in zip(a, b))
    return bool(a == b)


def test_r1_results_json_matches_committed_artifact() -> None:
    """NON_PHYSICS: committed-artifact post-data-edit detector (admissibility infra), not a registered physics invariant.
    The committed r1/RESULTS.json verdict/gates match a fresh build.

    Determinism + post-data-edit detector for the R1 artifact: the
    sha-pinned file must reproduce (gate names, observed values, pass
    flags). ``branch_sha`` / ``ledger_sha256`` are provenance fields
    that legitimately move with the commit and are excluded.
    """
    art = (
        Path(__file__).resolve().parents[3]
        / "research"
        / "calibration"
        / "grid_kuramoto"
        / "r1"
        / "RESULTS.json"
    )
    committed = json.loads(art.read_text(encoding="utf-8"))
    fresh = build_r1_ledger(wscc_9_bus(), SimConfig())
    assert committed["verdict"] == fresh["verdict"] == "NEGATIVE"
    assert _deep_close(committed["gates"], fresh["gates"])
    assert _deep_close(committed["metrics"], fresh["metrics"])


# ---------------------------------------------------------------------------
# Upgrade lineage #2 — graded identifiability front-gate (reliability infra)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_front_gate_accepts_noiseless_refuses_noisy() -> None:
    """NON_PHYSICS: identifiability front-gate envelope (calibration instrument), not a registered physics invariant.
    The two pre-registered cases: noiseless ACCEPT, σ=0.02 REFUSE.

    Instrument-honesty validation (MEASURED tier). It does NOT touch the
    frozen pre-registration/gates/seeds/σ/θ₀ and does NOT close the
    `noisy.frobenius` gate — it asserts the upgraded estimator now
    self-reports its envelope on the exact frozen calibration cases:

    * noiseless WSCC-9 → ACCEPT with a tight CRLB band (band width ≪
      |K̂|) and the model adequate (R² high);
    * σ=0.02 noisy → REFUSE (R² noise-dominated) instead of the
      ~20×-biased point estimate the parent lineage exposed.
    """
    from research.calibration.grid_kuramoto.identifiability.validate import (
        build_identifiability_ledger,
    )

    led = build_identifiability_ledger(wscc_9_bus(), SimConfig())
    assert led["is_science_claim"] is False
    assert led["closes_noisy_gate"] is False

    nl = led["front_gate"]["noiseless"]
    ny = led["front_gate"]["noisy"]

    # Noiseless: instrument declares itself in envelope.
    assert nl["verdict"] == "ACCEPT"
    assert nl["score"] > led["theory_constants"]["refuse_score"]
    assert nl["r_squared"] >= 0.5  # model adequate
    # Tight band: every edge's CRLB half-width ≪ |K̂| and excludes 0.
    for e in nl["edges"]:
        assert not e["ci_contains_zero"]
        width = abs(e["ci_high"] - e["ci_low"])
        assert width < abs(e["k_hat"]), (
            f"noiseless CRLB band not tight on edge {e['edge']}: "
            f"width {width:.4g} ≥ |K̂| {abs(e['k_hat']):.4g}"
        )

    # σ=0.02: instrument declares itself OUT of envelope (REFUSE) — the
    # parent lineage's silent ~20×-biased K̂ is now self-evident.
    assert ny["verdict"] == "REFUSE"
    assert ny["score"] < led["theory_constants"]["refuse_score"]
    assert ny["r_squared"] < 0.5  # noise-dominated fit
    assert "REFUSE" in ny["reason"]


@pytest.mark.slow
def test_front_gate_does_not_close_frozen_noisy_gate() -> None:
    """NON_PHYSICS: frozen-gate non-interference rail (admissibility infra), not a registered physics invariant.
    The frozen `noisy.frobenius` gate STAYS NEGATIVE (not closed).

    Explicit honesty rail: the upgrade makes the noisy failure
    self-evident; it must NOT improve the frozen metric. The swing
    noisy Frobenius error must still massively exceed the frozen 0.25
    threshold, and the R1 verdict must still be NEGATIVE.
    """
    from research.calibration.grid_kuramoto.identifiability.validate import (
        build_identifiability_ledger,
    )

    led = build_identifiability_ledger(wscc_9_bus(), SimConfig())
    ny = led["front_gate"]["noisy"]
    # Frozen NOISY_GATES threshold for noisy.frobenius is 0.25.
    noisy_frob_threshold = {g.name: g.threshold for g in NOISY_GATES}["noisy.frobenius"]
    assert noisy_frob_threshold == 0.25
    assert ny["frobenius_rel_error"] > noisy_frob_threshold, (
        "the front-gate must NOT close the frozen noisy.frobenius gate; "
        f"swing noisy Frobenius {ny['frobenius_rel_error']:.4f} must "
        f"still exceed the frozen threshold {noisy_frob_threshold}"
    )

    # The R1 calibration verdict is unchanged (still NEGATIVE) — the
    # graded layer is additive and reads, never redefines, the gates.
    sys = wscc_9_bus()
    cfg = SimConfig()
    res = evaluate_gates(
        run_calibration(sys, cfg, noisy=False, estimator_path="swing"),
        NOISELESS_GATES,
    ) + evaluate_gates(
        run_calibration(sys, cfg, noisy=True, estimator_path="swing"),
        NOISY_GATES,
    )
    assert overall_verdict(res) == "NEGATIVE"


@pytest.mark.slow
def test_front_gate_first_order_path_bit_stable() -> None:
    """NON_PHYSICS: frozen first-order artifact bit-stability detector (admissibility infra), not a registered physics invariant.
    The default first-order frozen artifact is byte-unchanged.

    The identifiability gate is opt-in and only on the symmetric swing
    path; the frozen first-order CALIB-GRID-001 ledger must reproduce
    exactly (frozen-gate drift discipline — strictly additive upgrade).
    """
    sys = wscc_9_bus()
    cfg = SimConfig()
    nl = run_calibration(sys, cfg, noisy=False)
    nl_explicit = run_calibration(sys, cfg, noisy=False, estimator_path="first_order")
    assert nl.frobenius_rel_error == nl_explicit.frobenius_rel_error
    assert nl.topology_f1 == nl_explicit.topology_f1
    # Parent ledger value (frozen): noiseless Frobenius ≈ 1.0459.
    assert abs(nl.frobenius_rel_error - 1.0459) < 1e-3


@pytest.mark.slow
def test_identifiability_results_json_matches_committed_artifact() -> None:
    """NON_PHYSICS: committed identifiability-artifact detector (admissibility infra), not a registered physics invariant.
    Committed identifiability/RESULTS.json reproduces (post-edit detector).

    Structure-exact, numeric-tolerant: verdicts and scores must
    reproduce; ``branch_sha`` / ``ledger_sha256`` legitimately move with
    the commit and are excluded.
    """
    from research.calibration.grid_kuramoto.identifiability.validate import (
        build_identifiability_ledger,
    )

    art = (
        Path(__file__).resolve().parents[3]
        / "research"
        / "calibration"
        / "grid_kuramoto"
        / "identifiability"
        / "RESULTS.json"
    )
    committed = json.loads(art.read_text(encoding="utf-8"))
    fresh = build_identifiability_ledger(wscc_9_bus(), SimConfig())
    assert committed["closes_noisy_gate"] is fresh["closes_noisy_gate"] is False
    assert committed["is_science_claim"] is fresh["is_science_claim"] is False
    for regime in ("noiseless", "noisy"):
        assert committed["front_gate"][regime]["verdict"] == fresh["front_gate"][regime]["verdict"]
        assert _deep_close(committed["front_gate"][regime], fresh["front_gate"][regime])


# ---------------------------------------------------------------------------
# CALIB-GRID-002 — integral / weak-form swing identifier (new lineage)
# ---------------------------------------------------------------------------

_CG002_PREREG = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "calibration"
    / "grid_kuramoto"
    / "cg002"
    / "PREREGISTRATION_002.yaml"
)


def test_cg002_preregistration_matches_code() -> None:
    """NON_PHYSICS: CG002 pre-registration vs code agreement (admissibility infra), not a registered physics invariant.
    No-peek: PREREGISTRATION_002.yaml mirrors cg002.py constants.

    Binds the frozen weak-form solver constants and every gate
    threshold to the pre-registered document. Changing either side
    without the other fails closed (post-data-edit detector).
    """
    from research.calibration.grid_kuramoto.cg002.cg002 import (
        CG002_BUMP_ORDER,
        CG002_N_WINDOWS,
        CG002_NOISELESS_GATES,
        CG002_NOISY_GATES,
        CG002_NULL_FPR_GATE,
        CG002_TEST_SUPPORT,
        CG002_THEOREM_GATE,
    )

    text = _CG002_PREREG.read_text(encoding="utf-8")
    assert f"bump_order: {CG002_BUMP_ORDER}" in text
    assert f"test_support: {CG002_TEST_SUPPORT}" in text
    assert f"n_windows: {CG002_N_WINDOWS}" in text
    assert "pe_min_singular_ratio_is_PE_HARD_FLOOR: true" in text
    for gate in (
        *CG002_NOISELESS_GATES,
        *CG002_NOISY_GATES,
        CG002_THEOREM_GATE,
        CG002_NULL_FPR_GATE,
    ):
        assert gate.name in text, f"{gate.name} missing from PREREGISTRATION_002.yaml"
        assert f"threshold: {gate.threshold}" in text
        assert f'operator: "{gate.operator}"' in text


def test_cg002_gate_thresholds_are_frozen_values() -> None:
    """NON_PHYSICS: CG002 frozen-gate post-data detector (admissibility infra), not a registered physics invariant. Lock the exact pre-registered CG002 numbers (post-data detector)."""
    from research.calibration.grid_kuramoto.cg002.cg002 import (
        CG002_NOISELESS_GATES,
        CG002_NOISY_GATES,
        CG002_NULL_FPR_GATE,
        CG002_THEOREM_GATE,
    )

    nl = {g.name: (g.operator, g.threshold) for g in CG002_NOISELESS_GATES}
    ny = {g.name: (g.operator, g.threshold) for g in CG002_NOISY_GATES}
    assert nl == {
        "cg002.noiseless.frobenius": ("<=", 0.10),
        "cg002.noiseless.topology_f1": (">=", 0.95),
    }
    assert ny == {
        "cg002.noisy.frobenius": ("<=", 0.25),
        "cg002.noisy.topology_f1": (">=", 0.90),
    }
    assert (CG002_THEOREM_GATE.operator, CG002_THEOREM_GATE.threshold) == ("<=", 0.15)
    assert (CG002_NULL_FPR_GATE.operator, CG002_NULL_FPR_GATE.threshold) == ("<=", 0.05)


def test_cg002_does_not_touch_frozen_calib_grid_001_gates() -> None:
    """NON_PHYSICS: cross-lineage frozen-gate non-interference rail (admissibility infra), not a registered physics invariant.
    CALIB-GRID-002 is a NEW lineage; the frozen R1 gates are unchanged.

    Frozen-gate non-interference rail: the five CALIB-GRID-001 / R1
    thresholds must still be exactly the pre-registered values and the
    R1 verdict must still be NEGATIVE — CG002 carries its own gates.
    """
    nl = {g.name: (g.operator, g.threshold) for g in NOISELESS_GATES}
    ny = {g.name: (g.operator, g.threshold) for g in NOISY_GATES}
    assert nl == {
        "noiseless.frobenius": ("<=", 0.10),
        "noiseless.topology_f1": (">=", 0.95),
        "noiseless.critical_coupling": ("<=", 0.15),
    }
    assert ny == {
        "noisy.frobenius": ("<=", 0.25),
        "noisy.topology_f1": (">=", 0.90),
    }


@pytest.mark.slow
def test_cg002_verdict_is_negative_and_localized() -> None:
    """NON_PHYSICS: CG002 pinned NEGATIVE verdict (admissibility ledger), not a registered physics invariant.
    The integral form does NOT close the frozen noisy regime.

    Pins the honest sha-pinned NEGATIVE: noiseless Frobenius PASSES
    (≤0.10, no regression vs R1's 0.0666) and the noisy Frobenius is
    massively better than R1's 16.6 but still FAILS the frozen 0.25
    target — the falsifiable claim is FALSIFIED for the noisy regime.
    No promotion language; this pins a measured numeric state.
    """
    from research.calibration.grid_kuramoto.cg002 import (
        build_cg002_ledger,
        run_cg002_calibration,
    )

    nl = run_cg002_calibration(wscc_9_bus(), SimConfig(), noisy=False)
    ny = run_cg002_calibration(wscc_9_bus(), SimConfig(), noisy=True)

    # Noiseless: integral class is sound and does not regress vs R1.
    assert nl.frobenius_rel_error <= 0.10
    assert nl.frobenius_rel_error < 0.0666  # strictly better than R1
    assert nl.topology_f1 >= 0.95
    assert nl.front_gate_verdict == "ACCEPT"

    # Noisy: massively better than R1 (16.6) but still fails ≤0.25.
    assert ny.frobenius_rel_error < 1.0  # ≫ better than R1's 16.6
    assert ny.frobenius_rel_error > 0.25  # still FAILS the frozen target
    assert ny.front_gate_verdict == "REFUSE"  # claim #2↔#1 FALSIFIED

    led = build_cg002_ledger(wscc_9_bus(), SimConfig())
    assert led["verdict"] == "NEGATIVE"
    assert led["is_science_claim"] is False
    assert led["failed_gates"]


@pytest.mark.slow
def test_cg002_front_gate_refuse_under_differential_and_integral() -> None:
    """NON_PHYSICS: CG002 before/after REFUSE rail (calibration instrument), not a registered physics invariant.
    Before→after rail: σ=0.02 REFUSEs under BOTH estimator classes.

    The pre-registered claim was that the integral form would flip the
    front-gate to ACCEPT at σ=0.02. It does NOT — the regressor-level
    SNR floor keeps R² noise-dominated for both classes. This rail pins
    the honest FALSIFIED outcome (REFUSE → REFUSE) on the same frozen
    σ=0.02 trajectory.
    """
    from research.calibration.grid_kuramoto.calibration import (
        ground_truth,
        simulate_phases,
    )

    sys = wscc_9_bus()
    cfg = SimConfig()

    # Differential R1 path at σ=0.02 → REFUSE (the merged behaviour).
    k_true, omega_true = ground_truth(sys, cfg.coupling_scale)
    phases, _ = simulate_phases(sys, k_true, omega_true, cfg)
    diff_est = estimate_swing_coupling(
        phases,
        np.asarray(sys.inertia, dtype=np.float64),
        np.asarray(sys.damping, dtype=np.float64),
        dt=cfg.dt,
        symmetric=True,
        savgol_window=7,
        savgol_polyorder=4,
        pe_guard=True,
        identifiability_gate=True,
    )
    assert diff_est.identifiability is not None
    assert diff_est.identifiability.verdict.value == "REFUSE"

    # Integral path on the SAME frozen σ=0.02 case → still REFUSE.
    from research.calibration.grid_kuramoto.cg002 import recover_coupling_integral

    rec = recover_coupling_integral(sys, cfg, noisy=True)
    assert rec.front_verdict == "REFUSE"


@pytest.mark.slow
def test_cg002_null_battery_specificity_reported() -> None:
    """NON_PHYSICS: CG002 null-battery FPR reporting (specificity infra), not a registered physics invariant.
    The null battery runs and its FPR is reported (not silently hidden).

    The pre-registered FPR target is ≤0.05; the measured value (≈0.10
    on the 3-edge WSCC-9 small graph) is a reported specificity
    limitation, NOT masked — the NEGATIVE verdict already reflects it.
    """
    from research.calibration.grid_kuramoto.cg002 import null_battery_fpr

    fpr, detail = null_battery_fpr(wscc_9_bus(), SimConfig())
    assert 0.0 <= fpr <= 1.0
    assert detail["n_trials"] >= 2
    assert "shuffle_null" in detail and "placebo_null" in detail
    # The placebo (no weight contrast) must be clean — low dispersion.
    assert detail["placebo_dispersion"] < 1.0


@pytest.mark.slow
def test_cg002_results_json_matches_committed_artifact() -> None:
    """NON_PHYSICS: committed CG002-artifact post-data detector (admissibility infra), not a registered physics invariant.
    Committed cg002/RESULTS.json reproduces (post-data-edit detector).

    Structure-exact, numeric-tolerant: verdict and gate pass-flags must
    reproduce; ``ledger_sha256`` legitimately moves with the commit
    only if a numeric drifts, so the verdict + gate booleans are pinned.
    """
    from research.calibration.grid_kuramoto.cg002 import build_cg002_ledger

    art = (
        Path(__file__).resolve().parents[3]
        / "research"
        / "calibration"
        / "grid_kuramoto"
        / "cg002"
        / "RESULTS.json"
    )
    committed = json.loads(art.read_text(encoding="utf-8"))
    fresh = build_cg002_ledger(wscc_9_bus(), SimConfig())
    assert committed["verdict"] == fresh["verdict"] == "NEGATIVE"
    assert committed["is_science_claim"] is fresh["is_science_claim"] is False
    assert _deep_close(committed["metrics"], fresh["metrics"])
    cg = {g["name"]: g["passed"] for g in committed["gates"]}
    fg = {g["name"]: g["passed"] for g in fresh["gates"]}
    assert cg == fg
