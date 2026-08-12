# SPDX-License-Identifier: MIT
"""LAW T3 — Coupling calibration to a target maximal Lyapunov exponent.

Constitutional Law T3 of seven (CLAUDE.md GeoSync Physics Law Act).

Identity
--------
Given a Kuramoto-Ricci network ``(ω, A_κ)`` from Law T1 and the maximal
Lyapunov estimator ``λ_1(·)`` from Law T2, find the scalar coupling
``K* > 0`` such that

    K*  =  argmin_{K > 0}  |λ_1(K · A_κ; ω)  −  λ_target|².

The single-scalar form is principled: ``K`` is the unique tunable
quantity in the Kuramoto-Ricci kernel that monotonically shifts the
spectral profile while preserving the network topology and the
intrinsic-frequency distribution. Calibrating *all* of (K, ω, κ)
simultaneously is **not** a well-posed inverse problem (multiple
``θ`` produce identical λ_1) and is rejected here on first principles.

Constitutional invariants (P0)
------------------------------
* INV-CAL1 | algebraic    | feasible target ⇒ ``|λ_1(K*) − λ_target| ≤
                            calibration_tolerance``. Default 5e-2.
* INV-CAL2 | conditional  | infeasible target ⇒ ``CalibrationStatus.
                            INFEASIBLE``; never silent best-effort.
* INV-CAL3 | universal    | ``K* > 0`` always; the optimiser searches in
                            a strictly positive interval enforced as a
                            hard bound, not a soft penalty.

Determinism: bit-identical ``K*`` for identical inputs (INV-HPC1) on
the same JAX/SciPy versions and hardware.

References
----------
* Pyragas, K. (1992). *Continuous control of chaos by self-controlling
  feedback.* Physics Letters A 170, 421–428.
* Brent, R. P. (1973). *Algorithms for Minimization Without Derivatives.*
  Prentice-Hall — bounded scalar optimiser used internally by SciPy.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

import jax
import jax.numpy as jnp
from jax import Array
from scipy.optimize import minimize_scalar

from core.kuramoto.kuramoto_ricci_engine import kuramoto_ricci_rhs
from core.physics.lyapunov_spectrum import lyapunov_spectrum

__all__ = [
    "CalibrationReport",
    "CalibrationStatus",
    "calibrate_coupling_to_lambda",
]


class CalibrationStatus(str, Enum):
    """Outcome class for a calibration run."""

    CONVERGED = "CONVERGED"
    INFEASIBLE = "INFEASIBLE"


class CalibrationReport(NamedTuple):
    """Outcome of one ``calibrate_coupling_to_lambda`` invocation.

    Attributes
    ----------
    status:
        ``CONVERGED`` if ``|λ_1(K*) − λ_target| ≤ tolerance``,
        ``INFEASIBLE`` otherwise. Never silent best-effort.
    K_optimal:
        Best ``K`` found within ``(K_min, K_max)``. Always strictly
        positive (INV-CAL3).
    lambda_achieved:
        ``λ_1(K_optimal)`` evaluated by Law T2.
    residual:
        ``|lambda_achieved − λ_target|``.
    n_evaluations:
        Number of ``lyapunov_spectrum`` calls SciPy made before
        terminating. Use as a budget proxy.
    """

    status: CalibrationStatus
    K_optimal: float
    lambda_achieved: float
    residual: float
    n_evaluations: int


def _evaluate_lambda_max(
    K: float,
    *,
    omega: Array,
    A: Array,
    theta_0: Array,
    dt: float,
    n_steps: int,
    qr_every: int,
) -> float:
    """λ_1 of the Kuramoto-Ricci RHS at coupling ``K``.

    Pure: depends only on (K, ω, A, θ_0, dt, n_steps, qr_every) — no
    closure over hidden state. JAX caches the JIT trace; subsequent
    evaluations at different ``K`` reuse it.
    """
    rhs = kuramoto_ricci_rhs(omega, K * A)
    rep = lyapunov_spectrum(rhs, theta_0, dt=dt, n_steps=n_steps, qr_every=qr_every)
    return float(rep.spectrum[0])


def calibrate_coupling_to_lambda(
    target_lambda_1: float,
    *,
    omega: Array,
    A: Array,
    theta_0: Array,
    K_min: float = 1e-3,
    K_max: float = 1e2,
    dt: float = 0.02,
    n_steps: int = 4_000,
    qr_every: int = 10,
    tolerance: float = 5e-2,
    max_iter: int = 50,
) -> CalibrationReport:
    """Find ``K* > 0`` so that ``λ_1(K* · A; ω) ≈ target_lambda_1``.

    Wraps SciPy's bounded Brent minimiser on the JAX-traced
    ``λ_1(K)`` from Law T2. Gradient-free by design — the spectrum is
    continuous but Lipschitz-discontinuous at regime boundaries, and
    backpropagating through a 4 000-step ``fori_loop`` of Jacobians
    is wasteful when the search is one-dimensional.

    Parameters
    ----------
    target_lambda_1:
        Requested ``λ_1``. Any finite real value.
    omega:
        Intrinsic frequencies, shape ``(N,)``.
    A:
        Symmetric, non-negative-entry adjacency, shape ``(N, N)``.
        Use ``ricci_to_adjacency`` if starting from signed κ.
    theta_0:
        Initial phase, shape ``(N,)``. The estimator burns in
        implicitly via ``n_steps``; for tight tolerance use a
        moderately large ``n_steps`` (default 4 000).
    K_min, K_max:
        Hard search bounds. Both must be strictly positive. INV-CAL3
        is enforced by ``K_min > 0``.
    dt, n_steps, qr_every:
        Forwarded to ``lyapunov_spectrum``. The defaults are tuned for
        N ∈ [4, 32] networks and converge to ≈3 % accuracy in ≈80 ms
        per call on 1 CPU core after JIT warm-up.
    tolerance:
        Maximum acceptable ``|λ_1(K*) − target_lambda_1|`` for status
        ``CONVERGED``. Larger residual ⇒ ``INFEASIBLE``.
    max_iter:
        SciPy iteration cap. The Brent algorithm converges in ~10–30
        iterations on smooth 1-D objectives.

    Returns
    -------
    CalibrationReport

    Raises
    ------
    ValueError
        On any contract violation. Fail-closed (INV-CAL3, INV-LY3).
    """
    if not jnp.isfinite(target_lambda_1):
        raise ValueError(f"INV-CAL3: target_lambda_1 must be finite, got {target_lambda_1}")
    if K_min <= 0.0:
        raise ValueError(f"INV-CAL3: K_min must be > 0 (positivity), got {K_min}")
    if K_max <= K_min:
        raise ValueError(f"INV-CAL3: K_max ({K_max}) must exceed K_min ({K_min})")
    if tolerance <= 0.0:
        raise ValueError(f"INV-CAL1: tolerance must be > 0, got {tolerance}")
    if max_iter <= 0:
        raise ValueError(f"INV-CAL3: max_iter must be > 0, got {max_iter}")
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-KR3: A must be square 2-D, got shape {A.shape}")
    if not bool(jnp.all(A >= 0.0)):
        raise ValueError("INV-KR3: A must have non-negative entries.")
    if omega.ndim != 1 or omega.shape[0] != A.shape[0]:
        raise ValueError(f"INV-CAL3: omega shape {omega.shape} mismatch with A shape {A.shape}")
    if theta_0.ndim != 1 or theta_0.shape[0] != A.shape[0]:
        raise ValueError(f"INV-CAL3: theta_0 shape {theta_0.shape} mismatch with A shape {A.shape}")

    n_evals: list[int] = [0]

    def objective(K: float) -> float:
        n_evals[0] += 1
        lam = _evaluate_lambda_max(
            float(K),
            omega=omega,
            A=A,
            theta_0=theta_0,
            dt=dt,
            n_steps=n_steps,
            qr_every=qr_every,
        )
        return float((lam - target_lambda_1) ** 2)

    result = minimize_scalar(
        objective,
        bounds=(float(K_min), float(K_max)),
        method="bounded",
        options={"xatol": 1e-3, "maxiter": int(max_iter)},
    )

    K_star = float(result.x)
    lambda_achieved = _evaluate_lambda_max(
        K_star,
        omega=omega,
        A=A,
        theta_0=theta_0,
        dt=dt,
        n_steps=n_steps,
        qr_every=qr_every,
    )
    residual = abs(lambda_achieved - target_lambda_1)
    status = CalibrationStatus.CONVERGED if residual <= tolerance else CalibrationStatus.INFEASIBLE
    return CalibrationReport(
        status=status,
        K_optimal=K_star,
        lambda_achieved=lambda_achieved,
        residual=residual,
        n_evaluations=n_evals[0],
    )


# Make sure JAX uses x64 here too — Lyapunov estimation needs it.
jax.config.update("jax_enable_x64", True)  # type: ignore[no-untyped-call]
