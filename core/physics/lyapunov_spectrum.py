# SPDX-License-Identifier: MIT
"""Full Lyapunov spectrum via Benettin-Galgani-Strelcyn QR method.

LAW T2 — Whole-spectrum Lyapunov estimator for autonomous ODEs

GeoSync Physics Law T2 (constitutional, INV-LY1..LY3). Companion to the
scalar Rosenstein MLE in ``lyapunov_exponent.py``: that estimator works
on observed time-series; this estimator integrates the variational
(tangent) flow and returns every exponent up to ``n_exp``.

Algorithm (Benettin et al. 1980, "Lyapunov characteristic exponents
for smooth dynamical systems and for Hamiltonian systems"):

1.  Augment state ``x ∈ R^n`` with an orthonormal tangent frame
    ``Q ∈ R^{n × n_exp}``, ``Q^T Q = I``.
2.  Co-integrate the augmented system ``ẋ = f(x)``, ``Q̇ = J(x)·Q``
    where ``J = ∂f/∂x`` (forward-mode via ``jax.jacfwd``).
3.  Every ``qr_every`` steps, perform a QR decomposition
    ``Q ← Q``, ``R ← R`` and accumulate ``log|diag(R)|``.
4.  Spectrum: ``λ_k = (1/T) · Σ log|R_kk|``.

The integrator is the explicit midpoint rule (Heun-RK2): bit-identical
under ``jit`` for the same ``(x0, dt, n_steps)``, second-order accurate,
and cheap enough for ``vmap`` over hundreds of seeds. RK4 was rejected
for v1 — it would quadruple ``jacfwd`` invocations per step while the
dominant error is the finite QR frequency, not the integrator order.

Invariants (CLAUDE.md INVARIANT REGISTRY):

* INV-LY1 | algebraic    | linear ``ẋ = A x``: ``sort(spectrum) ==
                          sort(real(eigvals(A)))`` to 1e-6.
* INV-LY2 | conservation | Hamiltonian flow: ``Σ λ_k = 0`` (symplectic
                          pairing). Tested on harmonic oscillator.
* INV-LY3 | universal    | for INV-LE1 (existing): finite, bounded
                          input ⟹ finite spectrum.
* INV-LY4 | universal    | QR conditioning is fail-closed: if at ANY
                          reorthonormalisation step the frame loses
                          orthonormality (``max|QᵀQ − I| > _ORTHO_TOL``)
                          or a direction collapses below float64 relative
                          resolution (``min|R_kk| / max|R_kk| ≤ eps_f64``),
                          the run raises ``FloatingPointError`` instead of
                          flooring ``|R_kk|`` with ``1e-30`` and returning a
                          ≈ −69-bit garbage exponent. Orthonormal Q is the
                          Benettin (1980) precondition.

Determinism: bit-identical output for identical ``(rhs, x0, dt,
n_steps, qr_every, n_exp)`` on same hardware/JAX version (INV-HPC1).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Final, NamedTuple

import jax
import jax.numpy as jnp
import numpy as np
from jax import Array

# INV-LY1/LY2 require float64 (1e-3 / 1e-6 precision; Σλ=0 to 1e-3). Enable x64
# at import so the estimator's precision does NOT depend on whether an unrelated
# module (e.g. lyapunov_calibration) happened to enable it first. Idempotent.
# (Called via an Any-typed alias: jax.config.update is untyped, and a bare call
# would trip mypy --strict no-untyped-call without adding a debt suppression.)
_jax_config: Any = jax.config
_jax_config.update("jax_enable_x64", True)

# Public API ------------------------------------------------------------------

__all__ = [
    "LyapunovReport",
    "lyapunov_spectrum",
]

# Numerical tolerance below which |R_kk| is treated as a zero singular
# value (collapsed direction). Slightly above float32 eps to stay
# robust under float32 fallback. Linked to INV-LY3.
#
# It exists ONLY as a last-resort clamp inside ``jnp.log`` to keep the
# traced kernel from emitting ``-inf`` (which would poison ``vmap`` /
# ``jit`` reductions). It is NOT an admissibility decision: a direction
# whose ``|R_kk|`` actually reaches this floor has lost all orthonormality
# meaning and the run is rejected fail-closed by the conditioning guard
# below (INV-LY4) BEFORE the floored value is ever returned to a caller.
_LOG_FLOOR: float = 1e-30

# --- INV-LY4: QR-conditioning fail-closed guard ------------------------------
# Math anchor: Benettin–Galgani–Strelcyn (1980). The continuous-Gram-Schmidt
# (Benettin QR) estimator is only valid while the tangent frame Q stays
# ORTHONORMAL — that orthonormality is the algorithm's precondition, not an
# incidental detail. Two independent failure modes break it, and a silent
# ``maximum(|R_kk|, 1e-30)`` floor hides both, returning a ~log(1e-30)/T ≈
# −69-bit garbage exponent dressed as a physical Lyapunov number:
#
#   1. Rank loss  — directions in Q collapse onto one another, so the smallest
#      ``|R_kk|`` underflows toward zero relative to the largest. Once
#      ``min|R_kk| / max|R_kk| ≤ eps_float64`` the small direction is below the
#      RELATIVE resolution of float64: QR cannot distinguish it from an exact
#      zero, so ``log|R_kk|`` is pure rounding noise. The threshold is TIED to
#      ``numpy.finfo(float64).eps`` (≈ 2.22e-16) — not a tunable knob.
#
#   2. Orthonormality loss — Householder QR returns a numerically orthonormal Q
#      even at rank loss, but an upstream non-finite Jacobian or a ``dt`` so
#      large the variational step blows up can still produce a Q whose Gram
#      matrix departs from the identity. We bound ``max|QᵀQ − I|`` by
#      ``_ORTHO_TOL``, set to ≈ 1e6 · eps_float64 (generous headroom over the
#      O(n·eps) residual a healthy reduced QR leaves) so well-conditioned
#      systems are never touched.
#
# When EITHER bound is breached the run RAISES ``FloatingPointError`` tagged
# INV-LY4 instead of flooring with 1e-30. Well-conditioned systems (every
# INV-LY1 / INV-LY2 case) keep bit-identical behaviour: the guard metrics are
# computed inside the traced loop, carried out, and asserted in eager Python —
# they never alter the accumulated log on the admissible path.
_FLOAT64_EPS: Final[float] = float(np.finfo(np.float64).eps)
# Smallest admissible ``min|R_kk| / max|R_kk|``. Below this the smallest
# stretched direction is unresolvable in float64 ⇒ log is garbage.
_RDIAG_REL_FLOOR: Final[float] = _FLOAT64_EPS
# Largest admissible ``max|QᵀQ − I|`` after reorthonormalisation. ≈ 1e6·eps.
_ORTHO_TOL: Final[float] = 1.0e-10


class LyapunovReport(NamedTuple):
    """Outcome of a single ``lyapunov_spectrum`` run.

    Attributes
    ----------
    spectrum:
        Length-``n_exp`` array sorted descending. ``spectrum[0]`` is
        the maximal Lyapunov exponent (compatible with the scalar
        ``maximal_lyapunov_exponent`` for the same trajectory).
    log_growth:
        Cumulative ``Σ log|R_kk|`` per direction, BEFORE division by
        ``T``. Useful for convergence diagnostics — its derivative
        with respect to ``T`` should stabilise.
    final_state:
        State ``x`` at the end of integration. Returned so callers
        can chain runs without re-warming.
    final_frame:
        Orthonormal frame ``Q`` at the end of integration.
    integration_time:
        Total wall-clock-physics time ``T = n_steps · dt``.
    """

    spectrum: Array
    log_growth: Array
    final_state: Array
    final_frame: Array
    integration_time: float


def lyapunov_spectrum(
    rhs: Callable[[Array], Array],
    x0: Array,
    *,
    dt: float,
    n_steps: int,
    n_exp: int | None = None,
    qr_every: int = 1,
) -> LyapunovReport:
    """Estimate the Lyapunov spectrum of an autonomous ODE ``ẋ = rhs(x)``.

    Parameters
    ----------
    rhs:
        Right-hand side. Must be a JAX-traceable function ``Array
        (shape (n,)) -> Array (shape (n,))``. Will be differentiated
        via ``jax.jacfwd`` once per midpoint substep.
    x0:
        Initial condition, shape ``(n,)``. ``dtype`` propagates to all
        outputs; pass ``float64`` for production-grade precision. This module
        enables ``jax_enable_x64`` at import, so float64 holds regardless of
        import order (INV-LY1/LY2 depend on it).
    dt:
        Integration timestep. Must satisfy ``dt > 0``.
    n_steps:
        Total number of midpoint integration steps. Total physical
        integration time is ``T = n_steps · dt``.
    n_exp:
        Number of exponents to estimate. Defaults to ``n`` (full
        spectrum). Passing ``n_exp < n`` is a valid optimisation when
        only the leading exponents are needed.
    qr_every:
        Re-orthonormalise the tangent frame every ``qr_every``
        integration steps. ``1`` is most stable; larger values save
        compute at the cost of conditioning. ``qr_every`` must
        divide ``n_steps``.

    Returns
    -------
    LyapunovReport
        See class docstring.

    Raises
    ------
    ValueError
        On any input that violates a contract: non-positive ``dt``,
        non-positive ``n_steps``, ``qr_every`` not dividing ``n_steps``,
        rank-deficient initial frame, ``x0`` not 1-D, non-finite ``x0``
        (DS-13: NaN/±Inf seed), ``n_exp > x0.size``. Fail-closed
        (INV-LE1, INV-HPC2 spirit) — no silent repair.
    FloatingPointError
        INV-LY4. If at any reorthonormalisation step the tangent frame
        loses orthonormality (``max|QᵀQ − I| > _ORTHO_TOL``) or a
        direction collapses below float64 relative resolution
        (``min|R_kk| / max|R_kk| ≤ eps_float64``). The Benettin (1980)
        QR estimator is undefined once Q stops being orthonormal, so the
        run is rejected rather than returning a 1e-30-floored garbage
        exponent.

    Notes
    -----
    The implementation is **pure functional** and JIT-friendly:
    ``rhs`` is captured by closure and the returned function compiles
    on first call with given ``(n_steps, qr_every, n_exp, dt)``. For
    parameter sweeps prefer ``vmap`` over a wrapping function rather
    than re-tracing.
    """
    # --- Contract checks (fail-closed) ---------------------------------------
    if dt <= 0.0:
        raise ValueError(f"INV-LY3: dt must be positive, got {dt}")
    if n_steps <= 0:
        raise ValueError(f"INV-LY3: n_steps must be positive, got {n_steps}")
    if qr_every <= 0:
        raise ValueError(f"INV-LY3: qr_every must be positive, got {qr_every}")
    if n_steps % qr_every != 0:
        raise ValueError(f"INV-LY3: qr_every={qr_every} must divide n_steps={n_steps}")

    x0 = jnp.asarray(x0)
    if x0.ndim != 1:
        raise ValueError(f"INV-LY3: x0 must be 1-D, got shape {x0.shape}")
    # DS-13 / INV-LY3 (fail-closed): a non-finite x0 seeds the variational flow
    # with NaN/±Inf. Only ``final_state`` visibly carries the NaN downstream —
    # the log|R_kk| accumulation and QR conditioning telemetry can still reduce
    # to a plausible FINITE spectrum, so the contract "every contract violation
    # → ValueError" was silently fail-OPEN on non-finite x0. Reject at the
    # boundary rather than emit a finite-looking spectrum from a poisoned seed.
    if not bool(jnp.isfinite(x0).all()):
        raise ValueError(f"INV-LY3: x0 must be all-finite, got non-finite entries {np.asarray(x0)}")
    n: int = int(x0.shape[0])
    n_exp_eff: int = n if n_exp is None else int(n_exp)
    if n_exp_eff <= 0 or n_exp_eff > n:
        raise ValueError(f"INV-LY3: n_exp must satisfy 1 ≤ n_exp ≤ {n}, got {n_exp_eff}")

    n_outer: int = n_steps // qr_every
    total_time: float = float(n_steps) * float(dt)

    # --- Initial orthonormal frame -------------------------------------------
    # Q0: first n_exp standard basis vectors. They are exactly orthonormal
    # so the first QR step is a no-op identity (sanity).
    Q0: Array = jnp.eye(n, n_exp_eff, dtype=x0.dtype)

    # --- Augmented midpoint integrator (no QR inside) ------------------------
    jac: Callable[[Array], Array] = jax.jacfwd(rhs)

    def _midpoint_inner(_i: Array, carry: tuple[Array, Array]) -> tuple[Array, Array]:
        """One midpoint step on (x, Q). Pure, jit-fusable."""
        x, Q = carry
        f1 = rhs(x)
        J1 = jac(x)
        x_mid = x + 0.5 * dt * f1
        Q_mid = Q + 0.5 * dt * J1 @ Q
        f2 = rhs(x_mid)
        J2 = jac(x_mid)
        x_next = x + dt * f2
        Q_next = Q + dt * J2 @ Q_mid
        return (x_next, Q_next)

    eye_exp: Array = jnp.eye(n_exp_eff, dtype=x0.dtype)

    def _outer_step(
        _k: Array, carry: tuple[Array, Array, Array, Array, Array]
    ) -> tuple[Array, Array, Array, Array, Array]:
        """``qr_every`` midpoint steps, then QR re-orthonormalisation.

        Alongside the log accumulation the step records two INV-LY4
        conditioning metrics — the worst (largest) orthonormality
        residual ``max|QᵀQ − I|`` and the worst (smallest) R-diagonal
        ratio ``min|R_kk| / max|R_kk|`` seen across the whole loop. They
        are reductions in the carry (max / min), so they are evaluated
        eagerly AFTER the traced loop without a Python branch inside it.
        """
        x, Q, log_sum, worst_ortho, worst_rratio = carry
        x, Q = jax.lax.fori_loop(0, qr_every, _midpoint_inner, (x, Q))
        # Reduced QR; R is upper-triangular (n_exp × n_exp).
        Q, R = jnp.linalg.qr(Q)
        diag_abs = jnp.abs(jnp.diag(R))
        # INV-LY3: any direction collapsed to numerical zero accumulates
        # as a strongly negative exponent rather than -inf.
        log_sum = log_sum + jnp.log(jnp.maximum(diag_abs, _LOG_FLOOR))
        # INV-LY4 conditioning telemetry (does NOT alter log_sum).
        ortho_residual = jnp.max(jnp.abs(Q.T @ Q - eye_exp))
        max_diag = jnp.max(diag_abs)
        # Guard the ratio's denominator: max_diag == 0 ⇒ total collapse ⇒
        # ratio 0, which trips the floor below. _LOG_FLOOR (not eps) keeps
        # the division finite without masking the collapse.
        r_ratio = jnp.min(diag_abs) / jnp.maximum(max_diag, _LOG_FLOOR)
        worst_ortho = jnp.maximum(worst_ortho, ortho_residual)
        worst_rratio = jnp.minimum(worst_rratio, r_ratio)
        return (x, Q, log_sum, worst_ortho, worst_rratio)

    log_sum0: Array = jnp.zeros(n_exp_eff, dtype=x0.dtype)
    worst_ortho0: Array = jnp.asarray(0.0, dtype=x0.dtype)
    worst_rratio0: Array = jnp.asarray(jnp.inf, dtype=x0.dtype)
    x_final, Q_final, log_sum_final, worst_ortho, worst_rratio = jax.lax.fori_loop(
        0, n_outer, _outer_step, (x0, Q0, log_sum0, worst_ortho0, worst_rratio0)
    )

    # --- INV-LY4: fail-closed conditioning check (eager, post-loop) -----------
    # Computed on concrete (non-traced) device scalars so a Python ``raise`` is
    # legal. Orthonormal Q is the Benettin (1980) precondition; once it breaks
    # the accumulated log is 1e-30-floored garbage, NOT a Lyapunov exponent.
    worst_ortho_f = float(worst_ortho)
    worst_rratio_f = float(worst_rratio)
    # A non-finite residual/ratio (NaN/Inf from a blown-up Q at large dt or a
    # non-finite Jacobian) is itself an orthonormality failure: ``nan > tol`` is
    # False, so route it explicitly to the fail-closed branch.
    if not math.isfinite(worst_ortho_f) or not math.isfinite(worst_rratio_f):
        raise FloatingPointError(
            "INV-LY4 VIOLATED: non-finite QR conditioning metric "
            f"(max|QᵀQ − I| = {worst_ortho_f}, min|R_kk|/max|R_kk| = "
            f"{worst_rratio_f}). The variational flow produced a non-finite "
            "tangent frame; the spectrum is undefined. Reduce dt or check rhs "
            "for a non-finite Jacobian."
        )
    if worst_ortho_f > _ORTHO_TOL:
        raise FloatingPointError(
            "INV-LY4 VIOLATED: tangent frame lost orthonormality "
            f"(max|QᵀQ − I| = {worst_ortho_f:.3e} > _ORTHO_TOL = {_ORTHO_TOL:.3e}). "
            "The Benettin QR estimator requires an orthonormal Q; the spectrum "
            "would be 1e-30-floored garbage. Reduce dt or qr_every, or check "
            "for a non-finite Jacobian."
        )
    if worst_rratio_f <= _RDIAG_REL_FLOOR:
        raise FloatingPointError(
            "INV-LY4 VIOLATED: tangent frame rank-collapsed "
            f"(min|R_kk| / max|R_kk| = {worst_rratio_f:.3e} ≤ eps_float64 = "
            f"{_RDIAG_REL_FLOOR:.3e}). The smallest stretched direction is below "
            "float64 relative resolution; log|R_kk| is rounding noise that the "
            "1e-30 floor would dress up as a ≈ −69-bit exponent. Reduce dt or "
            "qr_every so the frame is reorthonormalised before directions merge."
        )

    spectrum_unsorted = log_sum_final / total_time
    # Sort descending so spectrum[0] is the maximal exponent (matches
    # convention used by INV-LE2 and downstream T1 phase boundary).
    order = jnp.argsort(-spectrum_unsorted)
    spectrum = spectrum_unsorted[order]
    log_growth = log_sum_final[order]

    return LyapunovReport(
        spectrum=spectrum,
        log_growth=log_growth,
        final_state=x_final,
        final_frame=Q_final,
        integration_time=total_time,
    )
