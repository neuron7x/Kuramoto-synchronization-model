# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T18 — P1 Kuramoto invariants: monotone R(K), incoherent scaling, Lyapunov.

Three physically distinct P1 invariants tested against the production
``core.kuramoto.engine.KuramotoEngine``:

* **INV-K4** (conditional / sweep): steady-state R is monotone
  non-decreasing in coupling strength K for the standard all-to-all
  model without frequency-degree correlation.

* **INV-K5** (statistical / ensemble): in the fully incoherent regime
  (K=0), the mean order parameter scales as O(1/sqrt(N)) — the
  finite-size noise floor predicted by the central limit theorem on the
  unit circle.

* **INV-K7** (monotonic / trajectory): the Lyapunov functional
  V = -(K*N/2)*R^2 is non-increasing along trajectories with identical
  natural frequencies (all omega_i = 0), confirming gradient descent
  on the Kuramoto potential landscape.

* **INV-K8** (conservation / trajectory): the *second-order* swing-equation
  total energy E = (1/2)*sum(m*theta_dot^2) + V is conserved under the
  Stoermer-Verlet integrator when undamped (omega=0, d=0) and is monotone
  non-increasing when damped (omega=0, d>0). For the all-to-all model
  V = -(K*N/2)*R^2 + const (the INV-K7 potential), so E is observable
  black-box from velocities and R. Defends the "symplectic, energy-conserving"
  docstring claim in ``core.kuramoto.second_order`` against the two regression
  classes that survive every prior assertion: non-symplectic (Euler) drift
  and damping-sign inversion (anti-damping = energy injection).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine
from core.kuramoto.second_order import SecondOrderKuramotoEngine

# ---------------------------------------------------------------------------
# INV-K4: R_inf(K1) <= R_inf(K2) when K1 < K2  (sweep / conditional)
# ---------------------------------------------------------------------------


@pytest.mark.heavy_math
def test_steady_state_R_monotone_in_coupling_strength() -> None:
    """INV-K4: R_inf monotonically non-decreasing in K for standard model.

    Sweep K from 0.5 to 5.0 in 10 steps with N=200 oscillators.
    Compute steady-state R as the mean over the last 500 steps of
    each trajectory and assert the resulting sequence is monotone
    non-decreasing up to at most 2 finite-size noise violations.
    """
    # INV-K4: sweep parameters
    n_oscillators = 200  # N=200
    steps = 2000
    seed = 42
    dt = 0.01  # tolerance: standard integration step
    k_values = np.linspace(0.5, 5.0, 10)

    rng = np.random.default_rng(seed)
    omega = rng.standard_normal(n_oscillators)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)

    r_steady: list[float] = []
    for k_val in k_values:
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=float(k_val),
            omega=omega,
            theta0=theta0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        result = KuramotoEngine(cfg).run()
        trajectory = result.order_parameter
        # INV-K4: late-time window for steady-state estimate
        r_tail = float(np.mean(trajectory[-500:]))
        r_steady.append(r_tail)

    diffs = np.diff(r_steady)
    # INV-K4: count violations (where R decreased)
    violations = int(np.sum(diffs < 0))
    # tolerance: allow up to 2 violations from finite-size noise
    max_violations = 2

    assert violations <= max_violations, (
        f"INV-K4 VIOLATED: R_inf not monotone in K. "
        f"Expected at most {max_violations} violations, observed {violations}. "
        f"R_steady={[f'{r:.4f}' for r in r_steady]}. "
        f"At N={n_oscillators}, steps={steps}, seed={seed}, "
        f"K=[{k_values[0]:.1f}..{k_values[-1]:.1f}]. "
        f"Physical reasoning: standard Kuramoto R_inf is monotone in K "
        f"absent frequency-degree correlation."
    )


# ---------------------------------------------------------------------------
# INV-K5: <R> ~ O(1/sqrt(N)) in incoherent regime  (ensemble / statistical)
# ---------------------------------------------------------------------------


def test_incoherent_order_parameter_scales_as_inverse_sqrt_N() -> None:
    """INV-K5: mean R at K=0 is O(1/sqrt(N)) over >= 50 realizations.

    With zero coupling (K=0), oscillators are independent and R is the
    magnitude of the mean of N unit-circle random variables. By CLT,
    E[R] ~ 1/sqrt(N). We run 50 seeds, compute mean R for each, then
    check |<R> - 1/sqrt(N)| < 3*sigma/sqrt(n_trials).
    """
    # INV-K5: ensemble parameters
    n_oscillators = 100  # N=100
    steps = 500
    n_trials = 50
    dt = 0.01  # tolerance: standard integration step

    # INV-K5: theoretical prediction
    # epsilon: E[R] = sqrt(pi/(4*N)) for Rayleigh distribution of |mean(exp(i*theta))|
    # The exact finite-N result is sqrt(pi/(4*N)), which is O(1/sqrt(N)).
    expected_r = math.sqrt(math.pi / (4.0 * n_oscillators))

    r_means: list[float] = []
    for trial in range(n_trials):
        seed = trial + 1000
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=0.0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        result = KuramotoEngine(cfg).run()
        trajectory = result.order_parameter
        # INV-K5: use late-time mean to avoid transient
        r_means.append(float(np.mean(trajectory[-200:])))

    ensemble_mean = float(np.mean(r_means))
    ensemble_std = float(np.std(r_means, ddof=1))
    # INV-K5: tolerance from standard error of the mean
    # tolerance: 3 * sigma / sqrt(n_trials) — 3-sigma confidence bound
    tolerance = 3.0 * ensemble_std / math.sqrt(n_trials)

    deviation = abs(ensemble_mean - expected_r)

    assert deviation < tolerance, (
        f"INV-K5 VIOLATED: incoherent <R> deviates from sqrt(pi/(4*N)). "
        f"Expected <R> ~ {expected_r:.4f}, observed <R>={ensemble_mean:.4f}, "
        f"|deviation|={deviation:.4f} >= tolerance={tolerance:.4f}. "
        f"At N={n_oscillators}, K=0.0, steps={steps}, n_trials={n_trials}. "
        f"Physical reasoning: at K=0 oscillators are independent; "
        f"R = |mean(exp(i*theta))| ~ sqrt(pi/(4*N)) by Rayleigh statistics."
    )


# ---------------------------------------------------------------------------
# INV-K7: Lyapunov V = -(K*N/2)*R^2 non-increasing for omega=0
# ---------------------------------------------------------------------------


def test_lyapunov_functional_non_increasing_identical_frequencies() -> None:
    """INV-K7: V = -(K*N/2)*R^2 is non-increasing when all omega_i = 0.

    With identical frequencies the Kuramoto system is a gradient flow
    on the potential V. We compute V at each integration step and assert
    it never increases by more than a floating-point tolerance of 1e-10.
    """
    # INV-K7: trajectory parameters
    n_oscillators = 50  # N=50
    k_coupling = 2.0  # K=2.0
    steps = 1000
    seed = 42
    dt = 0.01  # tolerance: standard integration step

    omega = np.zeros(n_oscillators)
    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)

    cfg = KuramotoConfig(
        N=n_oscillators,
        K=k_coupling,
        omega=omega,
        theta0=theta0,
        dt=dt,
        steps=steps,
        seed=seed,
    )
    result = KuramotoEngine(cfg).run()
    r_trajectory = result.order_parameter

    # INV-K7: Lyapunov functional V = -(K*N/2) * R^2
    coeff = -(k_coupling * n_oscillators) / 2.0
    v_trajectory = coeff * r_trajectory**2

    dv = np.diff(v_trajectory)
    # tolerance: 1e-10 for floating-point accumulation in RK4
    fp_tolerance = 1e-10  # epsilon: floating-point tolerance for Lyapunov check
    violations = dv[dv > fp_tolerance]
    n_violations = len(violations)

    assert n_violations == 0, (
        f"INV-K7 VIOLATED: Lyapunov V = -(K*N/2)*R^2 increased {n_violations} times. "
        f"Expected V non-increasing (dV <= {fp_tolerance}), "
        f"observed max dV={float(np.max(dv)):.2e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}. "
        f"Physical reasoning: with omega_i=0 for all i, "
        f"Kuramoto is a gradient system and V is a strict Lyapunov function."
    )


# ---------------------------------------------------------------------------
# INV-K8: second-order swing-equation energy balance
#   E = (1/2) sum(m*theta_dot^2) + V,   V_all-to-all = -(K*N/2)*R^2 + const
#   omega=0, d=0  ->  dE/dt = 0          (conservation, Stoermer-Verlet)
#   omega=0, d>0  ->  dE/dt = -sum(d*theta_dot^2) <= 0   (dissipation)
# ---------------------------------------------------------------------------


def _swing_energy(
    velocities: np.ndarray, r_trajectory: np.ndarray, mass: float, k_coupling: float, n: int
) -> np.ndarray:
    """Total swing energy per timestep for the all-to-all second-order model.

    E(t) = (1/2) * mass * sum_i v_i(t)^2  +  V(t),  with the all-to-all
    potential V(t) = -(K*N/2) * R(t)^2 (the INV-K7 potential, up to an
    additive constant K/2 that cancels in every drift / monotonicity check).
    """
    kinetic = 0.5 * mass * np.sum(velocities**2, axis=1)
    potential = -0.5 * k_coupling * n * r_trajectory**2
    return kinetic + potential


def test_swing_energy_conserved_undamped() -> None:
    """INV-K8 (conservation): undamped swing energy is constant under Verlet.

    With omega_i = 0 and d = 0 the autonomous swing equation is conservative,
    so a symplectic (Stoermer-Verlet) integrator keeps E within a bounded
    O(dt^2) oscillation with no secular trend. We force a genuine transient
    (unlocked theta0 + non-zero velocity0) because the conservation law is
    sharpest exactly at this degenerate (omega=0, d=0) slice. The bound
    range/E_scale < 1e-2 sits ~300x above the observed Verlet drift (~3e-5)
    yet ~40x below the non-symplectic Euler drift (~0.39): it is a true
    falsifier for loss of symplecticity, not a magic number.
    """
    # INV-K8: undamped trajectory parameters
    n_oscillators = 64  # N=64
    k_coupling = 4.0  # K=4.0
    mass = 1.0  # uniform inertia
    steps = 6000
    seed = 0
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    omega = np.zeros(n_oscillators)  # INV-K8 condition: zero natural frequency
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)  # unlocked -> transient
    velocity0 = 0.3 * rng.standard_normal(n_oscillators)  # kinetic seed

    cfg = KuramotoConfig(
        N=n_oscillators,
        K=k_coupling,
        omega=omega,
        theta0=theta0,
        dt=dt,
        steps=steps,
        seed=seed,
    )
    result = SecondOrderKuramotoEngine(
        cfg, mass=mass, damping=0.0, velocity0=velocity0
    ).run()

    energy = _swing_energy(
        result.velocities, result.order_parameter, mass, k_coupling, n_oscillators
    )
    e_scale = 0.5 * k_coupling * n_oscillators  # potential well depth scale
    bounded_drift = float(energy.max() - energy.min())
    rel_drift = bounded_drift / e_scale
    # tolerance: empirically Verlet gives ~3e-5, Euler ~0.39 over this horizon
    drift_bound = 1e-2  # epsilon: symplectic bounded-drift tolerance

    assert rel_drift < drift_bound, (
        f"INV-K8 VIOLATED: undamped swing energy drifted range={bounded_drift:.3e} "
        f"(range/E_scale={rel_drift:.3e}) > tolerance={drift_bound:.1e}. "
        f"Expected bounded O(dt^2) oscillation with no secular trend; this "
        f"magnitude indicates loss of symplecticity (e.g. Euler integration). "
        f"At N={n_oscillators}, K={k_coupling}, d=0, steps={steps}, seed={seed}. "
        f"Physical reasoning: omega=0, d=0 -> dE/dt=0, conservative dynamics."
    )

    # Secular-trend guard: a symplectic scheme has zero net energy drift.
    initial = float(energy[0])
    final = float(energy[-1])
    step_index = np.arange(energy.size, dtype=np.float64)
    secular_slope = float(np.polyfit(step_index, energy, 1)[0])
    secular_total = abs(secular_slope) * energy.size
    rel_secular = secular_total / e_scale
    # tolerance: Verlet secular drift ~2e-4/E_scale; Euler is orders larger
    secular_bound = 1e-2  # epsilon: net (secular) energy drift tolerance

    assert rel_secular < secular_bound, (
        f"INV-K8 VIOLATED: undamped swing energy shows a secular trend "
        f"total={secular_total:.3e} (total/E_scale={rel_secular:.3e}) > "
        f"tolerance={secular_bound:.1e}. Expected a stationary E(t) with zero "
        f"net drift (initial={initial:.3e}, final={final:.3e}); a monotone trend "
        f"indicates non-symplectic integration. "
        f"At N={n_oscillators}, K={k_coupling}, d=0, steps={steps}, seed={seed}. "
        f"Physical reasoning: conservative swing flow -> E(t) is stationary."
    )


def test_swing_energy_dissipated_damped() -> None:
    """INV-K8 (dissipation): damped swing energy is monotone non-increasing.

    With omega_i = 0 and d > 0, dE/dt = -sum(d*theta_dot^2) <= 0, so E must
    not increase along the trajectory and must net-decrease while there is
    motion to dissipate. This clause is the falsifier for a damping-sign
    inversion (-d*theta_dot -> +d*theta_dot), which converts dissipation
    into energy injection and makes E diverge (~10^6 over this horizon).
    """
    # INV-K8: damped trajectory parameters
    n_oscillators = 64  # N=64
    k_coupling = 4.0  # K=4.0
    mass = 1.0  # uniform inertia
    damping = 0.2  # d>0: strictly dissipative
    steps = 6000
    seed = 0
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    omega = np.zeros(n_oscillators)  # INV-K8 condition: zero natural frequency
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)  # unlocked -> transient
    velocity0 = 0.3 * rng.standard_normal(n_oscillators)  # kinetic seed to dissipate

    cfg = KuramotoConfig(
        N=n_oscillators,
        K=k_coupling,
        omega=omega,
        theta0=theta0,
        dt=dt,
        steps=steps,
        seed=seed,
    )
    result = SecondOrderKuramotoEngine(
        cfg, mass=mass, damping=damping, velocity0=velocity0
    ).run()

    energy = _swing_energy(
        result.velocities, result.order_parameter, mass, k_coupling, n_oscillators
    )
    e_scale = 0.5 * k_coupling * n_oscillators  # potential well depth scale
    de = np.diff(energy)
    # tolerance: observed max per-step change is negative; allow tiny float slack
    fp_tolerance = 1e-6 * e_scale  # epsilon: floating-point monotonicity slack
    increases = de[de > fp_tolerance]
    n_increases = len(increases)

    assert n_increases == 0, (
        f"INV-K8 VIOLATED: damped swing energy increased {n_increases} times "
        f"(max step dE={float(np.max(de)):.3e} > tol={fp_tolerance:.3e}). "
        f"Expected dE/dt = -sum(d*theta_dot^2) <= 0; a positive step indicates "
        f"a damping-sign inversion (anti-damping = energy injection). "
        f"At N={n_oscillators}, K={k_coupling}, d={damping}, steps={steps}, seed={seed}. "
        f"Physical reasoning: positive damping can only remove kinetic energy."
    )

    # Net dissipation must actually occur (guards a no-op / near-zero damping path).
    initial = float(energy[0])
    final = float(energy[-1])
    net_change = final - initial
    assert net_change < -fp_tolerance, (
        f"INV-K8 VIOLATED: damped swing energy did not net-decrease "
        f"(observed final-initial={net_change:.3e} >= -tol={-fp_tolerance:.3e}). "
        f"With d={damping}>0 and a seeded transient, dissipation must reduce E. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}. "
        f"Physical reasoning: sustained motion under positive damping bleeds energy."
    )


# ---------------------------------------------------------------------------
# INV-K9: backward-error convergence order of the swing-equation integrator
#   Verlet conserves a shadow Hamiltonian H~ = H + O(dt^2), so the energy
#   error is BOUNDED and scales as max|dE| ~ dt^p with order p = 2.
#   Falsifiable signature: log-log slope of max|dE| vs dt equals the order.
# ---------------------------------------------------------------------------


def test_swing_energy_convergence_order_symplectic() -> None:
    """INV-K9: Stoermer-Verlet energy error scales as max|dE| ~ dt^2 (bounded).

    Backward-error analysis (Hairer-Lubich-Wanner, Geometric Numerical
    Integration): a symplectic integrator exactly conserves a modified
    (shadow) Hamiltonian H~ = H + O(dt^2), so the true-energy error is BOUNDED
    (no secular trend) and its amplitude scales as dt^p with p = the method
    order (2 for velocity-Verlet). We recover p as the least-squares log-log
    slope of bounded energy drift over a geometric dt-ladder and assert it
    matches the theoretical order. This is strictly stronger than the fixed-dt
    amplitude bound of INV-K8: a subtle order degradation (Verlet -> Euler)
    collapses the recovered slope from ~2.01 to ~0.81 and reintroduces secular
    growth, which a single-dt amplitude check can miss.
    """
    # INV-K9: convergence-order parameters
    n_oscillators = 32  # N=32
    k_coupling = 3.0  # K=3.0
    mass = 1.0  # uniform inertia
    horizon = 40.0  # fixed physical time; steps = horizon/dt per ladder rung
    seed = 11
    dt_ladder = [0.02, 0.01, 0.005, 0.0025]  # geometric x2 refinement

    rng = np.random.default_rng(seed)
    omega = np.zeros(n_oscillators)  # INV-K9 condition: autonomous conservative
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)  # unlocked transient
    velocity0 = 0.35 * rng.standard_normal(n_oscillators)  # kinetic seed
    e_scale = 0.5 * k_coupling * n_oscillators  # potential well depth scale

    drifts: list[float] = []
    max_secular = 0.0
    for dt in dt_ladder:
        steps = int(round(horizon / dt))
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=k_coupling,
            omega=omega,
            theta0=theta0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        result = SecondOrderKuramotoEngine(
            cfg, mass=mass, damping=0.0, velocity0=velocity0
        ).run()
        energy = _swing_energy(
            result.velocities, result.order_parameter, mass, k_coupling, n_oscillators
        )
        drifts.append(float(energy.max() - energy.min()))
        idx = np.arange(energy.size, dtype=np.float64)
        secular = abs(float(np.polyfit(idx, energy, 1)[0])) * energy.size
        max_secular = max(max_secular, secular / e_scale)

    # Recovered convergence order = log-log slope of bounded drift vs dt.
    order = float(np.polyfit(np.log(dt_ladder), np.log(drifts), 1)[0])
    theoretical_order = 2.0  # velocity-Verlet is second order
    # tolerance: Verlet recovers ~2.01; Euler collapses to ~0.81 (|deviation|>1)
    order_tol = 0.3  # epsilon: order-recovery band around the theoretical p=2

    assert abs(order - theoretical_order) < order_tol, (
        f"INV-K9 VIOLATED: recovered energy-error convergence order p={order:.3f} "
        f"deviates from theoretical p={theoretical_order:.1f} by more than "
        f"tol={order_tol:.1f}. Expected symplectic O(dt^2) scaling; a low order "
        f"indicates loss of symplecticity (Euler collapses p to ~0.8). "
        f"At N={n_oscillators}, K={k_coupling}, d=0, horizon={horizon}, seed={seed}, "
        f"drifts={['%.2e' % d for d in drifts]}. "
        f"Physical reasoning: Verlet conserves a shadow Hamiltonian H~=H+O(dt^2)."
    )

    # tolerance: bounded (non-secular) drift; Verlet ~6e-6, Euler O(1)
    secular_bound = 1e-3  # epsilon: net secular-trend tolerance over the ladder
    assert max_secular < secular_bound, (
        f"INV-K9 VIOLATED: energy error shows a secular trend "
        f"max(secular/E_scale)={max_secular:.3e} > tol={secular_bound:.1e}. "
        f"Expected bounded oscillation around the shadow Hamiltonian with zero "
        f"net drift; a secular trend indicates non-symplectic integration. "
        f"At N={n_oscillators}, K={k_coupling}, d=0, horizon={horizon}, seed={seed}. "
        f"Physical reasoning: symplectic flow has no secular energy drift."
    )


# ---------------------------------------------------------------------------
# INV-K10: the swing-equation velocity-Verlet map is SYMPLECTIC (root property)
#   The Jacobian M of one undamped (ω=0, d=0) step preserves the symplectic
#   form, MᵀJM = J, to machine precision; equivalently det(M)=1 (Liouville
#   phase-space-volume preservation). Energy conservation (INV-K8) and bounded
#   O(dt²) error (INV-K9) follow as theorems from this single defining property.
# ---------------------------------------------------------------------------


def test_swing_integrator_jacobian_is_symplectic() -> None:
    """INV-K10: velocity-Verlet swing map is symplectic, MᵀJM=J (machine ε).

    Symplecticity is the ROOT property of the integrator; INV-K8 (energy
    conservation) and INV-K9 (bounded O(dt²) error, no secular drift) are
    consequences (Hairer-Lubich-Wanner, Geometric Numerical Integration). We
    build the Jacobian M of one step by complex-step differentiation — exact to
    machine precision, no truncation error — after confirming the complex-safe
    one-step replica reproduces the production SecondOrderKuramotoEngine
    bit-exactly, then assert M preserves the standard symplectic form
    J=[[0,I],[-I,0]] and that det(M)=1 (Liouville volume preservation).
    """
    # INV-K10: Jacobian / symplecticity parameters
    n = 5  # 2n=10 phase-space dimension
    k_coupling = 3.0
    mass = 1.0
    dt = 0.01
    seed = 3

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n)
    velocity0 = 0.3 * rng.standard_normal(n)
    omega = np.zeros(n)  # INV-K10 condition: undamped autonomous (ω=0, d=0)
    adj = np.full((n, n), k_coupling / n)
    np.fill_diagonal(adj, 0.0)

    def verlet_step(state: np.ndarray) -> np.ndarray:
        """Complex-safe one-step velocity-Verlet map (undamped), replicating
        core.kuramoto.second_order.SecondOrderKuramotoEngine.run()."""
        theta, v = state[:n], state[n:]
        accel = (adj * np.sin(theta[None, :] - theta[:, None])).sum(axis=1) / mass
        theta_new = theta + v * dt + 0.5 * accel * dt * dt
        accel_new = (adj * np.sin(theta_new[None, :] - theta_new[:, None])).sum(axis=1) / mass
        v_new = v + 0.5 * (accel + accel_new) * dt
        return np.concatenate([theta_new, v_new])

    # Bind the replica to the production integrator: one step must match bit-exactly.
    cfg = KuramotoConfig(
        N=n, K=k_coupling, omega=omega, theta0=theta0, dt=dt, steps=1, seed=seed
    )
    result = SecondOrderKuramotoEngine(
        cfg, mass=mass, damping=0.0, velocity0=velocity0
    ).run()
    z_engine = np.concatenate([result.phases[1], result.velocities[1]])
    z_replica = verlet_step(np.concatenate([theta0, velocity0]))
    replica_gap = float(np.max(np.abs(z_engine - z_replica)))
    assert np.array_equal(z_engine, z_replica), (
        f"INV-K10 VIOLATED: complex-safe replica diverged from the production "
        f"velocity-Verlet engine by {replica_gap:.3e} (expected 0.0 bit-exact). "
        f"Expected the symplectic-Jacobian probe to test the real integrator. "
        f"At N={n}, K={k_coupling}, d=0, dt={dt}, seed={seed}. "
        f"Physical reasoning: the Jacobian must be that of the shipped step map."
    )

    # Complex-step Jacobian M (machine-precision, no subtractive cancellation).
    z0 = np.concatenate([theta0, velocity0]).astype(np.complex128)
    eps = 1e-200
    jac = np.empty((2 * n, 2 * n), dtype=np.float64)
    for col in range(2 * n):
        zp = z0.copy()
        zp[col] += 1j * eps
        jac[:, col] = verlet_step(zp).imag / eps

    sform = np.block(
        [
            [np.zeros((n, n)), np.eye(n)],
            [-np.eye(n), np.zeros((n, n))],
        ]
    )
    symplectic_residual = float(np.max(np.abs(jac.T @ sform @ jac - sform)))
    det_jac = float(np.linalg.det(jac))
    # tolerance: machine-precision; velocity-Verlet is EXACTLY symplectic so the
    # residual is O(machine ε)≈2e-16, while a non-symplectic step (Euler) gives
    # an O(dt²)≈1e-4 residual — a 12-order separation.
    symplectic_tol = 1e-12  # epsilon: symplectic-form preservation tolerance

    assert symplectic_residual < symplectic_tol, (
        f"INV-K10 VIOLATED: Jacobian is not symplectic, max|MᵀJM − J|="
        f"{symplectic_residual:.3e} > tol={symplectic_tol:.1e}. Expected exact "
        f"symplectic-form preservation (Verlet is symplectic); a non-zero "
        f"residual indicates a non-symplectic integrator (e.g. Euler ~1e-4). "
        f"At N={n}, K={k_coupling}, d=0, dt={dt}, seed={seed}. "
        f"Physical reasoning: symplecticity is the root of INV-K8/K9."
    )
    assert abs(det_jac - 1.0) < symplectic_tol, (
        f"INV-K10 VIOLATED: phase-space volume not preserved, det(M)="
        f"{det_jac:.15f} (expected 1.0, |Δ|={abs(det_jac - 1.0):.3e} > "
        f"tol={symplectic_tol:.1e}). Expected Liouville volume preservation for "
        f"the undamped Hamiltonian flow. "
        f"At N={n}, K={k_coupling}, d=0, dt={dt}, seed={seed}. "
        f"Physical reasoning: a symplectic map has unit Jacobian determinant."
    )


# ---------------------------------------------------------------------------
# INV-K8/K10: long-horizon energy bound (Benettin-Giorgilli)
#   Symplecticity (INV-K10) implies the energy error is BOUNDED over
#   exponentially long times, NOT secular. The bounded drift does not grow
#   with the number of steps — a non-symplectic integrator's would.
# ---------------------------------------------------------------------------


@pytest.mark.heavy_math
def test_swing_energy_bounded_over_long_horizon() -> None:
    """INV-K8/K10: symplectic energy drift is bounded, not secular, long-term.

    Backward-error analysis gives a shadow Hamiltonian conserved over times
    t ~ exp(c/dt) (Benettin-Giorgilli), so the true-energy error stays BOUNDED
    and does not grow with the number of integration steps. We integrate the
    same undamped system at two horizons 4x apart and assert the bounded-drift
    ratio ≈ 1 (Verlet) rather than ≈ 4 (linear secular growth of a
    non-symplectic step). This is the long-time consequence of INV-K10
    symplecticity, beyond the fixed-dt amplitude (INV-K8) and order (INV-K9).
    """
    # INV-K8/K10: long-horizon parameters
    n_oscillators = 8  # N=8
    k_coupling = 3.0  # K=3.0
    mass = 1.0  # uniform inertia
    dt = 0.02  # tolerance: standard integration step
    seed = 5
    short_steps = 20_000
    long_steps = 80_000  # 4x horizon

    rng = np.random.default_rng(seed)
    omega = np.zeros(n_oscillators)  # INV-K8/K10 condition: undamped autonomous
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)
    velocity0 = 0.3 * rng.standard_normal(n_oscillators)
    e_scale = 0.5 * k_coupling * n_oscillators  # potential well depth scale

    def _bounded_drift(steps: int) -> tuple[float, float]:
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=k_coupling,
            omega=omega,
            theta0=theta0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        result = SecondOrderKuramotoEngine(
            cfg, mass=mass, damping=0.0, velocity0=velocity0
        ).run()
        energy = _swing_energy(
            result.velocities, result.order_parameter, mass, k_coupling, n_oscillators
        )
        idx = np.arange(energy.size, dtype=np.float64)
        secular = abs(float(np.polyfit(idx, energy, 1)[0])) * energy.size / e_scale
        return float(energy.max() - energy.min()) / e_scale, secular

    drifts: list[float] = []
    seculars: list[float] = []
    for horizon_steps in (short_steps, long_steps):
        d, s = _bounded_drift(horizon_steps)
        drifts.append(d)
        seculars.append(s)
    drift_short, drift_long = drifts
    secular_short, secular_long = seculars
    ratio = drift_long / drift_short

    # tolerance: Verlet ratio ≈ 1.0; a non-symplectic (Euler) step grows ≈ 3.65
    # over a 4x horizon, so 1.5 cleanly separates bounded from secular.
    ratio_bound = 1.5  # epsilon: bounded-drift growth ceiling (linear would be ≈4)

    assert ratio < ratio_bound, (
        f"INV-K10 VIOLATED: energy drift grew with horizon, ratio(long/short)="
        f"{ratio:.3f} > tol={ratio_bound:.1f} (drift_short={drift_short:.3e}, "
        f"drift_long={drift_long:.3e}). Expected a bounded shadow-Hamiltonian "
        f"error (ratio≈1); growth ≈4x indicates secular, non-symplectic drift. "
        f"At N={n_oscillators}, K={k_coupling}, d=0, dt={dt}, "
        f"steps={short_steps}->{long_steps}, seed={seed}. "
        f"Physical reasoning: a symplectic flow conserves a modified energy "
        f"over exponentially long times (Benettin-Giorgilli)."
    )

    # tolerance: bounded absolute drift and negligible secular trend at horizon
    drift_bound = 1e-2  # epsilon: bounded-drift magnitude tolerance
    secular_bound = 1e-3  # epsilon: net secular-trend tolerance
    assert drift_long < drift_bound and max(secular_short, secular_long) < secular_bound, (
        f"INV-K8 VIOLATED: long-horizon drift={drift_long:.3e} "
        f"(tol={drift_bound:.1e}) or secular={max(secular_short, secular_long):.3e} "
        f"(tol={secular_bound:.1e}) exceeded. Expected bounded, non-secular "
        f"energy over the full horizon. "
        f"At N={n_oscillators}, K={k_coupling}, d=0, dt={dt}, steps={long_steps}, "
        f"seed={seed}. Physical reasoning: symplectic flow has no secular drift."
    )


# ---------------------------------------------------------------------------
# INV-K10 (damped clause): phase-space volume contracts at the dissipation rate
#   With d > 0 the swing map is no longer symplectic; the one-step Jacobian
#   determinant equals exp(-(Σ d_i/m_i)·dt) — Liouville's theorem with damping.
# ---------------------------------------------------------------------------


def test_swing_integrator_damped_volume_contraction() -> None:
    """INV-K10 (damped): det(M) = exp(-(Σ d_i/m_i)·dt) to O(dt²).

    Completes the INV-K10 statement: undamped the map is symplectic (det=1,
    tested above); with damping d>0 phase-space volume contracts at exactly the
    dissipation rate. We build the one-step Jacobian by complex-step
    differentiation and compare det(M) to the Liouville prediction for several
    damping values. This is the dissipative analogue of symplecticity and the
    geometric root of INV-K8's monotone-energy (damped) clause.
    """
    # INV-K10 damped parameters
    n = 6  # 2n=12 phase-space dimension
    k_coupling = 3.0
    mass = 1.0
    dt = 0.005
    seed = 2

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n)
    velocity0 = 0.3 * rng.standard_normal(n)
    omega = np.zeros(n)
    adj = np.full((n, n), k_coupling / n)
    np.fill_diagonal(adj, 0.0)

    def verlet_step_damped(state: np.ndarray, damping: float) -> np.ndarray:
        """Complex-safe one-step velocity-Verlet map with uniform damping."""
        theta, v = state[:n], state[n:]
        accel = (
            omega + (adj * np.sin(theta[None, :] - theta[:, None])).sum(axis=1) - damping * v
        ) / mass
        theta_new = theta + v * dt + 0.5 * accel * dt * dt
        accel_new = (
            omega
            + (adj * np.sin(theta_new[None, :] - theta_new[:, None])).sum(axis=1)
            - damping * v
        ) / mass
        v_new = v + 0.5 * (accel + accel_new) * dt
        return np.concatenate([theta_new, v_new])

    z0 = np.concatenate([theta0, velocity0]).astype(np.complex128)
    eps = 1e-200
    # tolerance: velocity-Verlet reproduces the contraction to O(dt²); at
    # dt=5e-3 the observed relative error is ≤ 2e-5, so 1e-3 is robust.
    contraction_tol = 1e-3  # epsilon: Liouville-contraction relative tolerance

    for damping in (0.2, 0.5):
        jac = np.empty((2 * n, 2 * n), dtype=np.float64)
        for col in range(2 * n):
            zp = z0.copy()
            zp[col] += 1j * eps
            jac[:, col] = verlet_step_damped(zp, damping).imag / eps
        det_jac = float(np.linalg.det(jac))
        predicted = float(np.exp(-(n * damping / mass) * dt))
        rel_err = abs(det_jac - predicted) / predicted

        assert rel_err < contraction_tol, (
            f"INV-K10 VIOLATED (damped): det(M)={det_jac:.10f} deviates from the "
            f"Liouville prediction exp(-(Σd/m)·dt)={predicted:.10f} by rel_err="
            f"{rel_err:.3e} > tol={contraction_tol:.1e}. Expected phase-space "
            f"volume to contract at exactly the dissipation rate. "
            f"At N={n}, K={k_coupling}, d={damping}, m={mass}, dt={dt}, seed={seed}. "
            f"Physical reasoning: dV/dt of the flow = -Σ d_i/m_i (Liouville)."
        )


def test_INV_K10_engine_damped_velocity_is_second_order() -> None:
    """INV-K9/K10: the PRODUCTION engine's damped map is order-2, not Euler.

    The existing INV-K10 damped test exercises a *local* ``verlet_step_damped``
    helper, so a production engine that integrated the velocity-dependent
    friction by explicit Euler (evaluating −d·v at the OLD velocity) passed CI
    while being only first-order. This test drives the real
    ``SecondOrderKuramotoEngine.run`` on a pure-damping system (ω=0, K=0, so
    θ̇(t) = v₀·exp(−(d/m)t) exactly) and asserts the global velocity error
    converges as O(dt²). The Euler-damping regression yields slope ≈ 1 and
    fails this bound.
    """
    d, mass, v0, horizon = 0.5, 1.0, 1.0, 2.0
    dts = [0.04, 0.02, 0.01, 0.005]
    errors: list[float] = []
    for dt in dts:
        steps = int(round(horizon / dt))
        cfg = KuramotoConfig(
            N=2, K=0.0, dt=dt, steps=steps, omega=np.zeros(2), theta0=np.zeros(2)
        )
        engine = SecondOrderKuramotoEngine(
            cfg, mass=mass, damping=d, velocity0=np.array([v0, v0])
        )
        result = engine.run()
        v_final = float(result.velocities[-1, 0])
        analytic = v0 * math.exp(-(d / mass) * steps * dt)
        errors.append(abs(v_final - analytic))

    slope = float(np.polyfit(np.log(dts), np.log(errors), 1)[0])
    assert slope >= 1.9, (
        f"INV-K9/K10 VIOLATED: damped velocity convergence order={slope:.3f} < 1.9. "
        f"Expected O(dt²) (velocity Verlet); explicit-Euler damping gives ≈1. "
        f"Pure damping θ̇(t)=v₀·exp(−(d/m)t) at d={d}, m={mass}, T={horizon}. "
        f"errors={['%.2e' % e for e in errors]} at dts={dts}."
    )
