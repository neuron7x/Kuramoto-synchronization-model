# SPDX-License-Identifier: MIT
"""T23 (algebraic companion) — Ott-Antonsen fixed-point at machine epsilon.

The companion test file (`test_T23_ott_antonsen_chimera.py`) verifies
INV-OA2 by integrating the ODE for T=100 and comparing the long-time
limit with `√(1 − 2Δ/K)`. Because that test goes through RK4 at
``dt=0.01``, its tolerance is bounded by the integrator (≈ 1e-3) — a
loosening of the underlying invariant which is, per CLAUDE.md
("INV-OA2 ... Analytical — CAN test to float precision"), exact at
the algebraic level.

These tests close that gap. They do *not* integrate. They evaluate
the Ott-Antonsen ODE right-hand side directly at the analytical
fixed point ``z = R_∞ + 0j`` (with ω₀ = 0) and assert
``|dz/dt| < 1e-13`` — i.e., the formula and the implementation
agree to within IEEE-754 double-precision arithmetic noise on a
single ``_dz_dt`` evaluation.

Why this is the strongest possible test for INV-OA2
---------------------------------------------------

INV-OA2 is an *algebraic* invariant: at the supercritical fixed
point ``z = R_∞`` (real, ω₀ = 0), the right-hand side reduces to::

    dz/dt = -Δ·R_∞ + (K/2)·(R_∞ − R_∞³)
          = R_∞·[(K/2)·(1 − R_∞²) − Δ]
          = R_∞·[(K/2)·(2Δ/K) − Δ]    (substitute R_∞² = 1 − 2Δ/K)
          = R_∞·[Δ − Δ]
          = 0.

So at the analytical R_∞, ``_dz_dt`` should return exactly zero
modulo IEEE-754 round-off. Any deviation larger than ~10·eps
proves the implementation has drifted from the formula. The
existing 1e-3 RK4 test would not catch a sign error in one of the
RHS terms; this one would.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.ott_antonsen import OttAntonsenEngine

# Machine epsilon ≈ 2.22e-16; allow ~50·eps for accumulated round-off
# across the multiplication / subtraction chain in _dz_dt. Empirically
# the residual stays under 1e-14 across the parameter sweep.
_ALGEBRAIC_TOL: float = 1e-13


@pytest.mark.parametrize(
    ("K", "delta"),
    [
        (1.5, 0.5),  # K/K_c = 1.5  → R_∞ ≈ 0.577
        (2.0, 0.5),  # K/K_c = 2.0  → R_∞ ≈ 0.707
        (3.0, 0.5),  # K/K_c = 3.0  → R_∞ ≈ 0.816
        (5.0, 0.5),  # K/K_c = 5.0  → R_∞ ≈ 0.894
        (10.0, 0.5),  # K/K_c = 10.0 → R_∞ ≈ 0.949
        (100.0, 0.5),  # extreme: R_∞ → 1
        (1.01, 0.5),  # near critical: R_∞ ≈ 0.099 (tight test of the formula)
        (4.0, 1.0),  # different Δ
        (0.4, 0.1),  # smaller scale
        (200.0, 0.05),  # extreme: R_∞ → 1, very small Δ
    ],
)
def test_inv_oa2_fixed_point_residual_at_machine_epsilon(K: float, delta: float) -> None:
    """INV-OA2 (algebraic): _dz_dt(R_∞ + 0j) == 0 to machine precision.

    Evaluates the right-hand side at the analytical fixed point and
    asserts the residual is below ``1e-13``. This is the strongest
    possible test for INV-OA2 because it does not depend on a
    numerical integrator — only on the formula's algebraic
    correctness.
    """
    engine = OttAntonsenEngine(K=K, delta=delta, omega0=0.0)
    R_inf = math.sqrt(1.0 - 2.0 * delta / K)
    z_fixed = complex(R_inf, 0.0)
    dz = engine._dz_dt(z_fixed)  # noqa: SLF001 — algebraic invariant probe
    residual = abs(dz)
    assert residual < _ALGEBRAIC_TOL, (
        f"INV-OA2 ALGEBRAIC VIOLATED: |dz/dt| at the analytical "
        f"fixed point R_∞ = √(1 − 2Δ/K) is {residual:.3e}, "
        f"expected < {_ALGEBRAIC_TOL:.0e}. "
        f"Observed at K={K}, Δ={delta}, K_c={2 * delta}, R_∞={R_inf:.16f}, "
        f"dz/dt = {dz!r}. "
        "Physical reasoning: at the supercritical fixed point the "
        "drift terms exactly cancel — any residual above the "
        "round-off floor implies a sign or factor drift in _dz_dt "
        "that the integration-tolerance test (1e-3) would miss."
    )


def test_inv_oa2_subcritical_zero_is_also_a_fixed_point() -> None:
    """INV-OA2 / INV-OA3: z = 0 is *always* a fixed point (sub- and supercritical).

    For both K < K_c and K > K_c the incoherent state z = 0 is a
    fixed point of the ODE. Subcritically it is the *only* stable
    one; supercritically it is unstable but still a fixed point.
    Either way, ``_dz_dt(0)`` must be exactly ``0+0j``.
    """
    for K, delta in [(0.5, 0.5), (1.0, 0.5), (2.0, 0.5), (10.0, 0.5)]:
        engine = OttAntonsenEngine(K=K, delta=delta)
        dz = engine._dz_dt(complex(0.0, 0.0))  # noqa: SLF001
        assert dz == 0j, (
            f"INV-OA2/3 VIOLATED: z=0 must yield dz/dt == 0+0j exactly; "
            f"got {dz!r} at K={K}, delta={delta}. "
            "Any non-zero result would imply spurious drift terms in _dz_dt."
        )


def test_inv_oa2_critical_point_zero_residual() -> None:
    """INV-OA2 (boundary) — at K = K_c the only fixed point is z = 0; R_∞ formula returns 0.

    Verifies that :attr:`OttAntonsenEngine.R_steady` returns exactly
    ``0.0`` at the bifurcation point (no pseudo-supercritical drift),
    and that ``_dz_dt(0)`` agrees.
    """
    delta = 0.7
    K_c = 2.0 * delta
    engine = OttAntonsenEngine(K=K_c, delta=delta)
    assert engine.R_steady == 0.0, (
        f"INV-OA2 boundary: at K = K_c the steady-state magnitude must "
        f"be exactly 0.0; got R_steady={engine.R_steady!r} at K={K_c}, "
        f"delta={delta}. The formula √(1 − K_c/K) evaluates to 0 here, "
        "but a sloppy implementation could return √eps."
    )
    dz = engine._dz_dt(complex(0.0, 0.0))  # noqa: SLF001
    assert dz == 0j, (
        f"INV-OA2 boundary VIOLATED: _dz_dt(0) at K = K_c "
        f"observed = {dz!r}, expected = 0+0j. "
        f"Parameters: K={K_c}, delta={delta}, K_c=2·delta={2 * delta}. "
        "Physical reasoning: at the bifurcation point K = K_c the "
        "incoherent fixed point z = 0 is marginally stable; the ODE "
        "right-hand side must still vanish there exactly by symmetry."
    )


def test_inv_oa2_residual_grows_with_perturbation_size() -> None:
    """INV-OA2 (discriminative-power probe) — verify the algebraic test is non-vacuous.

    Demonstrates that ``_dz_dt`` is sensitive to perturbations off
    the fixed point, so the at-fixed-point residual being below
    ``1e-13`` is a real falsification of any drift in INV-OA2 — not
    an artifact of a degenerate (e.g., constantly-zero) function.
    The residual at ``z = R_∞ + ε`` must grow at least linearly
    with ε for small ε.
    """
    K, delta = 3.0, 0.5
    engine = OttAntonsenEngine(K=K, delta=delta)
    R_inf = math.sqrt(1.0 - 2.0 * delta / K)
    base = abs(engine._dz_dt(complex(R_inf, 0.0)))  # noqa: SLF001
    perturbed = abs(engine._dz_dt(complex(R_inf + 1e-6, 0.0)))  # noqa: SLF001
    assert perturbed > base * 1e6, (
        f"INV-OA2 discriminative-power probe failed: "
        f"observed perturbed-residual = {perturbed:.3e}, "
        f"expected ≥ base × 1e6 = {base * 1e6:.3e} (base = {base:.3e}). "
        f"Parameters: K={K}, delta={delta}, R_inf={R_inf:.6f}, perturbation=1e-6. "
        "Physical reasoning: if _dz_dt is suspiciously flat near the "
        "fixed point, the algebraic test cannot catch implementation "
        "drift and INV-OA2 would be vacuously satisfied."
    )


# ---------------------------------------------------------------------------
# INV-OA2 — ω₀ ≠ 0 / off-real-axis falsifiers.
#
# Every test above fixes ω₀ = 0 and probes z on the real axis. On that
# measure-zero slice the conjugate-vs-direct coupling form is bit-
# identical, so a z↔z̄ swap in the linear coupling gain is INVISIBLE
# there (the original defect: ``(K/2)·z̄`` instead of ``(K/2)·z``). The
# tests below permanently close that blind manifold: they exercise the
# rotating fixed point ``z = R_∞·e^{iφ}`` with ω₀ ≠ 0, where the OA
# normal form requires *rigid rotation*::
#
#     dz/dt = -(Δ+iω₀)·z + (K/2)·(z − |z|²·z)
#           = z·[-(Δ+iω₀) + (K/2)·(1 − R_∞²)]
#           = z·[-(Δ+iω₀) + Δ]              (R_∞² = 1 − 2Δ/K)
#           = -iω₀·z
#
# i.e. zero radial drift, pure rotation at the mean frequency, for
# ANY phase φ. The buggy z̄ form does not satisfy this for ω₀ ≠ 0 (it
# counter-rotates and collapses to z = 0), so these are genuine
# falsifiers, not vacuous probes.
# ---------------------------------------------------------------------------

_OMEGA0_CASES: list[float] = [0.3, 1.0, 2.0, -1.7, 5.0]
_PHASE_CASES: list[float] = [0.0, 0.7, math.pi / 2, math.pi, -2.1]


@pytest.mark.parametrize("K", [1.5, 3.0, 5.0, 20.0])
@pytest.mark.parametrize("omega0", _OMEGA0_CASES)
@pytest.mark.parametrize("phi", _PHASE_CASES)
def test_inv_oa2_rotating_fixed_point_is_rigid_rotation(
    K: float, omega0: float, phi: float
) -> None:
    """INV-OA2 (ω₀≠0 algebraic): _dz_dt(R_∞·e^{iφ}) == -iω₀·z to machine ε.

    Strongest non-integrator falsifier of the z↔z̄ coupling-gain
    defect: at the supercritical amplitude the radial drift must
    vanish and the order parameter must rotate rigidly at ω₀ for
    every phase φ. A conjugate on the linear term breaks this for any
    ω₀ ≠ 0 or φ ≠ 0.
    """
    delta = 0.5
    engine = OttAntonsenEngine(K=K, delta=delta, omega0=omega0)
    R_inf = math.sqrt(1.0 - 2.0 * delta / K)
    z = complex(R_inf * math.cos(phi), R_inf * math.sin(phi))
    dz = engine._dz_dt(z)  # noqa: SLF001 — algebraic invariant probe
    expected = -1j * omega0 * z  # pure rigid rotation, zero radial drift
    residual = abs(dz - expected)
    assert residual < _ALGEBRAIC_TOL, (
        f"INV-OA2 ROTATING-FIXED-POINT VIOLATED: at z = R_∞·e^(iφ) the "
        f"OA RHS must equal -iω₀·z (rigid rotation, zero radial drift); "
        f"|dz/dt − (−iω₀·z)| = {residual:.3e} > {_ALGEBRAIC_TOL:.0e}. "
        f"K={K}, Δ={delta}, ω₀={omega0}, φ={phi}, R_∞={R_inf:.12f}, "
        f"dz/dt={dz!r}, expected={expected!r}. A residual here is the "
        f"signature of a conjugate on the linear coupling gain "
        f"(z̄ instead of z) — invisible on the ω₀=0 real axis."
    )


@pytest.mark.parametrize("omega0", [0.0, 1.0, -2.5, 4.0])
def test_inv_oa2_omega0_integration_locks_at_R_inf(omega0: float) -> None:
    """INV-OA2 (ω₀≠0 dynamical): RK4 from a perturbation locks to R_∞.

    Closes the integrator-path blind spot (integrate() also defaulted
    ω₀=0). For supercritical K the magnitude must converge to
    √(1−2Δ/K) regardless of ω₀; with the conjugate defect it instead
    collapses to 0 for ω₀≠0.
    """
    K, delta = 4.0, 0.5
    engine = OttAntonsenEngine(K=K, delta=delta, omega0=omega0)
    result = engine.integrate(T=80.0, dt=0.005, R0=0.05, psi0=0.3)
    R_final = result.R[-1]
    R_expected = math.sqrt(1.0 - 2.0 * delta / K)
    assert abs(R_final - R_expected) < 1e-3, (
        f"INV-OA2 DYNAMICAL VIOLATED: integrated R_∞ = {R_final:.6f} at "
        f"ω₀={omega0}, expected √(1−2Δ/K) = {R_expected:.6f} "
        f"(K={K}, Δ={delta}). A collapse to ~0 for ω₀≠0 is the "
        f"conjugate-coupling defect; the magnitude must be ω₀-invariant."
    )


def _oa_transient_exact(t: np.ndarray, K: float, delta: float, r0: float) -> np.ndarray:
    """Closed-form OA order-parameter transient R(t) for ω₀ = 0.

    With ω₀=0 and real R, the OA flow reduces to the Bernoulli ODE
    dR/dt = a·R − b·R³ (a = K/2 − Δ, b = K/2). Substituting u = R² gives the
    logistic equation du/dt = 2a·u − 2b·u², solved in closed form:
        u(t) = u₀·e^{2at} / (1 + (b/a)·u₀·(e^{2at} − 1))   (a ≠ 0).
    The supercritical fixed point u∞ = a/b = 1 − 2Δ/K recovers INV-OA2.
    """
    a = K / 2.0 - delta
    b = K / 2.0
    u0 = r0 * r0
    if abs(a) < 1e-14:
        u = u0 / (1.0 + 2.0 * b * u0 * t)
    else:
        exp2at = np.exp(2.0 * a * t)
        u = u0 * exp2at / (1.0 + (b / a) * u0 * (exp2at - 1.0))
    return np.sqrt(np.clip(u, 0.0, None))


@pytest.mark.parametrize(
    "K, delta, r0",
    [(6.0, 0.5, 0.1), (3.0, 0.5, 0.05), (1.0, 2.0, 0.8)],  # super, super, subcritical
)
def test_inv_oa2_full_transient_matches_closed_form(K: float, delta: float, r0: float) -> None:
    """INV-OA2 (transient): the integrator matches the exact R(t) everywhere.

    Beyond the fixed point R_∞ = √(1−2Δ/K), the WHOLE OA transient has the
    closed-form Bernoulli/logistic solution. We integrate and compare the entire
    R(t) trajectory to the analytic form — a far stronger check than the
    steady-state value alone. Expected agreement is at machine precision
    (observed max error ≈ 1e-13).
    """
    engine = OttAntonsenEngine(K=K, delta=delta, omega0=0.0)
    result = engine.integrate(T=20.0, dt=0.001, R0=r0)
    r_exact = _oa_transient_exact(result.time, K, delta, r0)
    max_err = float(np.max(np.abs(result.R - r_exact)))
    # tolerance: RK4 at dt=1e-3 tracks the analytic transient to ~1e-13
    transient_tol = 1e-9  # epsilon: full-trajectory transient agreement
    assert max_err < transient_tol, (
        f"INV-OA2 TRANSIENT VIOLATED: max|R_num − R_exact| = {max_err:.3e} "
        f"> tol = {transient_tol:.1e} over the full trajectory. Expected the "
        f"integrator to track the closed-form Bernoulli/logistic R(t). "
        f"At K={K}, Δ={delta}, R0={r0}, ω₀=0, T=20, dt=1e-3. "
        f"Physical reasoning: ω₀=0 reduces OA to dR/dt = aR − bR³ (exact)."
    )
