# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T3 Corollary T3.1 — supercritical λ₁-invariance.

The T3 calibrator solves the *forward-well-posed* slice ``λ_target → K*``. This
battery proves, constructively and deterministically, *why* it can only promise
a λ-residual and never a K-recovery: on the phase-locked branch (``K > K_c``) the
maximal Lyapunov exponent ``λ₁`` is **exactly invariant in K** — its value is set
by the intrinsic-frequency dispersion of the synchronised manifold, not by the
coupling scale. A whole interval of couplings therefore maps to a single ``λ₁``,
so ``λ → K`` is **non-injective by construction** (not ill-conditioned by noise).

Corollary T3.1 (a theorem derived from Laws T1+T2, not a new constitutional
invariant): for ``K > K_c`` the leading exponent ``λ₁(K·A_κ; ω)`` is constant in
K to machine precision (≤ 1e-9 across a ≥2× coupling span, while ``|ΔK| ≥ 0.3``).
Hence the ``λ→K`` inverse is a constant-to-interval map and K-recovery is ill-posed
*by physics*. The calibrator's contract is therefore on the λ-residual, never on K.

This is the mechanistic root cause of the historical fragility of the
``test_negative_control_K_search_does_not_clamp_to_K_min`` proxy: it asked the
recovered K's to differ, but the physics forbids a stable difference. Proving
the invariance turns that surprise into a guarded, falsifiable law.

Anchored on: Law T1 (`kuramoto_ricci_rhs`), Law T2 (`lyapunov_spectrum`),
Law T3 (`calibrate_coupling_to_lambda`).  Deterministic: x64, fixed seed.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
from jax import Array

from core.kuramoto.kuramoto_ricci_engine import (
    kuramoto_ricci_rhs,
    phase_transition_boundary,
)
from core.kuramoto.lyapunov_calibration import (
    CalibrationStatus,
    calibrate_coupling_to_lambda,
)
from core.physics.lyapunov_spectrum import lyapunov_spectrum

jax.config.update("jax_enable_x64", True)  # type: ignore[no-untyped-call]

# Deterministic experiment design (shared with the T3 battery).
_N = 4
_GAMMA = 0.5
_SEED = 15
_DT = 0.02
_N_STEPS = 3000
_QR_EVERY = 10
# Supercritical couplings spanning a >2x range; all strictly above K_c.
_SUPERCRITICAL_MULTIPLES = (3.0, 5.0, 8.0)
# Machine-precision-class equality bound for λ₁ across the plateau. The observed
# spread is ~4e-17 (2 ULP at 1e-2); 1e-9 is a robust, platform-safe ceiling.
_LAMBDA_INVARIANCE_TOL = 1e-9
_MIN_COUPLING_SPAN = 0.3


def _complete_graph(n: int) -> Array:
    return jnp.ones((n, n)) - jnp.eye(n)


def _lorentzian_omega(rng: np.random.Generator, n: int, gamma: float) -> Array:
    u = rng.uniform(-0.5 + 1e-6, 0.5 - 1e-6, size=n)
    return jnp.asarray(float(gamma) * np.tan(np.pi * u))


def _fixture() -> tuple[Array, Array, Array, float]:
    rng = np.random.default_rng(seed=_SEED)
    A = _complete_graph(_N)
    omega = _lorentzian_omega(rng, _N, _GAMMA)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=_N))
    K_c = float(phase_transition_boundary(K=0.0, lorentzian_half_width=_GAMMA, A=A).K_c)
    return A, omega, theta_0, K_c


def _lambda_1(K: float, A: Array, omega: Array, theta_0: Array) -> float:
    rhs = kuramoto_ricci_rhs(omega, K * A)
    rep = lyapunov_spectrum(rhs, theta_0, dt=_DT, n_steps=_N_STEPS, qr_every=_QR_EVERY)
    return float(rep.spectrum[0])


def test_T3_corollary_lambda1_is_K_invariant_on_synchronised_branch() -> None:
    """Corollary T3.1: λ₁ is constant in K above K_c → λ→K is non-injective.

    Constructive witness: three couplings spanning a >2x range, all supercritical,
    yield λ₁ equal to machine precision. This is the positive statement of the
    inverse's non-injectivity — the physics, not the optimiser, forbids unique K.
    """
    A, omega, theta_0, K_c = _fixture()
    couplings = [m * K_c for m in _SUPERCRITICAL_MULTIPLES]
    lambdas = [_lambda_1(K, A, omega, theta_0) for K in couplings]

    span = max(couplings) - min(couplings)
    spread = max(lambdas) - min(lambdas)
    assert span >= _MIN_COUPLING_SPAN, (
        f"Corollary T3.1 setup: coupling span {span:.4f} too small to be a witness; "
        f"K_c={K_c:.4f}, couplings={couplings}"
    )
    assert spread <= _LAMBDA_INVARIANCE_TOL, (
        f"Corollary T3.1 VIOLATED: λ₁ is NOT K-invariant on the synchronised branch. "
        f"Across |ΔK|={span:.4f} (>{_MIN_COUPLING_SPAN}), λ₁ spread={spread:.3e} "
        f"exceeds {_LAMBDA_INVARIANCE_TOL:.0e}. couplings={couplings}, "
        f"lambdas={lambdas}. If this fires, the supercritical centre-manifold "
        f"exponent has become K-dependent — re-derive Law T3 Corollary T3.1."
    )


def test_T3_corollary_inverse_is_non_injective_witness() -> None:
    """Two well-separated couplings achieve the SAME λ₁ — the literal non-injection."""
    A, omega, theta_0, K_c = _fixture()
    K_a, K_b = 3.0 * K_c, 8.0 * K_c
    lam_a = _lambda_1(K_a, A, omega, theta_0)
    lam_b = _lambda_1(K_b, A, omega, theta_0)
    assert abs(K_a - K_b) >= _MIN_COUPLING_SPAN
    assert abs(lam_a - lam_b) <= _LAMBDA_INVARIANCE_TOL, (
        f"Corollary T3.1 witness failed: K_a={K_a:.4f}→λ={lam_a:.3e}, "
        f"K_b={K_b:.4f}→λ={lam_b:.3e}; |Δλ|={abs(lam_a - lam_b):.3e}"
    )


def test_T3_corollary_lambda1_is_bit_deterministic() -> None:
    """Determinism (x64): λ₁ is bit-identical on recomputation — the invariance
    is a property of the physics, not of nondeterministic float reduction."""
    A, omega, theta_0, K_c = _fixture()
    K = 5.0 * K_c
    assert _lambda_1(K, A, omega, theta_0) == _lambda_1(K, A, omega, theta_0)


def test_T3_corollary_calibrator_honours_lambda_contract_on_plateau() -> None:
    """Given the plateau λ, the calibrator CONVERGES to *some* interior K and
    makes no K-recovery claim — exactly the T3 contract under non-injectivity."""
    A, omega, theta_0, K_c = _fixture()
    K_min, K_max = 1e-3, 10.0 * K_c
    target = _lambda_1(5.0 * K_c, A, omega, theta_0)
    cal = calibrate_coupling_to_lambda(
        target_lambda_1=target,
        omega=omega,
        A=A,
        theta_0=theta_0,
        K_min=K_min,
        K_max=K_max,
        n_steps=_N_STEPS,
    )
    assert cal.status == CalibrationStatus.CONVERGED, (
        f"plateau target {target:.3e} must be feasible (it is achieved by an "
        f"interval of K); got {cal.status.name}, residual={cal.residual:.3e}"
    )
    assert K_min < cal.K_optimal < K_max  # interior; Law T3 positivity (K*>0) implied
    assert cal.residual <= 5e-2


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
