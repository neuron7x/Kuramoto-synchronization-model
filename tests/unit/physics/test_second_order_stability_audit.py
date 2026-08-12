# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Issue #1109 — bounded SecondOrderStabilityAudit + promotion firewall.

Closes the gaps the runtime guard (non-finite + RoCoF) leaves open. Each test
pins a measured numerical-stability diagnostic of the symplectic Störmer–Verlet
second-order Kuramoto integrator and would fail if that property degraded. The
firewall tests pin that the audit can never silently promote S7 stability and
that an invalid energy model fails closed rather than emitting a hollow pass.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.coupling_spec import CLAIM_SIGNED
from core.kuramoto.second_order import (
    SecondOrderKuramotoEngine,
    SecondOrderStabilityReport,
    _swing_energy_trajectory,
)


def _conservative_engine() -> SecondOrderKuramotoEngine:
    """ω≡0, d≡0 — the regime where swing energy must be (near-)conserved."""
    n = 6
    cfg = KuramotoConfig(
        N=n,
        K=2.0,
        omega=np.zeros(n),
        theta0=np.linspace(0.0, 1.0, n),
        dt=0.005,
        steps=400,
        seed=0,
    )
    return SecondOrderKuramotoEngine(
        cfg, mass=1.0, damping=0.0, velocity0=0.1 * np.ones(n)
    )


def test_streamed_swing_energy_matches_dense_formula() -> None:
    """Streamed O(N²) evaluator must preserve the previous dense formula."""
    theta = np.array(
        [
            [0.0, 0.2, 0.7, 1.1],
            [0.3, -0.4, 0.5, 1.4],
            [1.2, 0.1, -0.6, 0.8],
        ],
        dtype=np.float64,
    )
    vel = np.array(
        [
            [0.1, -0.2, 0.3, -0.4],
            [0.5, 0.0, -0.3, 0.2],
            [-0.1, 0.4, 0.2, -0.5],
        ],
        dtype=np.float64,
    )
    mass = np.array([1.0, 2.0, 1.5, 0.75], dtype=np.float64)
    omega = np.array([0.2, -0.1, 0.3, -0.4], dtype=np.float64)
    adj = np.array(
        [
            [0.0, 0.7, 0.2, 0.0],
            [0.7, 0.0, 0.5, 0.1],
            [0.2, 0.5, 0.0, 0.4],
            [0.0, 0.1, 0.4, 0.0],
        ],
        dtype=np.float64,
    )

    streamed = _swing_energy_trajectory(theta, vel, mass, omega, adj)

    kinetic = 0.5 * (mass * vel * vel).sum(axis=1)
    drive = -(omega * theta).sum(axis=1)
    delta = theta[:, np.newaxis, :] - theta[:, :, np.newaxis]
    dense_pairwise = -0.5 * np.einsum("ij,tij->t", adj, np.cos(delta))
    expected = kinetic + drive + dense_pairwise

    np.testing.assert_allclose(streamed, expected, rtol=0.0, atol=1e-12)


def test_energy_like_drift_bound() -> None:
    """Symplectic Verlet keeps swing energy bounded in the conservative regime.

    A non-symplectic / broken integrator would drift secularly; the relative
    energy drift must stay tiny (≤1e-3) for ω≡0, d≡0.
    """
    report = _conservative_engine().audit()
    assert report.energy_conservative_regime is True
    assert report.energy_like_drift >= 0.0
    assert report.energy_like_drift <= 1e-3, (
        f"swing-energy drift {report.energy_like_drift:.3e} exceeds 1e-3 in the "
        f"conservative regime — symplectic conservation (INV-K8/K9) degraded."
    )


def test_phase_spread_bound() -> None:
    """Phase spread is finite and reported; a runaway would be non-finite/huge."""
    report = _conservative_engine().audit()
    assert report.phase_spread_finite is True
    assert np.isfinite(report.phase_spread_bound)
    assert report.phase_spread_bound >= 0.0


def test_solver_metadata_present() -> None:
    """The integrator is identified, with order/symplecticity/step policy."""
    meta = _conservative_engine().audit().solver_metadata
    assert meta["integrator"] == "stoermer_verlet"
    assert meta["order"] == 2
    assert meta["symplectic"] is True
    assert meta["adaptive"] is False
    assert meta["fixed_step"] is True
    assert meta["dt"] == pytest.approx(0.005)
    # fixed-step integrator has no tolerance knobs — declared null, not faked.
    assert meta["rtol"] is None
    assert meta["atol"] is None


def test_stiffness_regime_declared() -> None:
    """Stiffness ratio = ω_fast·dt is computed and the regime labelled.

    A well-resolved run (small dt, modest K) is 'resolved'; a coarse, strongly
    coupled run is 'underresolved_stiff'.
    """
    resolved = _conservative_engine().audit()
    assert resolved.stiffness_regime == "resolved"
    assert 0.0 <= resolved.stiffness_ratio <= 0.1

    n = 6
    stiff_cfg = KuramotoConfig(
        N=n,
        K=50.0,
        omega=np.zeros(n),
        theta0=np.linspace(0.0, 1.0, n),
        dt=0.2,
        steps=20,
        seed=0,
    )
    stiff = SecondOrderKuramotoEngine(stiff_cfg, mass=1.0, damping=0.0).audit(
        cross_solver_steps=10, agreement_tol=1.0
    )
    assert stiff.stiffness_ratio > 1.0
    assert stiff.stiffness_regime == "underresolved_stiff"


def test_cross_solver_reference_agreement() -> None:
    """The engine's Verlet trajectory agrees with an independent RK4 solver.

    Over a short, well-resolved horizon the two integrators must match to the
    audit tolerance — evidence the trajectory is correct, not self-consistent.
    """
    report = _conservative_engine().audit(cross_solver_steps=100, agreement_tol=1e-3)
    assert report.cross_solver_reference == "explicit_rk4"
    assert report.cross_solver_agrees is True
    assert report.cross_solver_max_deviation <= 1e-3


def test_damped_run_loses_energy_monotonically() -> None:
    """With damping the swing energy must not be claimed conserved.

    Sanity: the conservative flag is False once d>0, so no false conservation
    claim is emitted for a dissipative run.
    """
    n = 6
    cfg = KuramotoConfig(
        N=n,
        K=2.0,
        omega=np.zeros(n),
        theta0=np.linspace(0.0, 1.0, n),
        dt=0.005,
        steps=300,
        seed=0,
    )
    report = SecondOrderKuramotoEngine(
        cfg, mass=1.0, damping=0.3, velocity0=0.5 * np.ones(n)
    ).audit()
    assert report.energy_conservative_regime is False


def test_report_is_frozen_and_complete() -> None:
    report = _conservative_engine().audit()
    assert isinstance(report, SecondOrderStabilityReport)
    assert report.audit_scope == "energy_phase_solver_stiffness_crosssolver"
    # remaining gaps are explicitly preserved — the audit is not over-claimed full.
    assert "full_lyapunov_spectrum" in report.remaining_gaps
    with pytest.raises((AttributeError, TypeError)):
        setattr(report, "energy_like_drift", 0.0)


def _signed_asymmetric_engine() -> SecondOrderKuramotoEngine:
    """Conservative regime BUT an asymmetric, signed coupling matrix.

    The swing-energy potential V = −½Σ adjᵢⱼ cos(Δθ) is conserved only for a
    symmetric, unsigned adjacency, so the energy diagnostic is invalid here.
    """
    n = 4
    adj = np.array(
        [
            [0.0, 1.0, -0.5, 0.0],
            [0.2, 0.0, 1.0, 0.0],  # asymmetric (0.2 ≠ 1.0) and signed (−0.5)
            [-0.5, 1.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    cfg = KuramotoConfig(
        N=n,
        K=1.0,
        omega=np.zeros(n),
        theta0=np.linspace(0.0, 1.0, n),
        adjacency=adj,
        # The signed/asymmetric adjacency above is the whole point of this
        # fixture (it invalidates the swing-energy claim), so it must declare
        # the signed claim boundary: the attractive-only default rejects
        # negative weights at construction (a later-merged KuramotoConfig
        # validator), which would otherwise mask the audit logic under test.
        claim_boundary=CLAIM_SIGNED,
        dt=0.005,
        steps=200,
        seed=0,
    )
    return SecondOrderKuramotoEngine(
        cfg, mass=1.0, damping=0.0, velocity0=0.05 * np.ones(n)
    )


def test_failed_audit_blocks_stability_promotion() -> None:
    """promotion_allowed is structurally False, and a failing check sets it too.

    Even a clean conservative run is never promotable (remaining_gaps non-empty),
    and an audit that fails an in-scope check has audit_passed=False with a
    named reason — no silent pass.
    """
    clean = _conservative_engine().audit()
    assert clean.audit_passed is True
    assert clean.promotion_allowed is False  # open gaps ⇒ never a stability cert
    assert clean.failure_reason == ()

    failed = _signed_asymmetric_engine().audit()
    assert failed.audit_passed is False
    assert failed.promotion_allowed is False
    assert "energy_conservation_claimed_on_invalid_model" in failed.failure_reason


def test_cross_solver_trajectory_wide_max() -> None:
    """Agreement is judged trajectory-wide, not at the endpoint alone.

    The trajectory-wide max spans every step in [0, horizon], so it is always
    ≥ the endpoint deviation — an endpoint that re-converges cannot hide a
    mid-trajectory divergence.
    """
    report = _conservative_engine().audit(cross_solver_steps=100, agreement_tol=1e-3)
    assert np.isfinite(report.trajectory_wide_cross_solver_max)
    assert report.trajectory_wide_cross_solver_max >= report.cross_solver_max_deviation
    assert report.trajectory_wide_cross_solver_max <= 1e-3
    assert report.metric_validity_flags["cross_solver_trajectory_wide"] is True


def test_energy_model_validity_flags() -> None:
    """A symmetric, unsigned adjacency yields a valid energy model."""
    flags = _conservative_engine().audit().metric_validity_flags
    assert flags["adjacency_symmetric"] is True
    assert flags["adjacency_unsigned"] is True
    assert flags["energy_model_valid"] is True


def test_asymmetric_or_signed_adjacency_invalidates_energy_claim() -> None:
    """Asymmetric/signed coupling invalidates the conservation diagnostic.

    energy_model_valid must be False and, in the conservative regime, the audit
    must fail closed rather than emit a meaningless energy-drift pass.
    """
    report = _signed_asymmetric_engine().audit()
    assert report.metric_validity_flags["adjacency_symmetric"] is False
    assert report.metric_validity_flags["adjacency_unsigned"] is False
    assert report.metric_validity_flags["energy_model_valid"] is False
    assert report.audit_passed is False
    assert "energy_conservation_claimed_on_invalid_model" in report.failure_reason


def _symmetric_signed_engine() -> SecondOrderKuramotoEngine:
    """Conservative regime, adjacency SYMMETRIC but SIGNED.

    Complements _signed_asymmetric_engine (which is both signed AND asymmetric).
    Here adjacency_symmetric is True yet adjacency_unsigned is False, so the
    energy-model validity is the AND of one True and one False operand — the
    case that distinguishes ``symmetric and unsigned`` from ``symmetric or
    unsigned`` (mutation_probe survivor, second_order.py L493).
    """
    n = 4
    adj = np.array(
        [
            [0.0, 1.0, -0.5, 0.0],
            [1.0, 0.0, 1.0, 0.0],
            [-0.5, 1.0, 0.0, 1.0],  # == adj.T but contains -0.5 (signed)
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    cfg = KuramotoConfig(
        N=n,
        K=1.0,
        omega=np.zeros(n),
        theta0=np.linspace(0.0, 1.0, n),
        adjacency=adj,
        claim_boundary=CLAIM_SIGNED,
        dt=0.005,
        steps=200,
        seed=0,
    )
    return SecondOrderKuramotoEngine(
        cfg, mass=1.0, damping=0.0, velocity0=0.05 * np.ones(n)
    )


def test_symmetric_signed_adjacency_invalidates_energy_model() -> None:
    """Symmetric BUT signed coupling: energy_model_valid must be False.

    energy_model_valid = adjacency_symmetric AND adjacency_unsigned. Here
    symmetric is True and unsigned is False, so AND gives False (the swing-energy
    potential is conserved only for symmetric *and* unsigned adjacency). This
    kills the L493 `and`->`or` mutant, under which symmetric=True alone would
    wrongly mark the energy model valid and run a meaningless drift check.
    """
    report = _symmetric_signed_engine().audit()
    assert report.metric_validity_flags["adjacency_symmetric"] is True
    assert report.metric_validity_flags["adjacency_unsigned"] is False
    assert report.metric_validity_flags["energy_model_valid"] is False
    assert report.audit_passed is False
    assert "energy_conservation_claimed_on_invalid_model" in report.failure_reason
    assert "energy_drift_exceeds_tol" not in report.failure_reason
