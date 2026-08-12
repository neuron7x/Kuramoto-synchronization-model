# SPDX-License-Identifier: MIT
"""T23 — Ott-Antonsen reduction + chimera state detection witnesses.

The Ott-Antonsen ansatz (2008) reduces the infinite-N Kuramoto model
to a single complex ODE for z(t). These witnesses verify the reduction
is exact by comparing analytical predictions with numerical integration.

INV-OA1: |z(t)| ≤ 1 always (order parameter on the unit disk)
INV-OA2: K > 2Δ ⟹ R_∞ = √(1 − 2Δ/K) (exact analytical steady state)
INV-OA3: K < 2Δ ⟹ R → 0 (subcritical decay, consistent with INV-K2)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.ott_antonsen import (
    OttAntonsenEngine,
    detect_chimera,
)


def test_ott_antonsen_order_parameter_bounded() -> None:
    """INV-OA1: |z(t)| ≤ 1 for every step of the Ott-Antonsen trajectory.

    Sweeps subcritical and supercritical regimes with various initial
    conditions. R(t) = |z(t)| must never exceed 1.
    """
    # epsilon: |z| ≤ 1 is a unit-disk constraint, no numerical slack
    scenarios = [
        (2.0, 0.5, 0.01),  # supercritical, small IC
        (2.0, 0.5, 0.99),  # supercritical, near-boundary IC
        (0.3, 0.5, 0.5),  # subcritical, mid IC
        (5.0, 0.1, 0.01),  # strongly supercritical
    ]
    for K, delta, R0 in scenarios:
        engine = OttAntonsenEngine(K=K, delta=delta)
        result = engine.integrate(T=30.0, dt=0.01, R0=R0)
        r_max = float(np.max(result.R))
        assert r_max <= 1.0 + 1e-12, (  # epsilon: numerical ULP slack only
            f"INV-OA1 VIOLATED: max R={r_max:.6f} > 1 at K={K}, delta={delta}, R0={R0}. "
            f"Expected |z(t)| ≤ 1 by unit-disk projection. "
            f"Observed at T=30, dt=0.01. "
            f"Physical reasoning: z = R·exp(iΨ) is a mean of unit phasors."
        )


def test_ott_antonsen_supercritical_steady_state() -> None:
    """INV-OA2: R_∞ = √(1 − 2Δ/K) for K > K_c = 2Δ.

    Compares the analytical steady state with the long-time limit of
    the ODE integration across a sweep of K values.
    """
    delta = 0.5
    K_c = 2.0 * delta
    # tolerance: RK4 at dt=0.01 converges to ~1e-4 of analytical
    convergence_tolerance = 1e-3  # epsilon: ODE integration accuracy

    for K in [1.5, 2.0, 3.0, 5.0, 10.0]:
        engine = OttAntonsenEngine(K=K, delta=delta)
        result = engine.integrate(T=100.0, dt=0.01, R0=0.01)
        R_analytical = math.sqrt(1.0 - K_c / K)
        R_numerical = float(result.R[-1])
        error = abs(R_numerical - R_analytical)
        assert error < convergence_tolerance, (
            f"INV-OA2 VIOLATED: R_numerical={R_numerical:.6f} vs "
            f"R_analytical={R_analytical:.6f}, error={error:.3e}. "
            f"Expected |R_num - √(1-2Δ/K)| < {convergence_tolerance}. "
            f"Observed at K={K}, delta={delta}, K_c={K_c}. "
            f"Physical reasoning: Ott-Antonsen ODE is EXACT in the "
            f"thermodynamic limit; RK4 at dt=0.01 should converge."
        )


def test_ott_antonsen_subcritical_decay() -> None:
    """INV-OA3: K < 2Δ ⟹ R → 0 (matches INV-K2 subcritical prediction).

    Starts from R0=0.5 and verifies exponential decay to zero.
    """
    delta = 0.5
    # tolerance: after T=100, subcritical R should be < 1e-4
    decay_tolerance = 1e-4  # epsilon: exponential decay target

    # K=0.99 excluded: critical slowing down at K→K_c makes decay
    # rate ∝ (K_c−K) = 0.01, requiring T >> 100 to reach tolerance.
    # This is correct physics, not a bug.
    for K in [0.1, 0.3, 0.5, 0.8]:
        engine = OttAntonsenEngine(K=K, delta=delta)
        result = engine.integrate(T=100.0, dt=0.01, R0=0.5)
        R_final = float(result.R[-1])
        assert R_final < decay_tolerance, (
            f"INV-OA3 VIOLATED: R_final={R_final:.6f} > {decay_tolerance} "
            f"at K={K} < K_c={2 * delta}. "
            f"Expected subcritical R → 0 exponentially. "
            f"Observed at delta={delta}, T=100, R0=0.5. "
            f"Physical reasoning: below K_c the incoherent state is the "
            f"only stable fixed point of the Ott-Antonsen ODE."
        )


@pytest.mark.heavy_math
def test_ott_antonsen_matches_n_body_kuramoto() -> None:
    """INV-OA2 cross-validation: Ott-Antonsen R_∞ matches N-body simulation.

    Runs the full Kuramoto engine (N=512, Lorentzian ω) and compares
    the steady-state R with the Ott-Antonsen analytical prediction.
    The agreement should improve with N (finite-size corrections ~ 1/√N).
    """
    from core.kuramoto.config import KuramotoConfig
    from core.kuramoto.engine import KuramotoEngine

    delta = 0.5  # Lorentzian half-width
    K = 2.5  # K/K_c = 2.5 (well supercritical)
    N = 512
    # tolerance: finite-size correction ~ 1/√N ≈ 0.044
    finite_size_tolerance = 3.0 / math.sqrt(N)  # epsilon: INV-K2 style

    # Ott-Antonsen prediction
    R_oa = math.sqrt(1.0 - 2.0 * delta / K)

    # N-body with Lorentzian frequencies: ω ~ Cauchy(0, Δ)
    rng = np.random.default_rng(seed=42)
    omega = rng.standard_cauchy(N) * delta  # Lorentzian
    theta0 = rng.uniform(-math.pi, math.pi, N)

    cfg = KuramotoConfig(
        N=N,
        K=K,
        omega=omega,
        theta0=theta0,
        dt=0.01,
        steps=3000,
        seed=42,
    )
    result = KuramotoEngine(cfg).run()
    R_nbody = float(np.mean(result.order_parameter[-500:]))

    error = abs(R_nbody - R_oa)
    assert error < finite_size_tolerance, (
        f"INV-OA2 cross-validation: |R_nbody - R_OA| = {error:.4f} > "
        f"tolerance={finite_size_tolerance:.4f}. "
        f"Expected N-body R to match Ott-Antonsen within 3/√N. "
        f"Observed at N={N}, K={K}, delta={delta}, R_OA={R_oa:.4f}, "
        f"R_nbody={R_nbody:.4f}. "
        f"Physical reasoning: Ott-Antonsen is exact at N→∞; finite-size "
        f"corrections are O(1/√N)."
    )


def test_chimera_detection_identifies_partial_sync() -> None:
    """INV-K1 + chimera: detect partial synchronization across sectors.

    Creates a 3-sector system where 2 sectors are phase-locked and 1
    is uniformly distributed. The chimera detector must identify the
    split correctly.
    """
    rng = np.random.default_rng(seed=7)
    # Sector 0: tech — tightly clustered near π/4
    tech_phases = rng.normal(math.pi / 4, 0.05, 15)
    # Sector 1: energy — uniformly distributed (desynchronized)
    energy_phases = rng.uniform(-math.pi, math.pi, 15)
    # Sector 2: finance — tightly clustered near -π/3
    finance_phases = rng.normal(-math.pi / 3, 0.05, 15)

    phases = np.concatenate([tech_phases, energy_phases, finance_phases])
    sectors = np.array([0] * 15 + [1] * 15 + [2] * 15)
    labels = ["Tech", "Energy", "Finance"]

    report = detect_chimera(phases, sectors, labels)

    assert report.is_chimera, (
        f"Chimera not detected: sector_R={list(zip(labels, report.sector_R))}. "
        f"Expected Tech+Finance sync, Energy desync. "
        f"Observed at N=45 (3×15), seed=7. "
        f"Physical reasoning: two clustered + one uniform = chimera by definition."
    )
    assert "Tech" in report.sync_sectors, (
        f"INV-K1 chimera: Tech not in sync sectors. "
        f"sector_R(Tech)={report.sector_R[0]:.3f}. "
        f"Expected Tech R > 0.7 (tightly clustered phases). "
        f"Observed at N=15, seed=7."
    )
    assert "Energy" in report.desync_sectors, (
        f"INV-K1 chimera: Energy not in desync sectors. "
        f"sector_R(Energy)={report.sector_R[1]:.3f}. "
        f"Expected Energy R < 0.3 (uniform phases). "
        f"Observed at N=15, seed=7."
    )
    # epsilon: chimera index should be substantial (> 0.3) for clear chimera
    assert report.chimera_index > 0.3, (
        f"Chimera index too low: {report.chimera_index:.3f}. "
        f"Expected > 0.3 for a clear partial-sync configuration. "
        f"Observed at N=45, seed=7. "
        f"Physical reasoning: std(sector_R)/mean(sector_R) measures "
        f"the disparity between sync and desync groups."
    )
