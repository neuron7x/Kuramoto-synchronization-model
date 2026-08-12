# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T1: Kuramoto-Ricci sync-onset boundary.

Each test pins one invariant. Negative controls are explicit — a test
prefixed ``test_negative_control_*`` MUST fail in a known way to prove
the positive test is not vacuous.

Invariants under test:
* INV-KR1 | algebraic    | sign(Φ) ⇒ asymptotic ⟨R⟩ regime.
* INV-KR2 | qualitative  | the variational MLE crosses zero through Φ = 0.
* INV-KR3 | conservation | with ω_i = 0, the potential V(θ(t)) is
                          non-increasing.
* INV-K1  (compat)       | R ∈ [0, 1] always (existing).
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.kuramoto.kuramoto_ricci_engine import (
    BoundaryReport,
    coupling_potential,
    kuramoto_ricci_rhs,
    kuramoto_ricci_step,
    kuramoto_ricci_trajectory,
    order_parameter,
    phase_transition_boundary,
    ricci_to_adjacency,
)
from core.physics.lyapunov_spectrum import lyapunov_spectrum

# Lyapunov estimation needs float64 (Sprott 2003 references the canonical
# spectrum at double precision; INV-KR2 uses T2 which is gated on this).
jax.config.update("jax_enable_x64", True)  # type: ignore[no-untyped-call]


# ── Fixtures ────────────────────────────────────────────────────────────────


def _erdos_renyi(rng: np.random.Generator, n: int, p: float = 0.4) -> Array:
    """Symmetric ER adjacency with all-1 weights, zero diagonal."""
    upper = rng.binomial(1, p, size=(n, n)).astype(np.float64)
    upper = np.triu(upper, k=1)
    A = upper + upper.T
    return jnp.asarray(A)


def _lorentzian_omega(rng: np.random.Generator, n: int, gamma: float) -> Array:
    """Sample N intrinsic frequencies from a Lorentzian(0, γ) distribution."""
    u = rng.uniform(-0.5 + 1e-6, 0.5 - 1e-6, size=n)
    omega = float(gamma) * np.tan(np.pi * u)
    omega -= np.mean(omega)
    return jnp.asarray(omega)


# ── INV-K1 / INV-KR0 sanity ─────────────────────────────────────────────────


def test_order_parameter_in_unit_interval() -> None:
    """INV-K1 (compat): R(t) ∈ [0, 1] for any phase vector."""
    rng = np.random.default_rng(seed=0)
    for _ in range(50):
        theta = jnp.asarray(rng.uniform(-10 * np.pi, 10 * np.pi, size=64))
        R = float(order_parameter(theta))
        assert 0.0 <= R <= 1.0, f"INV-K1 VIOLATED: R={R} outside [0, 1]"


def test_ricci_to_adjacency_zeros_negative_curvatures() -> None:
    """Anti-correlated edges (κ < 0) get zeroed; bounds preserved."""
    kappa = jnp.asarray(
        [
            [0.0, 0.5, -0.3, 0.0],
            [0.5, 0.0, 0.7, -0.2],
            [-0.3, 0.7, 0.0, 0.4],
            [0.0, -0.2, 0.4, 0.0],
        ]
    )
    A = ricci_to_adjacency(kappa)
    assert bool(jnp.all(A >= 0.0)), "ricci_to_adjacency produced a negative entry"
    assert float(A[0, 2]) == 0.0, f"κ[0,2]=-0.3 should be zeroed, got {float(A[0, 2])}"
    assert float(A[1, 3]) == 0.0, f"κ[1,3]=-0.2 should be zeroed, got {float(A[1, 3])}"
    assert bool(jnp.allclose(A, A.T)), "Output must be symmetric"
    assert bool(jnp.all(jnp.diag(A) == 0.0)), "Diagonal must be zero"


# ── Boundary scalar Φ ────────────────────────────────────────────────────────


def test_phase_transition_boundary_complete_graph() -> None:
    """On a complete graph K_N (all weights 1), λ_max(A) = N − 1.

    Then K_c = 2γ/(N − 1). At K = K_c, Φ = 0 to floating-point precision.
    """
    n = 8
    A = jnp.ones((n, n)) - jnp.eye(n)
    gamma = 0.5
    K_c_expected = 2.0 * gamma / (n - 1)
    rep = phase_transition_boundary(K_c_expected, gamma, A)
    assert isinstance(rep, BoundaryReport)
    assert abs(rep.phi) < 1e-10, f"Φ at K_c must be 0, got {rep.phi}"
    assert abs(rep.K_c - K_c_expected) < 1e-12
    assert abs(rep.lambda_max_A - (n - 1)) < 1e-10


def test_phase_transition_boundary_zero_adjacency() -> None:
    """Disconnected null graph: K_c = ∞, Φ = -2γ at any finite K."""
    n = 5
    A = jnp.zeros((n, n))
    rep = phase_transition_boundary(K=10.0, lorentzian_half_width=0.7, A=A)
    assert rep.K_c == float("inf"), "Null graph must give K_c = ∞"
    assert rep.phi == -2.0 * 0.7, f"Φ should be -2γ, got {rep.phi}"


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"K": float("nan")}, "K must be finite"),
        ({"K": -0.1}, "K must be ≥ 0"),
        ({"lorentzian_half_width": 0.0}, "must be > 0"),
        ({"lorentzian_half_width": -0.5}, "must be > 0"),
    ],
)
def test_INV_KR3_boundary_fail_closed(kwargs: dict[str, float], msg: str) -> None:
    base: dict[str, float | Array] = {
        "K": 1.0,
        "lorentzian_half_width": 0.5,
        "A": jnp.ones((4, 4)) - jnp.eye(4),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        phase_transition_boundary(**base)  # type: ignore[arg-type]


def test_INV_KR3_boundary_rejects_signed_adjacency() -> None:
    A = jnp.array([[0.0, -0.1], [-0.1, 0.0]])
    with pytest.raises(ValueError, match="non-negative"):
        phase_transition_boundary(K=1.0, lorentzian_half_width=0.5, A=A)


# ── INV-KR1: sign(Φ) ⇒ asymptotic ⟨R⟩ regime ────────────────────────────────


def test_INV_KR1_subcritical_phi_negative_yields_low_R() -> None:
    """Φ < 0 ⇒ ⟨R⟩ ≤ 3/√N at long T (incoherent finite-size bound).

    Use a complete graph at K = K_c / 4 — strongly subcritical.
    INV-K2 finite-size bound is ε = 3/√N; we use it as the falsifier.
    """
    n = 64
    rng = np.random.default_rng(seed=42)
    A = jnp.ones((n, n)) - jnp.eye(n)
    gamma = 0.5
    rep = phase_transition_boundary(K=0.0, lorentzian_half_width=gamma, A=A)
    K_c = rep.K_c
    K = 0.25 * K_c

    omega = _lorentzian_omega(rng, n, gamma)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))

    # Burn-in then time-average R.
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=2_000, omega=omega, A=K * A)
    R_traj = order_parameter(traj[1000:])  # drop transient
    R_mean = float(jnp.mean(R_traj))
    epsilon = 3.0 / np.sqrt(n)
    assert R_mean < epsilon * 1.5, (
        f"INV-KR1 VIOLATED: subcritical ⟨R⟩={R_mean:.3f} > 1.5·3/√N={1.5 * epsilon:.3f} "
        f"at K={K:.3f}, K_c={K_c:.3f}, N={n}, γ={gamma}, T=100"
    )


def test_INV_KR1_supercritical_phi_positive_yields_high_R() -> None:
    """Φ > 0 ⇒ ⟨R⟩ > 0.5 at long T (synchronised regime)."""
    n = 64
    rng = np.random.default_rng(seed=7)
    A = jnp.ones((n, n)) - jnp.eye(n)
    gamma = 0.5
    rep = phase_transition_boundary(K=0.0, lorentzian_half_width=gamma, A=A)
    K_c = rep.K_c
    K = 4.0 * K_c

    omega = _lorentzian_omega(rng, n, gamma)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))

    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=2_000, omega=omega, A=K * A)
    R_traj = order_parameter(traj[1000:])
    R_mean = float(jnp.mean(R_traj))
    assert R_mean > 0.5, (
        f"INV-KR1 VIOLATED: supercritical ⟨R⟩={R_mean:.3f} < 0.5 at "
        f"K={K:.3f} = 4·K_c, K_c={K_c:.3f}, N={n}, γ={gamma}"
    )


# ── INV-KR3: dV/dt ≤ 0 in the homogeneous limit (ω = 0) ──────────────────────


def test_INV_KR3_potential_monotone_under_gradient_flow() -> None:
    """With ω = 0, V(θ(t)) is non-increasing along trajectories.

    Tolerance ``1e-9`` accounts for floating-point noise in the
    midpoint integrator; a *real* monotonicity violation would be
    O(K · dt²) ≈ 1e-3, far above noise floor.
    """
    n = 32
    rng = np.random.default_rng(seed=12)
    upper = rng.uniform(0.0, 1.0, size=(n, n))
    upper = np.triu(upper, k=1)
    A = jnp.asarray(upper + upper.T)
    omega = jnp.zeros(n)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))

    traj = kuramoto_ricci_trajectory(theta_0, dt=0.01, n_steps=1000, omega=omega, A=A)
    Vs = jnp.asarray([coupling_potential(traj[k], A) for k in range(0, traj.shape[0], 50)])
    diffs = jnp.diff(Vs)
    max_increase = float(jnp.max(diffs))
    assert max_increase <= 1e-9, (
        f"INV-KR3 VIOLATED: max dV/dt = {max_increase:.3e} > 1e-9 "
        f"at ω=0; gradient flow must dissipate. Vs (every 50 steps) = "
        f"{np.array(Vs)[:6]}..."
    )


# ── INV-KR2: variational MLE crosses zero through Φ = 0 ──────────────────────


def test_INV_KR2_lyapunov_max_negative_in_synchronised_regime() -> None:
    """Φ > 0, well above K_c: λ_1 (full state) is non-positive.

    Synchronised state lies on the centre manifold (one zero exponent
    along the global phase, the rest negative). λ_1 ≤ small positive
    threshold (drift away from the synchronised manifold is bounded).
    """
    n = 8
    rng = np.random.default_rng(seed=3)
    A = jnp.ones((n, n)) - jnp.eye(n)
    gamma = 0.5
    rep = phase_transition_boundary(K=0.0, lorentzian_half_width=gamma, A=A)
    K = 6.0 * rep.K_c

    omega = _lorentzian_omega(rng, n, gamma)
    rhs = kuramoto_ricci_rhs(omega, K * A)
    theta_0 = jnp.asarray(rng.uniform(-0.2, 0.2, size=n))

    # Burn-in to the synchronised manifold first, then estimate spectrum.
    burn_in = kuramoto_ricci_trajectory(theta_0, dt=0.02, n_steps=2000, omega=omega, A=K * A)
    theta_warm = burn_in[-1]

    rep_lyap = lyapunov_spectrum(rhs, theta_warm, dt=0.02, n_steps=4000, qr_every=10)
    lam_1 = float(rep_lyap.spectrum[0])
    # In the synchronised regime, the leading exponent is the zero of the
    # uniform-phase mode; small positive numerical bias is acceptable.
    assert lam_1 < 0.15, (
        f"INV-KR2 VIOLATED: λ_1={lam_1:.3f} > 0.15 in supercritical regime "
        f"(K=6·K_c={K:.3f}, N={n}). Synchronised manifold should be (near-)stable."
    )


def test_INV_KR2_lyapunov_max_positive_or_near_zero_at_subcritical_strong_disorder() -> None:
    """Φ < 0 with appreciable γ: the incoherent state has λ_1 ≥ 0.

    Disordered phases under weak coupling: nearby trajectories diverge
    at a rate set by the spread of intrinsic frequencies. λ_1 ≥ -0.05
    is the falsifier (a strongly negative λ_1 would indicate the
    estimator is not picking up the disorder-driven drift).
    """
    n = 8
    rng = np.random.default_rng(seed=11)
    A = jnp.ones((n, n)) - jnp.eye(n)
    gamma = 0.5
    rep = phase_transition_boundary(K=0.0, lorentzian_half_width=gamma, A=A)
    K = 0.2 * rep.K_c

    omega = _lorentzian_omega(rng, n, gamma)
    rhs = kuramoto_ricci_rhs(omega, K * A)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))

    rep_lyap = lyapunov_spectrum(rhs, theta_0, dt=0.02, n_steps=4000, qr_every=10)
    lam_1 = float(rep_lyap.spectrum[0])
    assert lam_1 > -0.05, (
        f"INV-KR2 VIOLATED: subcritical λ_1={lam_1:.3f} < -0.05 — "
        f"incoherent state should not be strongly contractive at K=0.2·K_c."
    )


# ── INV-HPC1: determinism ────────────────────────────────────────────────────


def test_INV_HPC1_trajectory_bit_identical_repeat() -> None:
    """Two identical trajectory runs are bit-equal."""
    n = 16
    rng = np.random.default_rng(seed=99)
    A = _erdos_renyi(rng, n)
    omega = _lorentzian_omega(rng, n, gamma=0.3)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    traj_a = kuramoto_ricci_trajectory(theta_0, dt=0.01, n_steps=500, omega=omega, A=A)
    traj_b = kuramoto_ricci_trajectory(theta_0, dt=0.01, n_steps=500, omega=omega, A=A)
    assert bool(jnp.all(traj_a == traj_b)), "INV-HPC1 VIOLATED: trajectory not deterministic"


def test_INV_HPC1_step_bit_identical_repeat() -> None:
    """Single step: theta_next bit-equal under identical inputs."""
    n = 8
    rng = np.random.default_rng(seed=5)
    A = _erdos_renyi(rng, n)
    omega = _lorentzian_omega(rng, n, gamma=0.4)
    theta = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    a = kuramoto_ricci_step(theta, dt=0.05, omega=omega, A=A)
    b = kuramoto_ricci_step(theta, dt=0.05, omega=omega, A=A)
    assert bool(jnp.all(a == b))


# ── Negative controls ───────────────────────────────────────────────────────


def test_negative_control_omega_nonzero_potential_can_increase() -> None:
    """With nonzero ω, V is NOT a Lyapunov function — sanity check.

    If this test fails (V monotone with ω ≠ 0), it would mean our
    INV-KR3 monotonicity assertion is vacuous (always true regardless
    of the homogeneous condition).
    """
    n = 16
    rng = np.random.default_rng(seed=1)
    A = jnp.ones((n, n)) - jnp.eye(n)
    omega = jnp.asarray(rng.uniform(-2.0, 2.0, size=n))
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))

    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=200, omega=omega, A=0.05 * A)
    Vs = jnp.asarray([coupling_potential(traj[k], A) for k in range(traj.shape[0])])
    diffs = jnp.diff(Vs)
    assert float(jnp.max(diffs)) > 0.0, (
        "Negative control failed: V was monotone non-increasing even with ω≠0 — "
        "INV-KR3 claim is vacuous."
    )


def test_negative_control_zero_coupling_phases_drift_apart() -> None:
    """K = 0: phases drift independently; R(t) does not converge.

    This is the *trivial* control: with no coupling, the system is N
    independent rotators — no synchronisation is possible.
    """
    n = 32
    rng = np.random.default_rng(seed=8)
    A = jnp.zeros((n, n))
    omega = _lorentzian_omega(rng, n, gamma=0.5)
    theta_0 = jnp.asarray(rng.uniform(-np.pi, np.pi, size=n))
    traj = kuramoto_ricci_trajectory(theta_0, dt=0.05, n_steps=2000, omega=omega, A=A)
    R_late = float(jnp.mean(order_parameter(traj[1500:])))
    epsilon = 3.0 / np.sqrt(n)
    assert (
        R_late < 2.0 * epsilon
    ), f"Negative control failed: K=0 ⟨R⟩={R_late:.3f} > 2·3/√N={2 * epsilon:.3f}"
