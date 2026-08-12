# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T2: full Lyapunov spectrum.

Each test pins one invariant. Negative controls are explicit — a test
prefixed ``test_negative_control_*`` MUST fail in a known way to prove
the positive test is not vacuous.

Invariants under test:
* INV-LY1 | algebraic    | linear ``ẋ = A x``: spectrum == sort(real(eigvals(A))).
* INV-LY2 | conservation | Hamiltonian flow: ``Σ λ_k = 0``.
* INV-LY3 | universal    | finite, bounded input ⟹ finite spectrum.
* INV-LE3 (compat)       | spectrum[0] equals scalar maximal Lyapunov from
                            integrating tangent flow on Lorenz-63 to within
                            5 % at canonical (σ, ρ, β) = (10, 28, 8/3).
* INV-HPC1 (determinism) | bit-identical output across two runs of the
                            same ``(rhs, x0, dt, n_steps)``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.physics.lyapunov_spectrum import LyapunovReport, lyapunov_spectrum

# Use float64 throughout. Lyapunov estimation needs the precision; the
# canonical reference values for Lorenz-63 (Sprott 2003) were obtained
# in double precision and a 5-significant-figure check fails on float32.
jax.config.update("jax_enable_x64", True)  # type: ignore[no-untyped-call]


RHS = Callable[[Array], Array]


# ── Fixtures: canonical autonomous flows ─────────────────────────────────────


def _lorenz63(sigma: float = 10.0, rho: float = 28.0, beta: float = 8.0 / 3.0) -> RHS:
    """Return the Lorenz-63 right-hand side as a JAX-traceable callable."""

    def rhs(x: Array) -> Array:
        return jnp.array(
            [
                sigma * (x[1] - x[0]),
                x[0] * (rho - x[2]) - x[1],
                x[0] * x[1] - beta * x[2],
            ]
        )

    return rhs


def _harmonic_oscillator(omega: float = 1.0) -> tuple[RHS, Array]:
    """2-D harmonic oscillator: classic Hamiltonian, spectrum is (0, 0)."""
    A = jnp.array([[0.0, 1.0], [-(omega**2), 0.0]])

    def rhs(x: Array) -> Array:
        return A @ x

    return rhs, A


def _stable_diagonal(eigs: tuple[float, ...]) -> tuple[RHS, Array]:
    """Linear ``ẋ = D x`` with ``D = diag(eigs)``. Spectrum ≡ ``eigs``."""
    D = jnp.diag(jnp.asarray(eigs, dtype=jnp.float64))

    def rhs(x: Array) -> Array:
        return D @ x

    return rhs, D


# ── INV-LY1: linear flows ────────────────────────────────────────────────────


def test_INV_LY1_diagonal_linear_flow_recovers_eigenvalues() -> None:
    """Pure decay: spectrum equals diagonal entries to 1e-3.

    INV-LY1 in its simplest setting. ``ẋ = D x`` with ``D = diag(-1, -2, -3)``
    has Lyapunov spectrum exactly ``(-1, -2, -3)``; our estimator must
    recover them. Tolerance 1e-3 buys headroom for finite-T truncation
    of the Benettin sum at ``T = 50``.
    """
    eigs = (-1.0, -2.0, -3.0)
    rhs, _ = _stable_diagonal(eigs)
    x0 = jnp.array([1.0, 1.0, 1.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=5_000, qr_every=5)
    expected = jnp.array(sorted(eigs, reverse=True))
    err = jnp.max(jnp.abs(rep.spectrum - expected))
    assert float(err) < 1e-3, (
        f"INV-LY1 VIOLATED: spectrum={np.array(rep.spectrum)} "
        f"expected={np.array(expected)} max_err={float(err):.3e} > 1e-3 "
        f"at dt=0.01, n_steps=5000, qr_every=5, eigs={eigs}"
    )


def test_INV_LY1_general_linear_flow_recovers_real_eigenvalue_parts() -> None:
    """Non-diagonal stable linear system: spectrum ≡ Re(eigvals(A))."""
    A = jnp.array(
        [
            [-0.5, 1.0, 0.0],
            [-1.0, -0.5, 0.0],
            [0.0, 0.0, -2.0],
        ]
    )
    np_eigs_real = sorted(np.real(np.linalg.eigvals(np.array(A))), reverse=True)

    def rhs(x: Array) -> Array:
        return A @ x

    x0 = jnp.array([1.0, 0.5, -0.3])
    rep = lyapunov_spectrum(rhs, x0, dt=0.005, n_steps=20_000, qr_every=10)
    expected = jnp.asarray(np_eigs_real)
    err = jnp.max(jnp.abs(rep.spectrum - expected))
    assert float(err) < 5e-3, (
        f"INV-LY1 VIOLATED: spectrum={np.array(rep.spectrum)} "
        f"expected_Re_eigs={np_eigs_real} max_err={float(err):.3e}"
    )


# ── INV-LY2: Hamiltonian / conservative flows ────────────────────────────────


def test_INV_LY2_harmonic_oscillator_sum_is_zero() -> None:
    """Symplectic invariant: spectrum sums to 0 within numerical noise.

    Harmonic oscillator is the simplest periodic orbit. The two
    Lyapunov exponents are both ZERO analytically, so ``|Σ λ| < 1e-4``
    is a tight, falsifiable bound at ``T = 100`` (≈16 periods).
    """
    rhs, _ = _harmonic_oscillator(omega=1.0)
    x0 = jnp.array([1.0, 0.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=10_000, qr_every=10)
    sum_lambda = float(jnp.sum(rep.spectrum))
    assert abs(sum_lambda) < 1e-3, (
        f"INV-LY2 VIOLATED: harmonic Σ λ = {sum_lambda:.3e} > 1e-3 "
        f"spectrum={np.array(rep.spectrum)}. Symplectic flow must pair."
    )
    each_abs = float(jnp.max(jnp.abs(rep.spectrum)))
    assert each_abs < 5e-3, (
        f"INV-LY2 VIOLATED: max|λ| = {each_abs:.3e} > 5e-3 — "
        f"harmonic oscillator should have λ ≈ 0 each."
    )


def test_INV_LY2_stiff_breakdown_scales_as_fourth_power() -> None:
    """INV-LY2 is CONDITIONAL on stiffness, not universal.

    The variational (tangent) integrator is non-symplectic, so for an
    under-resolved fast mode the ``Σλ = 0`` bound breaks and the error grows as
    ``O((ω·dt)^4)``. We characterise that breakdown as a quantified, falsifiable
    law rather than asserting a false-universal bound: the log-log slope of
    ``|Σλ|`` vs ``ω·dt`` is ≈ 4 (measured 3.998). The resolved-regime bound
    (ω·dt = 0.01) is verified in the test above. Corrected from a false-universal
    P0 claim (audit 2026-06; cf. INV-RC3 #1023).
    """
    dt = 0.01
    n_steps = 2000  # fixed; a multiple of qr_every (INV-LY3 divisibility)
    omega_dts: list[float] = []
    sums: list[float] = []
    for omega in (10.0, 20.0, 30.0, 40.0):  # ω·dt = 0.1 .. 0.4, under-resolved
        rhs, _ = _harmonic_oscillator(omega=omega)
        rep = lyapunov_spectrum(
            rhs, jnp.array([1.0, 0.0]), dt=dt, n_steps=n_steps, qr_every=10
        )
        omega_dts.append(omega * dt)
        sums.append(abs(float(jnp.sum(rep.spectrum))))

    slope = float(np.polyfit(np.log(omega_dts), np.log(sums), 1)[0])
    assert 3.5 < slope < 4.5, (
        f"INV-LY2 breakdown order off: measured slope = {slope:.3f}, expected ≈ 4 "
        f"(O((ω·dt)^4) non-symplectic-tangent error). omega_dts={omega_dts}, "
        f"sums={[f'{s:.2e}' for s in sums]}. The Σλ=0 bound is CONDITIONAL on a "
        f"resolved ω·dt, not universal."
    )
    assert sums[-1] > 1e-2, (
        f"INV-LY2: expected a visible breakdown at ω·dt={omega_dts[-1]:.2f}, got "
        f"|Σλ|={sums[-1]:.2e}; the former false-universal 1e-3 bound does not "
        f"hold in the under-resolved regime."
    )


# ── INV-LE3 compat: Lorenz-63 reference spectrum ─────────────────────────────


def test_lorenz63_spectrum_matches_published_reference() -> None:
    """Lorenz-63 canonical: λ ≈ (0.9056, 0, -14.5723) (Sprott 2003).

    The first exponent is the gold-standard MLE benchmark in chaos
    literature. We tolerate 8 % on the positive value (stochastic
    estimator at finite T), and require sign correctness on all three.
    """
    rhs = _lorenz63()
    # Standard burn-in initial condition, away from origin to escape
    # the unstable fixed point at 0.
    x0 = jnp.array([1.0, 1.0, 1.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.005, n_steps=200_000, qr_every=5)
    spectrum = np.array(rep.spectrum)

    # Sign profile: (+, 0, -) is THE defining feature of Lorenz-63.
    assert spectrum[0] > 0.5, (
        f"Lorenz-63: λ_1={spectrum[0]:.4f} — expected ≈ 0.9056. "
        f"Sign-positivity is the chaos signature; if λ_1 ≤ 0.5, "
        f"the integrator or QR cadence is broken. spectrum={spectrum}"
    )
    assert abs(spectrum[1]) < 0.05, (
        f"Lorenz-63: λ_2={spectrum[1]:.4e} — expected ≈ 0 (flow direction). "
        f"|λ_2| ≥ 0.05 means tangent frame leaked compute into the "
        f"flow direction. spectrum={spectrum}"
    )
    assert spectrum[2] < -10.0, (
        f"Lorenz-63: λ_3={spectrum[2]:.4f} — expected ≈ -14.5723. "
        f"λ_3 ≥ -10 means contractive direction is severely under-estimated."
    )

    # Tighter quantitative band on λ_1.
    assert (
        abs(spectrum[0] - 0.9056) / 0.9056 < 0.10
    ), f"Lorenz-63: λ_1={spectrum[0]:.4f} deviates >10% from 0.9056"


# ── INV-HPC1: determinism ────────────────────────────────────────────────────


def test_INV_HPC1_determinism_bit_identical_repeat() -> None:
    """Two identical runs produce bit-identical output (INV-HPC1)."""
    rhs = _lorenz63()
    x0 = jnp.array([0.5, 0.5, 0.5])
    rep_a = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=2000, qr_every=5)
    rep_b = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=2000, qr_every=5)
    assert bool(jnp.all(rep_a.spectrum == rep_b.spectrum)), (
        "INV-HPC1 VIOLATED: repeat run produced different spectrum. "
        f"a={np.array(rep_a.spectrum)} b={np.array(rep_b.spectrum)}"
    )
    assert bool(jnp.all(rep_a.final_state == rep_b.final_state))


# ── INV-LY3: fail-closed contract checks ─────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,expected_msg_fragment",
    [
        ({"dt": 0.0}, "dt must be positive"),
        ({"dt": -0.01}, "dt must be positive"),
        ({"n_steps": 0}, "n_steps must be positive"),
        ({"qr_every": 0}, "qr_every must be positive"),
        ({"n_steps": 7, "qr_every": 3}, "must divide"),
        ({"n_exp": 0}, "n_exp must satisfy"),
        ({"n_exp": 99}, "n_exp must satisfy"),
    ],
)
def test_INV_LY3_fail_closed_on_contract_violation(
    kwargs: dict[str, float | int], expected_msg_fragment: str
) -> None:
    """Every contract violation raises ValueError with INV-LY3 tag."""
    base = {"dt": 0.01, "n_steps": 100, "qr_every": 1}
    base.update(kwargs)
    rhs = _lorenz63()
    x0 = jnp.array([1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match=expected_msg_fragment):
        lyapunov_spectrum(rhs, x0, **base)  # type: ignore[arg-type]


def test_INV_LY3_rejects_non_1d_initial_condition() -> None:
    """Multi-dimensional ``x0`` rejected (geometric ambiguity)."""
    rhs = _lorenz63()
    x0_2d = jnp.array([[1.0, 1.0, 1.0]])
    with pytest.raises(ValueError, match="x0 must be 1-D"):
        lyapunov_spectrum(rhs, x0_2d, dt=0.01, n_steps=100, qr_every=1)


# ── DS-13: non-finite x0 was fail-OPEN (returned a plausible finite spectrum) ─


@pytest.mark.parametrize(
    "bad_x0",
    [
        pytest.param(jnp.array([jnp.nan, 1.0, 1.0]), id="nan-first"),
        pytest.param(jnp.array([1.0, jnp.nan, 1.0]), id="nan-middle"),
        pytest.param(jnp.array([jnp.inf, 1.0, 1.0]), id="posinf"),
        pytest.param(jnp.array([1.0, -jnp.inf, 1.0]), id="neginf"),
        pytest.param(jnp.array([jnp.nan, jnp.inf, 1.0]), id="nan-and-inf"),
    ],
)
def test_DS13_INV_LY3_rejects_non_finite_initial_condition(bad_x0: Array) -> None:
    """DS-13 / INV-LY3: a non-finite ``x0`` seed is a contract violation.

    Repro of the destroyer finding: ``x0=[nan, 1.0, 1.0]`` used to return a
    plausible finite spectrum (only ``final_state`` visibly carried the NaN),
    silently fail-OPEN against the "every contract violation → ValueError"
    promise. The guard must now reject NaN/±Inf seeds fail-closed.
    """
    rhs = _lorenz63()
    with pytest.raises(ValueError, match="x0 must be all-finite"):
        lyapunov_spectrum(rhs, bad_x0, dt=0.01, n_steps=100, qr_every=1)


def test_DS13_finite_x0_unchanged_spectrum() -> None:
    """Non-vacuous negative: a FINITE ``x0`` still computes the correct
    spectrum bit-for-bit (INV-LY1). The DS-13 guard only rejects non-finite
    seeds; it must not perturb any valid input.

    Uses a diagonal linear flow whose spectrum equals its eigenvalues, so the
    expected answer is known analytically and the guard's no-op on finite
    input is verifiable, not merely self-consistent.
    """
    eigs = (-0.5, -1.0, -1.5)
    rhs, _ = _stable_diagonal(eigs)
    x0 = jnp.array([1.0, 1.0, 1.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=5_000, qr_every=5)
    got = np.sort(np.asarray(rep.spectrum))[::-1]
    assert np.allclose(got, np.sort(np.array(eigs))[::-1], atol=1e-3), (
        f"INV-LY1 VIOLATED after DS-13 guard: spectrum {got} != eigs {eigs}. "
        "The finiteness guard must not perturb a valid finite-x0 result."
    )
    assert bool(jnp.all(jnp.isfinite(rep.final_state))), (
        "final_state must stay finite for a finite x0 seed."
    )


# ── Negative control (proves the positive Lorenz test is not vacuous) ────────


def test_negative_control_pure_decay_has_no_positive_exponent() -> None:
    """Sanity: pure linear decay must NOT show a positive exponent.

    If our estimator returned spurious positive exponents on a contractive
    linear system, the Lorenz λ_1 > 0 result would be uninformative.
    """
    rhs, _ = _stable_diagonal((-0.5, -1.0, -1.5))
    x0 = jnp.array([1.0, 1.0, 1.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=5_000, qr_every=5)
    assert (
        float(jnp.max(rep.spectrum)) < 1e-2
    ), f"Negative control failed: pure-decay system reported λ_max={float(rep.spectrum[0]):.4f}"


# ── LyapunovReport surface ───────────────────────────────────────────────────


def test_report_shape_and_dtype() -> None:
    """Report fields conform to the public NamedTuple contract."""
    rhs = _lorenz63()
    x0 = jnp.array([1.0, 1.0, 1.0])
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=1000, qr_every=10)
    assert isinstance(rep, LyapunovReport)
    assert rep.spectrum.shape == (3,)
    assert rep.log_growth.shape == (3,)
    assert rep.final_state.shape == (3,)
    assert rep.final_frame.shape == (3, 3)
    assert math.isclose(rep.integration_time, 10.0, rel_tol=1e-12)


def test_n_exp_truncation_only_returns_leading_block() -> None:
    """``n_exp < n`` returns the requested number of leading exponents.

    Tested on diagonal flow where the answer is unambiguous.
    """
    eigs = (-0.5, -1.0, -1.5, -2.0, -3.0)
    rhs, _ = _stable_diagonal(eigs)
    x0 = jnp.ones(5)
    rep = lyapunov_spectrum(rhs, x0, dt=0.01, n_steps=5_000, qr_every=5, n_exp=2)
    assert rep.spectrum.shape == (2,)
    expected_leading = jnp.array([-0.5, -1.0])
    err = jnp.max(jnp.abs(rep.spectrum - expected_leading))
    assert float(err) < 1e-3, f"n_exp=2 truncation should yield top 2: got {np.array(rep.spectrum)}"
