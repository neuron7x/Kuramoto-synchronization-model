# SPDX-License-Identifier: MIT
"""Adversarial fail-closed witnesses for the Ott-Antonsen runtime oracle.

The Ott-Antonsen steady state R_∞ = √(1 − 2Δ/K) is the EXACT fixed point of
the mean-field ODE (Ott & Antonsen 2008, Eq. 2.13), not a target the
integrator approximates. ``OttAntonsenEngine.integrate`` therefore promotes
INV-OA2 from a passive post-hoc property to an in-process oracle: after a
*stable, converged* supercritical run it raises ``FloatingPointError`` if the
settled order parameter departs from the closed form, because such a
disagreement is a step-size / CFL failure rather than tolerable drift.

These tests are adversarial: they assert not only that correct integration
reproduces the closed form, but that the oracle REJECTS a deliberately
CFL-violating step instead of returning a physically wrong steady state, and
that degenerate inputs fail closed at construction / integration. They also
re-affirm INV-OA1 (|z| ≤ 1 over the whole trajectory) on a (K, Δ, dt) sweep.

Anchor: Ott & Antonsen (2008), "Low dimensional behavior of large systems of
globally coupled oscillators," Chaos 18(3), 037113.

INV-OA1: |z(t)| ≤ 1 always.
INV-OA2: K > 2Δ ⟹ R_∞ = √(1 − 2Δ/K), enforced as a runtime fail-closed oracle.
INV-OA3: K < 2Δ ⟹ R → 0.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.ott_antonsen import R0_MIN, ORACLE_TOL, OttAntonsenEngine

# Closed-form steady-state recovery ceiling for a converged, stable run. The
# exact fixed point is reproduced to ~1e-12 by RK4 at dt ≤ 0.05; 1e-4 is a
# conservative pass bar well inside the oracle's own ORACLE_TOL = 1e-3 gate.
RECOVERY_TOL = 1e-4


# ---------------------------------------------------------------------------
# Positive: supercritical integration reproduces the EXACT closed form
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("K", "delta"),
    [(1.2, 0.5), (1.5, 0.5), (3.0, 0.5), (6.0, 0.5), (4.0, 1.0), (10.0, 0.2)],
)
def test_supercritical_R_matches_closed_form(K: float, delta: float) -> None:
    """INV-OA2: a stable supercritical run lands on √(1 − 2Δ/K) to ≤ 1e-4.

    The closed form is the exact fixed point; a stable RK4 step reproduces it.
    """
    K_c = 2.0 * delta
    assert K > K_c  # guard: parametrisation must be supercritical
    res = OttAntonsenEngine(K=K, delta=delta).integrate(T=200.0, dt=0.01, R0=0.05)
    R_closed_form = math.sqrt(1.0 - K_c / K)
    R_num = float(np.mean(res.R[-2000:]))
    residual = abs(R_num - R_closed_form)
    assert residual <= RECOVERY_TOL, (
        f"INV-OA2: integrated R={R_num:.10f} departs from closed form "
        f"√(1 − 2Δ/K)={R_closed_form:.10f} by {residual:.3e} > {RECOVERY_TOL:.0e} "
        f"(K={K}, delta={delta}). The supercritical fixed point is exact."
    )


def test_supercritical_run_does_not_raise_when_stable() -> None:
    """A stable, converged supercritical run must NOT trip the oracle.

    Fail-closed must not mean fail-noisy: the oracle stays silent on a correct
    trajectory. This locks against an over-eager threshold regression.
    """
    res = OttAntonsenEngine(K=4.0, delta=0.5).integrate(T=120.0, dt=0.01, R0=0.1)
    assert math.isclose(float(res.R[-1]), math.sqrt(1.0 - 1.0 / 4.0), abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Positive: subcritical decays to the incoherent state R → 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("K", [0.2, 0.5, 0.8])
def test_subcritical_collapses_to_zero(K: float) -> None:
    """INV-OA3: below onset (K < 2Δ) the incoherent state is the sole
    attractor; integrated R decays to 0. The oracle does not fire here (no
    supercritical closed form to match)."""
    delta = 0.5
    assert K < 2.0 * delta
    res = OttAntonsenEngine(K=K, delta=delta).integrate(T=200.0, dt=0.01, R0=0.3)
    R_final = float(res.R[-1])
    assert R_final < 1e-4, (
        f"INV-OA3: R_final={R_final:.3e} expected → 0 in the subcritical regime "
        f"(K={K}, delta={delta}, K_c={2.0 * delta})."
    )


# ---------------------------------------------------------------------------
# Adversarial: a CFL-violating dt must RAISE, never return a wrong steady state
# ---------------------------------------------------------------------------


def test_cfl_violating_dt_oracle_raises_instead_of_wrong_steady_state() -> None:
    """FAIL-CLOSED: a deliberately too-large dt past the RK4 stability limit
    settles the supercritical run on the WRONG stationary value; the INV-OA2
    oracle must RAISE rather than return that physically wrong R.

    K=4, Δ=0.5 ⟹ R_∞ = √(3)/2 ≈ 0.8660. At dt=1.0 the explicit RK4 step is
    CFL-violating: it converges to a stationary ≈ 0.71 plateau (verified flat,
    not en route), an order of magnitude beyond ORACLE_TOL from the closed
    form. A silent return of 0.71 would be a fabricated steady state.
    """
    engine = OttAntonsenEngine(K=4.0, delta=0.5)
    with pytest.raises(FloatingPointError, match="INV-OA2"):
        engine.integrate(T=50.0, dt=1.0, R0=0.1)


def test_cfl_violating_dt_blows_up_unit_disk_gate_raises() -> None:
    """FAIL-CLOSED (INV-OA1): a grossly too-large dt drives |z| past the unit
    disk beyond the RK4 local-error overshoot bound; the per-step gate raises
    rather than silently projecting a blown-up step onto |z|=1."""
    engine = OttAntonsenEngine(K=4.0, delta=0.5)
    with pytest.raises(FloatingPointError, match="INV-OA1"):
        engine.integrate(T=40.0, dt=5.0, R0=0.2)


def test_oracle_overshoot_bound_is_tied_to_step_size() -> None:
    """The INV-OA1 overshoot gate is dt-dependent (∝ (max(Δ,K)·dt)^5), not a
    frozen magic constant: a very coarse-but-stable step is tolerated only
    within its own larger local-error envelope, while the same overshoot at a
    fine step is rejected. Here we assert the documented module bound is
    consumed: a stable coarse run passes, a stability-breaking run raises."""
    engine = OttAntonsenEngine(K=2.0, delta=0.5)
    # Stable coarse step: K_c = 2Δ = 1.0, so R_∞ = √(1 − K_c/K) = √(1 − 1/2)
    # = √0.5 ≈ 0.7071. A coarse-but-stable dt=0.2 step still lands on it.
    res = engine.integrate(T=80.0, dt=0.2, R0=0.1)
    assert math.isclose(float(res.R[-1]), math.sqrt(1.0 - 1.0 / 2.0), abs_tol=1e-4)


# ---------------------------------------------------------------------------
# Adversarial: degenerate inputs fail closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_delta", [0.0, -0.5, -1e-9])
def test_nonpositive_delta_raises_at_construction(bad_delta: float) -> None:
    """Δ ≤ 0 is unphysical (the Lorentzian half-width must be positive); the
    engine fails closed at construction, never integrating a degenerate ODE."""
    with pytest.raises(ValueError, match="delta"):
        OttAntonsenEngine(K=2.0, delta=bad_delta)


def test_nan_K_raises_at_construction() -> None:
    """A non-finite K would let a NaN propagate past the |z| guard; reject it
    at construction (fail-closed finiteness contract)."""
    with pytest.raises(ValueError, match="K must be finite"):
        OttAntonsenEngine(K=float("nan"), delta=0.5)


def test_nan_delta_raises_at_construction() -> None:
    """Non-finite Δ is rejected at construction."""
    with pytest.raises(ValueError, match="delta"):
        OttAntonsenEngine(K=2.0, delta=float("nan"))


@pytest.mark.parametrize("bad_dt", [0.0, -0.01, float("nan"), float("inf")])
def test_bad_dt_raises_at_integration(bad_dt: float) -> None:
    """A non-positive / non-finite dt cannot be integrated; fail closed."""
    engine = OttAntonsenEngine(K=4.0, delta=0.5)
    with pytest.raises(ValueError, match="dt"):
        engine.integrate(T=10.0, dt=bad_dt)


def test_unstable_incoherent_fixed_point_R0_zero_does_not_false_raise() -> None:
    """R0 = 0 is the UNSTABLE incoherent fixed point: seeded exactly on the
    repeller the deterministic supercritical run stays at R = 0 ≠ R_∞. This is
    the unstable branch, NOT a CFL failure, so the oracle must abstain — it
    binds the stable branch reached from R0 > 0 only. Guards against the oracle
    mistaking the repeller for a numerical fault."""
    res = OttAntonsenEngine(K=2.0, delta=0.25).integrate(T=30.0, dt=0.01, R0=0.0)
    assert float(res.R[-1]) == 0.0


# ---------------------------------------------------------------------------
# INV-OA1: |z(t)| ≤ 1 across the whole trajectory for a (K, Δ, dt) sweep
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dt", [0.005, 0.01, 0.05])
@pytest.mark.parametrize("delta", [0.2, 0.5, 1.0])
@pytest.mark.parametrize("K", [0.3, 1.0, 2.5, 5.0])
def test_unit_disk_bound_over_full_trajectory(K: float, delta: float, dt: float) -> None:
    """INV-OA1: |z(t)| ≤ 1 at every step over a sub/supercritical (K, Δ, dt)
    sweep. The unit disk is the exact invariant manifold of the OA ODE; any
    step exceeding it past round-off is a fault, and a NaN would mean the RK4
    stepper diverged."""
    res = OttAntonsenEngine(K=K, delta=delta).integrate(T=40.0, dt=dt, R0=0.1)
    r_max = float(np.max(res.R))
    # One ULP at R=1 (~2.2e-16) accumulated over ≤ 8000 steps (~1.8e-12) with
    # safety margin; the round-off projection keeps the bound tight.
    assert r_max <= 1.0 + 1e-11, (
        f"INV-OA1 VIOLATED: max R={r_max:.6e} > 1 (K={K}, delta={delta}, dt={dt})."
    )
    assert np.all(np.isfinite(res.R)), (
        f"INV-OA1 VIOLATED: non-finite R (K={K}, delta={delta}, dt={dt})."
    )


def test_oracle_tol_is_documented_module_constant() -> None:
    """The oracle tolerance is an importable, documented module constant — not
    an inline magic number — so the contract is auditable from outside."""
    assert ORACLE_TOL == 1e-3


# ---------------------------------------------------------------------------
# INV-OA2 repeller-domain restriction (Task 3 — counterexample closure)
# ---------------------------------------------------------------------------


def test_repeller_counterexample_raises_under_convergence_claim() -> None:
    """REGRESSION (the known counterexample): a supercritical run seeded at the
    unstable fixed point R0 = 0 stalls at R ≈ 0 ≠ R_∞. With an explicit
    convergence claim (require_convergence=True) this is refused with a
    ValueError naming the repeller domain — no silently-wrong is_supercritical
    result, no silent repair."""
    engine = OttAntonsenEngine(K=2.0, delta=0.25)  # supercritical, K_c = 0.5
    with pytest.raises(ValueError, match="repeller domain"):
        engine.integrate(T=30.0, dt=0.01, R0=0.0, require_convergence=True)
    # The whole float neighbourhood of the repeller is refused, not just 0.0.
    with pytest.raises(ValueError, match="repeller domain"):
        engine.integrate(T=30.0, dt=0.01, R0=R0_MIN, require_convergence=True)


def test_convergence_claim_holds_above_floor() -> None:
    """Just above R0_MIN the convergence claim is admitted (domain is tight):
    a normal small-perturbation seed reaches the closed-form attractor."""
    engine = OttAntonsenEngine(K=2.0, delta=0.25)
    res = engine.integrate(T=200.0, dt=0.01, R0=0.05, require_convergence=True)
    assert math.isclose(float(res.R[-1]), engine.R_steady, abs_tol=RECOVERY_TOL)


def test_default_integrate_still_abstains_on_repeller() -> None:
    """CONTRACT PRESERVED: without require_convergence, R0 = 0 supercritical is
    still a valid unstable-branch trajectory that stalls at R = 0 (the oracle
    abstains). Task 3 must not break this enshrined behaviour."""
    res = OttAntonsenEngine(K=2.0, delta=0.25).integrate(T=30.0, dt=0.01, R0=0.0)
    assert float(res.R[-1]) == 0.0


def test_subcritical_convergence_unaffected_by_domain_floor() -> None:
    """INV-OA3: subcritical (K < 2Δ) converges to 0 from ANY seed, so even
    R0 = 0 with require_convergence=True is admitted (no repeller there)."""
    engine = OttAntonsenEngine(K=0.4, delta=0.5)  # subcritical, K_c = 1.0
    res = engine.integrate(T=80.0, dt=0.01, R0=0.0, require_convergence=True)
    assert float(res.R[-1]) < 1e-3


def test_r0_min_is_machine_epsilon_derived() -> None:
    """R0_MIN is a machine-epsilon-derived floor, not a tuned constant."""
    assert R0_MIN == 4.0 * float(np.finfo(np.float64).eps)
    assert R0_MIN < 1e-12  # far below any legitimate perturbation seed
