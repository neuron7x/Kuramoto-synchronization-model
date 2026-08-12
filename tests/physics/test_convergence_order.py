# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# NUMERICAL CONVERGENCE-ORDER witnesses for the executable falsification layer.
# =============================================================================
# These tests do NOT assert "the answer is close enough". They prove that the
# REAL solvers converge at their THEORETICAL order by measuring the empirical
# order of convergence: refine a parameter, fit the log-log slope of the error,
# and assert the slope lands in a calibrated band around the analytic order.
#
# Two laws are witnessed (see physics_contracts/falsification_catalog.yaml):
#
#   convergence_order_ott_antonsen_rk4
#       OttAntonsenEngine.integrate is an RK4 integrator of the OA ODE.
#       Richardson on dt (halve dt, error ratio -> 2^4 = 16) gives global
#       order p ~ 4. CALIBRATED slopes (this machine): RK4 = 4.02, and the
#       Euler negative control on the SAME real RHS = 1.00.
#
#   convergence_order_lyapunov_benettin
#       lyapunov_spectrum (Benettin QR on the non-symplectic midpoint tangent
#       flow) has a Sum-lambda symplectic-pairing error that obeys the EXACT
#       analytic law  Sum(lambda) = omega^4 * dt^3 / 4  for the harmonic
#       oscillator. That single law predicts TWO orders, both verified here:
#         * refine omega at fixed dt  -> slope vs (omega*dt) = 4  (INV-LY2,
#           documented "measured slope 3.998"); CALIBRATED here = 3.9986.
#         * refine dt at fixed omega  -> step-size order = 3; CALIBRATED = 3.000.
#       The damped (non-Hamiltonian) negative control has Sum(lambda) -> -2c != 0,
#       so refining dt does NOT drive |Sum| to zero (slope ~ 0) -> detected.
#
# NOTE on the AGM / Brent-Salamin pi task: a repo grep
#   grep -rniE "brent_salamin|gauss_legendre|\bagm\b" core/ --include=*.py
# returns nothing. No quadratic-convergence pi routine exists, so that task is
# deliberately SKIPPED rather than fabricated.

from __future__ import annotations

import math
from collections.abc import Callable

import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.lyapunov_spectrum import lyapunov_spectrum

# ---------------------------------------------------------------------------
# Shared refinement / slope helpers
# ---------------------------------------------------------------------------

# Theoretical orders.
_RK4_ORDER = 4.0
_EULER_ORDER = 1.0
_LY_OMEGA_ORDER = 4.0  # Sum(lambda) ~ (omega*dt)^4 at fixed dt (INV-LY2)
_LY_DT_ORDER = 3.0  # Sum(lambda) ~ dt^3 at fixed omega (step-size order)

# Calibrated acceptance bands (set from measured slopes, not guessed).
_RK4_BAND = (3.5, 4.5)
_EULER_BAND = (0.6, 1.5)
_LY_OMEGA_BAND = (3.5, 4.5)
_LY_DT_BAND = (2.6, 3.4)


def _loglog_slope(params: list[float], errors: list[float]) -> float:
    """Least-squares slope of log(error) vs log(refinement parameter)."""
    return float(np.polyfit(np.log(np.asarray(params)), np.log(np.asarray(errors)), 1)[0])


def _richardson_orders(values: list[complex]) -> list[float]:
    """Per-halving observed order log2(|d_k| / |d_{k+1}|) from a refinement ladder.

    Self-referencing Richardson estimate (no exact solution needed): the
    successive-difference ratio of a fixed-point-convergent ladder reveals the
    integrator order without an analytic reference state.
    """
    orders: list[float] = []
    for i in range(len(values) - 2):
        d1 = abs(values[i] - values[i + 1])
        d2 = abs(values[i + 1] - values[i + 2])
        if d2 > 0.0:
            orders.append(math.log2(d1 / d2))
    return orders


# ---------------------------------------------------------------------------
# Ott-Antonsen RK4 integrator: theoretical order 4
# ---------------------------------------------------------------------------

# A supercritical, rotating (omega0 != 0) OA configuration probed on its
# transient (short T) so the GLOBAL truncation error — not the exact fixed
# point — dominates and exposes the integrator order.
_OA_K = 3.0
_OA_DELTA = 0.5
_OA_OMEGA0 = 0.7
_OA_R0 = 0.3
_OA_PSI0 = 0.1
_OA_T = 2.0
_OA_DTS: tuple[float, ...] = tuple(0.02 / 2**k for k in range(6))


def _oa_rk4_final_z(dt: float) -> complex:
    """Final z(T) from the REAL OttAntonsenEngine RK4 integrator."""
    result = OttAntonsenEngine(K=_OA_K, delta=_OA_DELTA, omega0=_OA_OMEGA0).integrate(
        T=_OA_T, dt=dt, R0=_OA_R0, psi0=_OA_PSI0
    )
    return complex(result.z[-1])


def _oa_euler_final_z(dt: float) -> complex:
    """Final z(T) from a deliberately first-order Euler step on the SAME real
    OA right-hand side (engine._dz_dt). Reusing the real RHS makes this a clean
    order discriminator: only the time-stepping scheme differs from RK4."""
    engine = OttAntonsenEngine(K=_OA_K, delta=_OA_DELTA, omega0=_OA_OMEGA0)
    n_steps = int(_OA_T / dt)
    z = complex(_OA_R0 * math.cos(_OA_PSI0), _OA_R0 * math.sin(_OA_PSI0))
    for _ in range(n_steps):
        z = z + dt * engine._dz_dt(z)
    return z


def test_ott_antonsen_rk4_is_fourth_order() -> None:
    """POSITIVE witness: the real OA RK4 integrator converges at order ~4.

    Richardson on dt of OttAntonsenEngine.integrate. RK4 global error ~ O(dt^4),
    so the successive-difference log-log slope (and per-halving order) ~ 4.
    """
    values = [_oa_rk4_final_z(dt) for dt in _OA_DTS]
    diffs = [abs(values[i] - values[i + 1]) for i in range(len(values) - 1)]
    slope = _loglog_slope(list(_OA_DTS[:-1]), diffs)
    per_halving = _richardson_orders(values)
    lo, hi = _RK4_BAND
    assert lo < slope < hi, (
        f"convergence_order_ott_antonsen_rk4 VIOLATED: measured order = {slope:.3f} "
        f"outside band {_RK4_BAND}, expected ~{_RK4_ORDER:.1f} (RK4 global error O(dt^4)). "
        f"Method: Richardson log-log slope of |z(T;dt)-z(T;dt/2)| vs dt on the real "
        f"OttAntonsenEngine.integrate. "
        f"At K={_OA_K}, delta={_OA_DELTA}, omega0={_OA_OMEGA0}, T={_OA_T}, dts={_OA_DTS}, "
        f"diffs={[f'{d:.2e}' for d in diffs]}, per_halving={[f'{o:.2f}' for o in per_halving]}"
    )


def test_ott_antonsen_euler_is_not_fourth_order() -> None:
    """NEGATIVE control: a first-order Euler step on the SAME real OA RHS shows
    order ~1, NOT 4 — the discriminator detects the lower-order method."""
    values = [_oa_euler_final_z(dt) for dt in _OA_DTS]
    diffs = [abs(values[i] - values[i + 1]) for i in range(len(values) - 1)]
    slope = _loglog_slope(list(_OA_DTS[:-1]), diffs)
    rk4_lo, _ = _RK4_BAND
    eu_lo, eu_hi = _EULER_BAND
    assert slope < rk4_lo, (
        f"convergence_order_ott_antonsen_rk4 NEGATIVE-CONTROL FAILED: Euler order "
        f"= {slope:.3f} was NOT detected as below RK4 (>= {rk4_lo}). "
        f"A first-order method must not pass as fourth-order. "
        f"Method: Euler step on engine._dz_dt, Richardson slope. "
        f"At dts={_OA_DTS}, diffs={[f'{d:.2e}' for d in diffs]}"
    )
    assert eu_lo < slope < eu_hi, (
        f"convergence_order_ott_antonsen_rk4 NEGATIVE-CONTROL off-order: Euler order "
        f"= {slope:.3f} outside expected band {_EULER_BAND} (~{_EULER_ORDER:.1f}). "
        f"Euler global error is O(dt), so its measured order must sit near 1. "
        f"Method: Euler on the real OA RHS. "
        f"At K={_OA_K}, delta={_OA_DELTA}, omega0={_OA_OMEGA0}, T={_OA_T}, dts={_OA_DTS}"
    )


# ---------------------------------------------------------------------------
# Lyapunov spectrum (Benettin QR): Sum(lambda) = omega^4 * dt^3 / 4
# ---------------------------------------------------------------------------

_LY_OMEGA0 = 1.0  # base omega for the dt-refinement
_LY_N_PERIODS = 4
_LY_T = _LY_N_PERIODS * 2.0 * math.pi / _LY_OMEGA0
_LY_X0: Array = jnp.array([1.0, 0.0], dtype=jnp.float64)

# omega-refinement (fixed dt, fixed n_steps) — the INV-LY2 protocol.
_LY_FIXED_DT = 0.01
_LY_FIXED_NSTEPS = 2000
_LY_QR_EVERY = 10
_LY_OMEGAS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0)

# dt-refinement (fixed omega, fixed integration window).
_LY_DTS: tuple[float, ...] = tuple(0.02 / 2**k for k in range(4))

# Damped (non-Hamiltonian) negative control: Sum(lambda) -> trace(A) = -2c.
_LY_DAMP_C = 0.3


def _harmonic_rhs(omega: float) -> Callable[[Array], Array]:
    """Harmonic-oscillator RHS factory (avoids late-binding of the loop omega)."""

    def rhs(x: Array) -> Array:
        return jnp.array([x[1], -(omega**2) * x[0]])

    return rhs


def _damped_rhs(omega: float, c: float) -> Callable[[Array], Array]:
    """Damped-oscillator RHS factory; phase-space contracts at rate 2c."""

    def rhs(x: Array) -> Array:
        return jnp.array([x[1], -(omega**2) * x[0] - 2.0 * c * x[1]])

    return rhs


def _sum_lambda(rhs: Callable[[Array], Array], dt: float, n_steps: int, qr_every: int) -> float:
    """Sum of the Benettin spectrum from the REAL lyapunov_spectrum."""
    report = lyapunov_spectrum(rhs, _LY_X0, dt=dt, n_steps=n_steps, qr_every=qr_every)
    return float(jnp.sum(report.spectrum))


def test_lyapunov_sum_lambda_obeys_omega4_dt3_law() -> None:
    """POSITIVE witness: the Benettin Sum(lambda) error follows the exact law
    Sum(lambda) = omega^4 * dt^3 / 4, which simultaneously fixes BOTH orders.

    (a) refine omega at fixed dt  -> slope vs (omega*dt) ~ 4  (INV-LY2 O((omega*dt)^4)).
    (b) refine dt at fixed omega  -> step-size order ~ 3.
    Reuses the real lyapunov_spectrum on the harmonic (Hamiltonian) oscillator,
    whose true Sum(lambda) is exactly 0 (symplectic pairing).
    """
    # (a) omega-refinement at fixed dt/n_steps.
    omega_dts: list[float] = []
    sums_a: list[float] = []
    for omega in _LY_OMEGAS:
        s = abs(_sum_lambda(_harmonic_rhs(omega), _LY_FIXED_DT, _LY_FIXED_NSTEPS, _LY_QR_EVERY))
        omega_dts.append(omega * _LY_FIXED_DT)
        sums_a.append(s)
    slope_omega = _loglog_slope(omega_dts, sums_a)

    # (b) dt-refinement at fixed omega.
    dts: list[float] = []
    sums_b: list[float] = []
    for dt in _LY_DTS:
        n_steps = int(round(_LY_T / dt))
        s = abs(_sum_lambda(_harmonic_rhs(_LY_OMEGA0), dt, n_steps, 1))
        dts.append(dt)
        sums_b.append(s)
    slope_dt = _loglog_slope(dts, sums_b)

    # Analytic-law cross-check: measured |Sum| == omega^4 dt^3 / 4 (ratio ~ 1).
    predicted = [omega**4 * _LY_FIXED_DT**3 / 4.0 for omega in _LY_OMEGAS]

    olo, ohi = _LY_OMEGA_BAND
    assert olo < slope_omega < ohi, (
        f"convergence_order_lyapunov_benettin VIOLATED: omega-refine order "
        f"= {slope_omega:.3f} outside band {_LY_OMEGA_BAND}, expected ~{_LY_OMEGA_ORDER:.1f} "
        f"(INV-LY2 Sum(lambda) ~ O((omega*dt)^4) at fixed dt). "
        f"Method: log-log slope of |Sum(lambda)| vs omega*dt on lyapunov_spectrum. "
        f"At dt={_LY_FIXED_DT}, n_steps={_LY_FIXED_NSTEPS}, omega*dt={omega_dts}, "
        f"sums={[f'{s:.2e}' for s in sums_a]}"
    )
    dlo, dhi = _LY_DT_BAND
    assert dlo < slope_dt < dhi, (
        f"convergence_order_lyapunov_benettin VIOLATED: dt-refine order "
        f"= {slope_dt:.3f} outside band {_LY_DT_BAND}, expected ~{_LY_DT_ORDER:.1f} "
        f"(Sum(lambda) ~ dt^3 at fixed omega; global step-size order). "
        f"Method: log-log slope of |Sum(lambda)| vs dt on lyapunov_spectrum. "
        f"At omega={_LY_OMEGA0}, T={_LY_T:.3f}, dts={dts}, sums={[f'{s:.2e}' for s in sums_b]}"
    )
    np.testing.assert_allclose(
        sums_a,
        predicted,
        rtol=0.02,
        err_msg=(
            f"convergence_order_lyapunov_benettin VIOLATED: measured |Sum(lambda)| "
            f"departs from the exact law omega^4*dt^3/4 by > 2%. "
            f"Expected ratio ~ 1.0 (both orders descend from this single law). "
            f"Method: lyapunov_spectrum vs analytic prediction. "
            f"At omegas={_LY_OMEGAS}, dt={_LY_FIXED_DT}, measured={[f'{s:.3e}' for s in sums_a]}, "
            f"predicted={[f'{p:.3e}' for p in predicted]}"
        ),
    )


def test_lyapunov_damped_sum_does_not_converge_to_zero() -> None:
    """NEGATIVE control: a damped (non-Hamiltonian) oscillator has Sum(lambda) ->
    trace(A) = -2c != 0, so refining dt does NOT drive |Sum(lambda)| toward 0.

    The order machinery (which presumes convergence to the symplectic Sum=0)
    must register NO convergence: the dt-slope of |Sum(lambda) - 0| collapses to
    ~0 and stays far from the order-3 step-size band — the broken premise is
    detected rather than passing as a clean rate."""
    dts: list[float] = []
    sums: list[float] = []
    for dt in _LY_DTS:
        n_steps = int(round(_LY_T / dt))
        s = abs(_sum_lambda(_damped_rhs(_LY_OMEGA0, _LY_DAMP_C), dt, n_steps, 1))
        dts.append(dt)
        sums.append(s)
    slope = _loglog_slope(dts, sums)

    expected_trace = 2.0 * _LY_DAMP_C  # |trace(A)| = 2c
    dlo, _ = _LY_DT_BAND
    assert slope < dlo, (
        f"convergence_order_lyapunov_benettin NEGATIVE-CONTROL FAILED: damped "
        f"Sum(lambda) showed a spurious convergence order = {slope:.3f} (>= {dlo}). "
        f"A non-Hamiltonian system has Sum(lambda) -> -2c != 0, so |Sum| must NOT "
        f"shrink with dt. Method: dt-refine slope on damped lyapunov_spectrum. "
        f"At omega={_LY_OMEGA0}, c={_LY_DAMP_C}, dts={dts}, sums={[f'{s:.2e}' for s in sums]}"
    )
    # |Sum(lambda)| is pinned at the physical contraction rate, not zero.
    assert abs(sums[-1] - expected_trace) < 1e-3, (
        f"convergence_order_lyapunov_benettin NEGATIVE-CONTROL off-target: damped "
        f"|Sum(lambda)| = {sums[-1]:.5f} did not settle at |trace(A)| = 2c = "
        f"{expected_trace:.5f} (tol 1e-3). The control must pin the non-zero "
        f"contraction rate to prove the Sum=0 premise is genuinely broken. "
        f"At omega={_LY_OMEGA0}, c={_LY_DAMP_C}, finest dt={_LY_DTS[-1]}"
    )


if __name__ == "__main__":  # pragma: no cover - manual calibration entry point
    raise SystemExit(pytest.main([__file__, "-v"]))
