# SPDX-License-Identifier: MIT
"""LAW T1 — Sync-onset boundary on Ollivier-Ricci-weighted Kuramoto networks.

Constitutional Law T1 of seven (CLAUDE.md GeoSync Physics Law Act).

Identity
--------
For a network of phase oscillators on a connected graph ``G = (V, E)``
with edge weights ``κ_ij ∈ [-1, 1]`` interpreted as Ollivier-Ricci
curvatures (or any other physical edge-affinity bounded in that range),
the dynamics

    θ̇_i = ω_i + K · Σ_j A_ij · sin(θ_j − θ_i),    A_ij = max(κ_ij, 0),

undergoes a synchronisation transition at the ANCHORED Restrepo-Ott-Hunt
threshold

    Φ(K, γ, A_κ)  ≜  K · λ_max(A_κ) − 2 γ ,         (Φ = 0 boundary)

where γ is the half-width of the (Lorentzian) intrinsic-frequency
distribution. ``Φ < 0`` ⇒ incoherent state ``R(t→∞) → O(1/√N)``;
``Φ > 0`` ⇒ stable synchronised state ``R(t→∞) > 0``.

This module ships:

1. ``kuramoto_ricci_rhs(omega, A)``   — JAX RHS factory (jit-friendly).
2. ``kuramoto_ricci_step(state, …)``  — single midpoint step on (θ).
3. ``phase_transition_boundary(…)``   — analytic Φ value.
4. ``ricci_to_positive_adjacency``    — A_κ = max(κ, 0), zero diag + audit (FP-2).
5. ``ricci_to_signed_coupling``       — full signed descriptor, sign preserved (FP-2).
6. ``ricci_to_adjacency(kappa)``      — back-compat alias of the positive path.
7. ``order_parameter(theta)``         — R(t) = |⟨e^{iθ}⟩|.
8. ``coupling_potential(theta, A)``   — V(θ) = Σ A_ij (1 − cos(θ_i−θ_j))/2.

FP-2 "No silent physics loss" (issue #1096, Lane B)
---------------------------------------------------
The Ollivier-Ricci κ-matrix carries SIGNED information: ``κ_ij < 0`` means
anti-correlated random walks (an anti-synchronising / repulsive edge). The
Restrepo-Ott-Hunt onset boundary Φ = K·λ_max(A_κ) − 2γ is derived for
NON-NEGATIVE weights, so feeding signed κ through it is a category error. Two
NAMED paths make the loss-or-preservation of sign explicit and auditable:

* ``ricci_to_positive_adjacency`` — the threshold/onset-safe path. It clips
  negative curvature to zero ONLY here, and only with explicit
  :class:`RicciAdjacencyAudit` metadata recording how many edges and how much
  curvature mass were discarded. ROH-compatible; NOT signed-dynamics-compatible.
* ``ricci_to_signed_coupling`` — the full signed-descriptor path. It preserves
  every negative value. NOT ROH-compatible: it carries no onset-threshold claim
  and must never be passed to ``phase_transition_boundary``.

INV-KR4 (P0) makes this fail-closed: a signed matrix sent to the ROH boundary
is rejected, and the positive path can only discard negative curvature while
emitting metadata that says so (``clipped_for_threshold=True``). A test fails if
signed curvature is silently dropped while claiming full physical dynamics.

Constitutional invariants (P0)
------------------------------
* INV-KR1 | algebraic    | sign(Φ) ⇒ asymptotic ⟨R⟩: Φ < 0 ⇒ ⟨R⟩ ≤ 3/√N
                         | with ε margin; Φ > 0 ⇒ ⟨R⟩ > 0.5 with margin.
                         | Tested on ER and Lorentzian-frequency ensembles.
* INV-KR2 | qualitative  | the boundary λ_1(variational flow) crosses
                         | zero through Φ = 0 (verified via T2 spectrum).
* INV-KR3 | conservation | with ω_i = 0 (homogeneous limit), the coupling
                         | potential V(θ(t)) is non-increasing (gradient
                         | flow on Riemannian metric induced by A_κ).

Anchors (literature)
--------------------
* Restrepo, Ott, Hunt (2005). *Onset of synchronization in large
  networks of coupled oscillators.* Phys. Rev. E **71**, 036151.
  Provides the Φ formula and λ_max(A) threshold.
* Strogatz (2000). *From Kuramoto to Crawford …* Physica D 143, 1–20.
  Threshold for Lorentzian ensemble: K_c = 2γ.
* Ollivier (2009). *Ricci curvature of Markov chains on metric spaces.*
  J. Funct. Anal. 256, 810–864. Defines κ on weighted graphs.
* Lin, Lu, Yau (2011). *Ricci curvature of graphs.*
  Tohoku Math. J. 63, 605–627. Discrete-graph specialisation.

Determinism: bit-identical for identical ``(omega, A, dt, n_steps,
theta_0)`` (INV-HPC1).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import jax
import jax.numpy as jnp
from jax import Array

__all__ = [
    "BoundaryReport",
    "RicciAdjacencyAudit",
    "assert_roh_compatible",
    "coupling_potential",
    "kuramoto_ricci_rhs",
    "kuramoto_ricci_step",
    "kuramoto_ricci_trajectory",
    "order_parameter",
    "phase_transition_boundary",
    "ricci_to_adjacency",
    "ricci_to_positive_adjacency",
    "ricci_to_signed_coupling",
]


class BoundaryReport(NamedTuple):
    """Outcome of a single ``phase_transition_boundary`` evaluation.

    Attributes
    ----------
    phi:
        The signed boundary scalar ``Φ = K · λ_max(A) − 2γ``. Zero is
        the predicted onset; positive is synchronised, negative is
        incoherent.
    K_c:
        Critical coupling at which ``Φ = 0`` for the supplied ``γ``
        and ``A``: ``K_c = 2γ / λ_max(A)``. ``inf`` if ``λ_max(A) = 0``.
    lambda_max_A:
        Spectral radius of the (positive-part) adjacency. Always ≥ 0.
    lorentzian_half_width:
        The ``γ`` that was passed in, echoed for audit traceability.
    """

    phi: float
    K_c: float
    lambda_max_A: float
    lorentzian_half_width: float


class RicciAdjacencyAudit(NamedTuple):
    """Audit trail for a κ → adjacency / coupling transform (FP-2, INV-KR4).

    Emitted by both named Ricci paths so that any loss of signed curvature
    is observable rather than silent. ``clipped_for_threshold`` is the
    load-bearing honesty bit: it is ``True`` iff a negative curvature was
    discarded, and it is ``False`` for the signed path (which preserves sign).

    Attributes
    ----------
    negative_edges_count:
        Number of off-diagonal entries in the symmetrised κ with value
        ``< 0`` (counts each undirected edge twice — the symmetric matrix
        has both ``(i, j)`` and ``(j, i)``).
    negative_mass:
        Total absolute curvature mass that was negative on the symmetrised
        off-diagonal, ``Σ |min(κ_sym, 0)|`` over off-diagonal entries. This
        is exactly the signed information the positive path discards.
    clipped_for_threshold:
        ``True`` iff at least one negative edge was clipped to zero for the
        threshold/onset-safe (ROH) path. ``False`` for the signed path.
    roh_compatible:
        ``True`` iff the returned matrix is safe to pass to the Restrepo-
        Ott-Hunt boundary ``phase_transition_boundary`` (non-negative).
    signed_dynamics_compatible:
        ``True`` iff the returned matrix preserves signed (repulsive)
        curvature for full signed dynamics. Mutually exclusive with
        ``roh_compatible`` whenever any negative curvature was present.
    """

    negative_edges_count: int
    negative_mass: float
    clipped_for_threshold: bool
    roh_compatible: bool
    signed_dynamics_compatible: bool


# Adjacency / spectral radius -----------------------------------------------


def _symmetrise_zero_diag(kappa: Array) -> Array:
    """Return ``½(κ + κᵀ)`` with the diagonal forced to zero (no self-coupling)."""
    if kappa.ndim != 2:
        raise ValueError(f"INV-KR4: kappa must be 2-D, got shape {kappa.shape}")
    n: int = int(kappa.shape[0])
    if int(kappa.shape[1]) != n:
        raise ValueError(f"INV-KR4: kappa must be square, got shape {kappa.shape}")
    sym = 0.5 * (kappa + kappa.T)
    return sym - jnp.diag(jnp.diag(sym))


def _negative_audit_fields(sym_off_diag: Array) -> tuple[int, float]:
    """Count negative off-diagonal edges and their absolute curvature mass.

    This is a pure AUDIT measurement, not a value clamp: it does not repair or
    saturate any entry. ``negative_mass`` is the absolute sum over the strictly
    negative entries (``Σ |κ| where κ < 0``), computed via a boolean mask so the
    discarded signed information is MEASURED rather than silently truncated.
    """
    negative_mask = sym_off_diag < 0.0
    negative_edges = int(jnp.sum(negative_mask))
    # Sum |κ| only where κ < 0 (mask × |κ|); no jnp.minimum/clip — nothing is
    # repaired, the magnitude of the negative part is reported for the audit.
    negative_mass = float(jnp.sum(jnp.where(negative_mask, jnp.abs(sym_off_diag), 0.0)))
    return negative_edges, negative_mass


def ricci_to_positive_adjacency(
    kappa: Array, *, audit: bool = True
) -> tuple[Array, RicciAdjacencyAudit]:
    """Threshold/onset-safe κ → adjacency: clip negatives, EMIT audit (FP-2).

    This is the **named threshold-only path** (issue #1096 Lane B / INV-KR4).
    Negative curvature is the ONLY thing it discards, and it discards it ONLY
    here, ALWAYS with explicit :class:`RicciAdjacencyAudit` metadata recording
    how many edges and how much curvature mass were clipped. By Ollivier's
    construction ``κ_ij < 0`` is an anti-synchronising edge; the Restrepo-Ott-
    Hunt boundary Φ is derived for non-negative weights, so this path produces
    the ROH-compatible adjacency ``A_κ = max(κ_sym, 0)`` and the audit declares
    ``roh_compatible=True``, ``signed_dynamics_compatible=False``.

    INV-KR3 is preserved: ``A_ij ≥ 0`` ⇒ ``V`` is a valid Lyapunov function.

    Parameters
    ----------
    kappa:
        Square ``(N, N)`` matrix of edge curvatures. Off-diagonal entries in
        ``[-1, 1]`` (Ollivier; INV-RC1 upper bound κ ≤ 1 universal).
    audit:
        Retained for call-site readability/symmetry with the signed path; the
        audit is always computed (it is free) and always returned, because the
        contract (INV-KR4) forbids a SILENT clip. Passing ``audit=False`` does
        NOT suppress the metadata — it merely documents that the caller does
        not intend to inspect it.

    Returns
    -------
    tuple[Array, RicciAdjacencyAudit]
        The non-negative, symmetric, zero-diagonal adjacency and its audit.
    """
    sym = _symmetrise_zero_diag(kappa)
    negative_edges, negative_mass = _negative_audit_fields(sym)
    # INV-KR4: negative curvature may be clipped ONLY on this named threshold
    # path, and ONLY with the audit below making the loss observable.
    pos = jnp.maximum(sym, 0.0)
    audit_report = RicciAdjacencyAudit(
        negative_edges_count=negative_edges,
        negative_mass=negative_mass,
        clipped_for_threshold=negative_edges > 0,
        roh_compatible=True,
        signed_dynamics_compatible=False,
    )
    _ = audit  # documented no-op: the audit is never suppressed (INV-KR4).
    return pos, audit_report


def ricci_to_signed_coupling(
    kappa: Array, *, symmetrize: bool = True
) -> tuple[Array, RicciAdjacencyAudit]:
    """Full signed κ → coupling: PRESERVE sign, NO ROH threshold claim (FP-2).

    This is the **signed-descriptor path** (issue #1096 Lane B / INV-KR4). It
    keeps every negative curvature (anti-synchronising / repulsive edges) and
    therefore carries the full signed interaction descriptor. It makes NO
    synchronisation-onset claim: the Restrepo-Ott-Hunt boundary Φ is undefined
    for signed weights, so the returned matrix is ``roh_compatible=False`` and
    must never be passed to :func:`phase_transition_boundary` (that path is
    fail-closed via :func:`assert_roh_compatible` and the boundary's own
    non-negativity guard).

    Parameters
    ----------
    kappa:
        Square ``(N, N)`` matrix of edge curvatures.
    symmetrize:
        When ``True`` (default) the coupling is symmetrised to ``½(κ + κᵀ)``
        (undirected coupling graph). When ``False`` the off-diagonal is kept
        as supplied (diagonal still zeroed); use only for genuinely directed
        descriptors.

    Returns
    -------
    tuple[Array, RicciAdjacencyAudit]
        The sign-preserving, zero-diagonal coupling and its audit
        (``clipped_for_threshold=False``, ``signed_dynamics_compatible=True``).
    """
    if symmetrize:
        coupling = _symmetrise_zero_diag(kappa)
    else:
        if kappa.ndim != 2:
            raise ValueError(f"INV-KR4: kappa must be 2-D, got shape {kappa.shape}")
        if int(kappa.shape[1]) != int(kappa.shape[0]):
            raise ValueError(f"INV-KR4: kappa must be square, got shape {kappa.shape}")
        coupling = kappa - jnp.diag(jnp.diag(kappa))
    negative_edges, negative_mass = _negative_audit_fields(coupling)
    audit_report = RicciAdjacencyAudit(
        negative_edges_count=negative_edges,
        negative_mass=negative_mass,
        clipped_for_threshold=False,
        roh_compatible=False,
        signed_dynamics_compatible=True,
    )
    return coupling, audit_report


def assert_roh_compatible(A: Array) -> None:
    """Fail closed if ``A`` is not safe for the Restrepo-Ott-Hunt boundary (INV-KR4).

    A signed coupling (any ``A_ij < 0``) cannot be passed to the ROH onset
    boundary: Φ = K·λ_max(A) − 2γ is derived for non-negative weights, and a
    negative entry is an anti-synchronising edge with no onset-threshold
    semantics. This guard makes the misuse explicit and fail-closed rather than
    silently returning a meaningless Φ.
    """
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-KR4: A must be square 2-D, got shape {A.shape}")
    if not bool(jnp.all(A >= 0.0)):
        raise ValueError(
            "INV-KR4: a SIGNED Ricci coupling matrix (κ_ij < 0 present) cannot be used "
            "on the Restrepo-Ott-Hunt sync-onset boundary — Φ = K·λ_max(A) − 2γ is "
            "defined only for non-negative weights. Use ricci_to_positive_adjacency() "
            "for the threshold path (with audit metadata), or keep the signed coupling "
            "for full signed dynamics and make no onset-threshold claim."
        )


def ricci_to_adjacency(kappa: Array) -> Array:
    """Back-compat alias of the positive (threshold) Ricci path (FP-2).

    Pre-#1096 callers used this to obtain the non-negative, symmetric,
    zero-diagonal adjacency ``A_κ = max(κ_sym, 0)``. That behaviour is
    UNCHANGED: this now delegates to :func:`ricci_to_positive_adjacency` and
    returns only the adjacency, discarding the audit. New code SHOULD call
    :func:`ricci_to_positive_adjacency` (to inspect the clip audit) or
    :func:`ricci_to_signed_coupling` (to preserve sign). The name is retained
    so existing imports and trajectories keep working bit-for-bit.
    """
    adjacency, _audit = ricci_to_positive_adjacency(kappa, audit=False)
    return adjacency


def phase_transition_boundary(K: float, lorentzian_half_width: float, A: Array) -> BoundaryReport:
    """Compute the synchronisation-onset boundary scalar ``Φ``.

    ``Φ(K, γ, A) = K · λ_max(A) − 2 γ``. Φ = 0 is the predicted onset
    of synchronisation in the Restrepo-Ott-Hunt mean-field limit.

    Parameters
    ----------
    K:
        Coupling strength. Must be finite and ≥ 0.
    lorentzian_half_width:
        Half-width γ of the Lorentzian intrinsic-frequency distribution.
        Must be > 0.
    A:
        Symmetric, non-negative-entry adjacency. Use
        ``ricci_to_adjacency`` if starting from a signed curvature.

    Returns
    -------
    BoundaryReport
        With Φ, K_c, λ_max(A), and γ echoed.

    Raises
    ------
    ValueError
        On contract violation. Fail-closed; no silent repair.
    """
    if not jnp.isfinite(K):
        raise ValueError(f"INV-KR3: K must be finite, got {K}")
    if K < 0.0:
        raise ValueError(f"INV-KR3: K must be ≥ 0, got {K}")
    if lorentzian_half_width <= 0.0:
        raise ValueError(f"INV-KR3: lorentzian_half_width must be > 0, got {lorentzian_half_width}")
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-KR3: A must be square 2-D, got shape {A.shape}")
    if not bool(jnp.all(A >= 0.0)):
        raise ValueError("INV-KR3: A must have non-negative entries (use ricci_to_adjacency).")

    # eigvalsh returns ascending real eigenvalues for symmetric A. Take last.
    A_sym = 0.5 * (A + A.T)
    eigs = jnp.linalg.eigvalsh(A_sym)
    lam_max = float(eigs[-1])
    if lam_max <= 0.0:
        # Disconnected zero matrix: never synchronises at any finite K.
        return BoundaryReport(
            phi=-2.0 * float(lorentzian_half_width),
            K_c=float("inf"),
            lambda_max_A=0.0,
            lorentzian_half_width=float(lorentzian_half_width),
        )
    phi: float = float(K) * lam_max - 2.0 * float(lorentzian_half_width)
    K_c: float = 2.0 * float(lorentzian_half_width) / lam_max
    return BoundaryReport(
        phi=phi,
        K_c=K_c,
        lambda_max_A=lam_max,
        lorentzian_half_width=float(lorentzian_half_width),
    )


# Dynamics ------------------------------------------------------------------


def kuramoto_ricci_rhs(omega: Array, A: Array) -> Callable[[Array], Array]:
    """Factory: return the RHS ``θ̇ = f(θ; ω, A)`` as a closure.

    The factory pattern lets the caller pass a JAX-traceable RHS into
    the T2 ``lyapunov_spectrum`` estimator (which expects ``f: R^n →
    R^n``) without re-binding the network at every call.

    Parameters
    ----------
    omega:
        Intrinsic frequencies, shape ``(N,)``.
    A:
        Adjacency matrix, shape ``(N, N)``, non-negative entries.

    Returns
    -------
    Callable
        ``rhs(theta) -> Array`` of shape ``(N,)``.
    """

    def rhs(theta: Array) -> Array:
        # Pairwise sin(θ_j − θ_i): broadcasting (N,1) − (1,N) and sin.
        # Sum over j gives the i-th component of the coupling.
        delta = theta[None, :] - theta[:, None]
        coupling = jnp.sum(A * jnp.sin(delta), axis=1)
        return omega + coupling

    return rhs


def kuramoto_ricci_step(theta: Array, *, dt: float, omega: Array, A: Array) -> Array:
    """Single midpoint (Heun-RK2) step on ``θ``.

    Pure functional, jit-friendly. Use this as the building block for
    deterministic integration; for a full trajectory or Lyapunov
    spectrum, use ``kuramoto_ricci_trajectory`` or pass
    ``kuramoto_ricci_rhs(omega, A)`` to ``lyapunov_spectrum``.
    """
    rhs = kuramoto_ricci_rhs(omega, A)
    f1 = rhs(theta)
    theta_mid = theta + 0.5 * dt * f1
    f2 = rhs(theta_mid)
    return theta + dt * f2


def kuramoto_ricci_trajectory(
    theta_0: Array,
    *,
    dt: float,
    n_steps: int,
    omega: Array,
    A: Array,
) -> Array:
    """Integrate ``n_steps`` midpoint steps and return phases at each step.

    Returns shape ``(n_steps + 1, N)``: row 0 is ``theta_0``, row k is
    ``θ`` after k integration steps. Bit-identical for identical
    inputs (INV-HPC1).
    """
    if dt <= 0.0:
        raise ValueError(f"INV-KR3: dt must be positive, got {dt}")
    if n_steps <= 0:
        raise ValueError(f"INV-KR3: n_steps must be positive, got {n_steps}")
    if theta_0.ndim != 1:
        raise ValueError(f"INV-KR3: theta_0 must be 1-D, got shape {theta_0.shape}")

    def _step(_i: Array, theta: Array) -> Array:
        return kuramoto_ricci_step(theta, dt=dt, omega=omega, A=A)

    # Build the trajectory by storing each visited state in a result buffer.
    def _step_with_record(carry: tuple[Array, Array], i: Array) -> tuple[tuple[Array, Array], None]:
        theta, traj = carry
        theta_next = _step(i, theta)
        traj_next = traj.at[i + 1].set(theta_next)
        return (theta_next, traj_next), None

    n_keep: int = int(n_steps) + 1
    traj_init: Array = jnp.zeros((n_keep, theta_0.shape[0]), dtype=theta_0.dtype)
    traj_init = traj_init.at[0].set(theta_0)
    (_, traj_final), _ = jax.lax.scan(
        _step_with_record,
        (theta_0, traj_init),
        jnp.arange(int(n_steps), dtype=jnp.int32),
    )
    return traj_final


# Diagnostics ---------------------------------------------------------------


def order_parameter(theta: Array) -> Array:
    """Kuramoto order parameter ``R = |⟨e^{iθ}⟩|`` (INV-K1: ``R ∈ [0, 1]``).

    Accepts shape ``(N,)`` for a single instant or ``(T, N)`` for a
    trajectory; returns scalar or shape ``(T,)`` accordingly.
    """
    z = jnp.mean(jnp.exp(1j * theta), axis=-1)
    return jnp.abs(z)


def coupling_potential(theta: Array, A: Array) -> Array:
    """Pairwise coupling potential ``V = ½ Σ_ij A_ij (1 − cos(θ_i − θ_j))``.

    Non-increasing under the gradient flow ``θ̇ = −∂V/∂θ`` (homogeneous
    limit ``ω = 0``). INV-KR3 references this exact form.

    For a non-negative ``A``, ``V ≥ 0`` and ``V = 0`` iff all phases
    are equal. The factor ½ cancels the i↔j double counting.
    """
    delta = theta[None, :] - theta[:, None]
    return 0.5 * jnp.sum(A * (1.0 - jnp.cos(delta)))
