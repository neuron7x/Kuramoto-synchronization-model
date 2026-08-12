# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Second-order Kuramoto model with inertia and damping.

The classical Kuramoto model is first-order (overdamped).  For power
grid stability analysis, generator rotors have physical inertia:

    m_i · θ̈_i + d_i · θ̇_i = ω_i + K · Σ_j A_ij · sin(θ_j - θ_i)

where:
    m_i = inertia (moment of inertia / angular momentum coefficient)
    d_i = damping (friction / governor response)
    ω_i = natural frequency (power injection - demand)

This is equivalent to the swing equation in power systems:

    M_i · δ̈_i + D_i · δ̇_i = P_m,i - P_e,i(δ)

The second-order system exhibits richer dynamics: oscillatory
transients, frequency nadir, rate of change of frequency (RoCoF),
and inertia-dependent stability margins.

Usage::

    from core.kuramoto.second_order import SecondOrderKuramotoEngine
    config = KuramotoConfig(N=50, K=5.0, dt=0.005, steps=10000)
    engine = SecondOrderKuramotoEngine(config, mass=1.0, damping=0.1)
    result = engine.run()
    print(result.summary)
    # Access velocity: result.metadata["velocities"]  # (steps+1, N)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Union

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter

__all__ = [
    "SecondOrderDivergenceError",
    "SecondOrderKuramotoEngine",
    "SecondOrderResult",
    "SecondOrderStabilityReport",
]

_MetaValue = Union[str, int, float, bool, None]

_logger = logging.getLogger(__name__)


class SecondOrderDivergenceError(ValueError):
    """Fail-closed signal that the integrated state stopped being admissible.

    Raised by :meth:`SecondOrderKuramotoEngine.run` under the INV-HPC2
    ``finite in → finite out, else fail closed`` discipline:

    * a non-finite (NaN/Inf) phase or velocity appeared at a step, or
    * an opted-in ``rocof_max`` rate-of-change-of-frequency bound was
      exceeded (|θ̈_i| · ... — see ``rocof_max`` below).

    Subclasses :class:`ValueError` so existing ``except ValueError`` contract
    handlers keep working; the carried attributes name the offending step and
    the divergence so the failure is diagnosable rather than silent.
    """

    def __init__(self, message: str, *, step: int, kind: str) -> None:
        super().__init__(message)
        self.step = step
        self.kind = kind


# Partial-audit honesty (issue #1107). The second-order engine fails closed on
# non-finite states and an opted-in RoCoF bound only — it is NOT a full
# stability audit. These constants declare exactly that scope and enumerate the
# checks still missing, so passing CI cannot be read as a complete numerical
# stability validation. Full coverage is tracked as a follow-up
# SecondOrderStabilityAudit object (issue #1109; protocol #1107).
_AUDIT_SCOPE = "nonfinite_and_rocof_only"
_REMAINING_AUDIT_GAPS: tuple[str, ...] = (
    "energy_like_drift",
    "phase_spread_bound",
    "solver_metadata",
    "stiffness_assumption",
    "cross_solver_reference",
)


@dataclass
class SecondOrderResult:
    """Extended result wrapping KuramotoResult with velocity trajectories.

    The numerical guard implemented here is partial: ``audit_scope`` is
    ``"nonfinite_and_rocof_only"`` and ``remaining_audit_gaps`` lists the checks
    a full :class:`SecondOrderStabilityAudit` would still need. These are
    declarative provenance, not numeric outputs.
    """

    base: KuramotoResult
    velocities: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.velocities.size > 0:
            self.base.summary.update(self._compute_frequency_metrics())

    @property
    def audit_scope(self) -> str:
        """Declared scope of the fail-closed numerical guard (partial)."""
        return _AUDIT_SCOPE

    @property
    def remaining_audit_gaps(self) -> tuple[str, ...]:
        """Stability checks NOT covered here — explicitly preserved, not hidden."""
        return _REMAINING_AUDIT_GAPS

    @property
    def phases(self) -> NDArray[np.float64]:
        return self.base.phases

    @property
    def order_parameter(self) -> NDArray[np.float64]:
        return self.base.order_parameter

    @property
    def time(self) -> NDArray[np.float64]:
        return self.base.time

    @property
    def config(self) -> KuramotoConfig:
        return self.base.config

    @property
    def summary(self) -> dict[str, Any]:
        return self.base.summary

    def _compute_frequency_metrics(self) -> dict[str, Any]:
        """Power-grid relevant metrics from velocity trajectories."""
        v = self.velocities
        dt = self.base.config.dt
        return {
            "frequency_nadir": float(np.min(v)),
            "frequency_zenith": float(np.max(v)),
            "max_rocof": float(np.max(np.abs(np.diff(v, axis=0) / dt))),
            "final_frequency_spread": float(np.std(v[-1])),
            "mean_frequency": float(np.mean(v[-1])),
            "settling_time_95pct": self._settling_time(v),
        }

    def _settling_time(self, v: NDArray[np.float64], threshold: float = 0.05) -> float:
        """Time for frequency spread to settle within threshold of final value."""
        t = self.base.time
        final_spread = np.std(v[-1])
        for k in range(len(v) - 1, -1, -1):
            if np.std(v[k]) > final_spread + threshold:
                return float(t[min(k + 1, len(t) - 1)])
        return 0.0


@dataclass(frozen=True, slots=True)
class SecondOrderStabilityReport:
    """Offline numerical-stability audit of an integrated second-order run.

    This complements the engine's *runtime* fail-closed guard (non-finite +
    optional RoCoF, ``SecondOrderResult.audit_scope``): it is a post-hoc
    analysis of a completed trajectory that closes the gaps the runtime guard
    leaves open (issue #1109). Every field is a measured diagnostic, not an
    asserted physical law:

    energy_like_drift
        Relative drift of the swing energy
        ``E = ½Σ mᵢθ̇ᵢ² − Σ ωᵢθᵢ − ½Σ adjᵢⱼ cos(θⱼ−θᵢ)`` over the trajectory,
        ``(max E − min E)/max|E|``. In the conservative regime (ω≡0, d≡0) the
        symplectic Störmer–Verlet map keeps this bounded (INV-K8/K9/K10).
    energy_conservative_regime
        Whether ω≡0 and d≡0, i.e. energy is expected to be (near-)conserved.
    phase_spread_bound
        Maximum over time of ``max_i θᵢ − min_i θᵢ`` (raw, unwrapped phases).
    stiffness_ratio
        ``ω_fast · dt`` where ``ω_fast = √(λ_max(L_adj)/m_min)`` is the fastest
        linearised swing mode about synchrony (L_adj = Laplacian of the
        coupling matrix). Explicit fixed-step integration only resolves modes
        with ``ω·dt ≪ 1``.
    cross_solver_max_deviation
        Max state deviation between the engine's Verlet trajectory and an
        independent explicit RK4 integration of the same IVP over the audit
        horizon — a genuine cross-implementation check.
    cross_solver_max_deviation
        Endpoint deviation (at the audit horizon) — kept for back-compat.
    trajectory_wide_cross_solver_max
        Max state deviation between Verlet and RK4 over EVERY step in
        ``[0, horizon]``, not just the endpoint. Strictly ≥
        ``cross_solver_max_deviation``: an endpoint that happens to re-converge
        can hide a mid-trajectory divergence, so agreement is judged on this.
    remaining_gaps
        Stability properties this audit still does NOT cover.
    metric_validity_flags
        Per-metric validity gates. ``energy_model_valid`` is True only when the
        coupling matrix is symmetric and unsigned — the swing-energy
        ``V = −½Σ adjᵢⱼ cos(Δθ)`` is a conserved potential only then; an
        asymmetric or signed adjacency makes ``energy_like_drift`` physically
        meaningless and must not be read as a conservation result.
    audit_passed
        True iff every IN-SCOPE bounded check held (energy bounded where a valid
        conservation claim is made, phase spread finite, trajectory-wide
        cross-solver agreement). A measured pass of the partial audit — NOT a
        stability certificate.
    failure_reason
        Names of the checks that failed; empty iff ``audit_passed``.
    promotion_allowed
        ``audit_passed AND remaining_gaps == ()``. Because ``remaining_gaps`` is
        non-empty by construction, this is ALWAYS False: an offline diagnostic
        with open gaps can never promote second-order S7 stability. The firewall
        against the "full audit ⇒ certified stable" overclaim.
    """

    audit_scope: str
    energy_like_drift: float
    energy_conservative_regime: bool
    phase_spread_bound: float
    phase_spread_finite: bool
    stiffness_ratio: float
    stiffness_regime: str
    cross_solver_reference: str
    cross_solver_max_deviation: float
    trajectory_wide_cross_solver_max: float
    cross_solver_agrees: bool
    solver_metadata: dict[str, _MetaValue]
    metric_validity_flags: dict[str, bool]
    audit_passed: bool
    failure_reason: tuple[str, ...]
    promotion_allowed: bool
    remaining_gaps: tuple[str, ...]


def _swing_energy_trajectory(
    theta: NDArray[np.float64],
    vel: NDArray[np.float64],
    mass: NDArray[np.float64],
    omega: NDArray[np.float64],
    adj: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Evaluate swing energy with O(N^2) peak pairwise working memory.

    This helper keeps :meth:`SecondOrderKuramotoEngine.audit` as an orchestration
    method while preserving the same energy expression:
    ``T + V_drive + V_pairwise``. Each pairwise potential snapshot materializes
    only one ``N×N`` phase-delta matrix, never the full trajectory-wide
    ``T×N×N`` tensor.
    """
    kinetic = 0.5 * (mass * vel * vel).sum(axis=1)
    drive = -(omega * theta).sum(axis=1)
    pairwise_terms: list[float] = []
    for theta_t in theta:
        delta = theta_t[np.newaxis, :] - theta_t[:, np.newaxis]
        pairwise_terms.append(-0.5 * float(np.sum(adj * np.cos(delta))))
    pairwise = np.asarray(pairwise_terms, dtype=np.float64)
    return kinetic + drive + pairwise


class SecondOrderKuramotoEngine:
    """Second-order Kuramoto (swing equation) integrator.

    Parameters
    ----------
    config : KuramotoConfig
        Standard config.
    mass : float | NDArray
        Inertia coefficient(s).  Scalar for uniform, array(N) for heterogeneous.
    damping : float | NDArray
        Damping coefficient(s).  Scalar or array(N).
    velocity0 : NDArray | None
        Initial angular velocities.  Default: zeros (standstill).
    rocof_max : float | None
        Optional fail-closed bound on the instantaneous rate-of-change-of-
        frequency, max_i |θ̇_i(k+1) − θ̇_i(k)| / dt (the same quantity reported
        descriptively as ``max_rocof`` in the summary).  Default ``None`` leaves
        the bound OFF, so a healthy run is byte-identical to prior behaviour.
        When set to a finite positive value, a step whose RoCoF exceeds it
        raises :class:`SecondOrderDivergenceError` instead of letting an
        unphysical frequency excursion propagate into the summary (INV-HPC2).
    """

    def __init__(
        self,
        config: KuramotoConfig,
        mass: float | NDArray[np.float64] = 1.0,
        damping: float | NDArray[np.float64] = 0.1,
        velocity0: NDArray[np.float64] | None = None,
        rocof_max: float | None = None,
    ) -> None:
        self._cfg = config
        N = config.N
        self._omega, self._theta0 = self._resolve_ic(config)
        self._adj = self._resolve_adj(config)

        if rocof_max is not None and not (np.isfinite(rocof_max) and rocof_max > 0.0):
            raise ValueError(
                f"'rocof_max' must be a finite positive float when provided; got {rocof_max!r}."
            )
        self._rocof_max = float(rocof_max) if rocof_max is not None else None

        # Broadcast mass and damping to per-oscillator arrays
        self._mass = np.broadcast_to(np.asarray(mass, dtype=np.float64), (N,)).copy()
        self._damping = np.broadcast_to(np.asarray(damping, dtype=np.float64), (N,)).copy()

        if np.any(self._mass <= 0):
            raise ValueError("Mass must be strictly positive for all oscillators.")
        if np.any(self._damping < 0):
            raise ValueError("Damping must be non-negative for all oscillators.")

        self._v0 = velocity0.copy() if velocity0 is not None else np.zeros(N, dtype=np.float64)

        _logger.info(
            "SecondOrderKuramotoEngine: N=%d, K=%.4f, m=[%.3f, %.3f], d=[%.3f, %.3f]",
            N,
            config.K,
            float(np.min(self._mass)),
            float(np.max(self._mass)),
            float(np.min(self._damping)),
            float(np.max(self._damping)),
        )

    def run(self) -> SecondOrderResult:
        """Integrate second-order system using Störmer-Verlet (symplectic)."""
        cfg = self._cfg
        N = cfg.N
        steps = cfg.steps
        dt = cfg.dt

        phases = np.empty((steps + 1, N), dtype=np.float64)
        velocities = np.empty((steps + 1, N), dtype=np.float64)
        R_arr = np.empty(steps + 1, dtype=np.float64)
        time_arr = np.arange(steps + 1, dtype=np.float64) * dt

        theta = self._theta0.copy()
        v = self._v0.copy()
        phases[0] = theta
        velocities[0] = v
        R_arr[0] = _order_parameter(theta)

        m = self._mass
        d = self._damping
        inv_m = 1.0 / m
        rocof_max = self._rocof_max
        inv_dt = 1.0 / dt

        for k in range(steps):
            # Velocity Verlet for the swing equation m·θ̈ = (ω + coupling) − d·θ̇.
            # INV-K9/K10: the position half-step uses the full acceleration
            # a(θ, v) = (1/m)(ω + coupling(θ) − d·v).
            accel = inv_m * (self._omega + self._coupling(theta) - d * v)
            theta_new = theta + v * dt + 0.5 * accel * dt * dt

            # The velocity half-step must evaluate the velocity-dependent
            # damping −d·v at the NEW velocity (BBK / semi-implicit velocity
            # Verlet). Solving v_new = v + ½dt·(a(θ,v) + a(θ_new, v_new)) for
            # v_new gives the closed form below. Evaluating −d·v at the OLD
            # velocity instead integrates the friction by explicit Euler, which
            # drops the damped map to first order and breaks the symplectic /
            # det(M)=exp(−Σd/m·dt) contraction claim (INV-K10). Undamped (d=0)
            # this reduces EXACTLY to standard velocity Verlet (half·d = 0).
            force = self._omega + self._coupling(theta)
            force_new = self._omega + self._coupling(theta_new)
            half = 0.5 * dt * inv_m
            v_new = (v + half * (force + force_new - d * v)) / (1.0 + half * d)

            # INV-HPC2: finite in -> finite out, else fail closed. A non-finite
            # state can never produce meaningful phases/summary, so stop here and
            # name the step rather than propagate NaN/Inf silently.
            if not (np.isfinite(theta_new).all() and np.isfinite(v_new).all()):
                raise SecondOrderDivergenceError(
                    f"INV-HPC2 VIOLATED: non-finite second-order state at step {k} "
                    f"(theta finite={bool(np.isfinite(theta_new).all())}, "
                    f"velocity finite={bool(np.isfinite(v_new).all())}). "
                    f"Integration diverged (NaN/Inf); refusing to emit a "
                    f"non-finite trajectory. At N={N}, K={cfg.K:.4f}, dt={dt}, "
                    f"steps={steps}.",
                    step=k,
                    kind="non_finite",
                )

            # Optional opted-in RoCoF bound (default OFF => byte-identical run).
            if rocof_max is not None:
                step_rocof = float(np.max(np.abs(v_new - v)) * inv_dt)
                if step_rocof > rocof_max:
                    raise SecondOrderDivergenceError(
                        f"INV-HPC2 VIOLATED: RoCoF {step_rocof:.6g} exceeded bound "
                        f"rocof_max={rocof_max:.6g} at step {k}. The frequency "
                        f"changed faster than the configured stability limit; "
                        f"failing closed instead of reporting an unphysical "
                        f"max_rocof. At N={N}, K={cfg.K:.4f}, dt={dt}, "
                        f"steps={steps}.",
                        step=k,
                        kind="rocof_exceeded",
                    )

            theta = theta_new
            v = v_new

            phases[k + 1] = theta
            velocities[k + 1] = v
            R_arr[k + 1] = _order_parameter(theta)

        base = KuramotoResult(
            phases=phases,
            order_parameter=R_arr,
            time=time_arr,
            config=cfg,
        )
        return SecondOrderResult(base=base, velocities=velocities)

    def audit(
        self,
        *,
        cross_solver_steps: int = 200,
        agreement_tol: float = 1e-3,
        energy_drift_tol: float = 1e-3,
    ) -> SecondOrderStabilityReport:
        """Run the engine and produce a bounded numerical-stability audit (#1109).

        Closes the gaps the runtime guard leaves open: energy drift, phase
        spread, solver metadata, stiffness regime, and an independent
        trajectory-wide cross-solver agreement check. This is a SCOPE-LIMITED
        diagnostic, NOT a full S7 stability certificate: ``remaining_gaps``
        stays non-empty and ``promotion_allowed`` is therefore always False.
        Does not mutate or weaken the dynamics.
        """
        result = self.run()
        theta = result.base.phases
        vel = result.velocities
        cfg = self._cfg
        dt = cfg.dt
        m, d, omega, adj = self._mass, self._damping, self._omega, self._adj

        # --- energy-like drift: swing energy over the trajectory ---
        # Physics is unchanged: E = T + V_drive + V_pairwise. The evaluator keeps
        # audit() componentized while avoiding a trajectory-wide T×N×N tensor.
        energy = _swing_energy_trajectory(theta, vel, m, omega, adj)
        e_scale = float(np.abs(energy).max()) + 1e-12
        energy_like_drift = float((energy.max() - energy.min()) / e_scale)
        conservative = bool(np.allclose(omega, 0.0) and np.allclose(d, 0.0))

        # --- phase spread (raw, unwrapped) ---
        spread = theta.max(axis=1) - theta.min(axis=1)
        phase_spread_bound = float(spread.max())
        phase_spread_finite = bool(np.isfinite(spread).all())

        # --- stiffness: fastest linearised swing mode vs dt ---
        adj_sym = 0.5 * (adj + adj.T)
        laplacian = np.diag(adj_sym.sum(axis=1)) - adj_sym
        lam_max = float(np.linalg.eigvalsh(laplacian).max())
        # bounds: a graph Laplacian is positive semi-definite, so λ_max ≥ 0 in
        # exact arithmetic; eigvalsh can return a tiny negative due to rounding.
        # Floor at 0 keeps the sqrt real — a numerical guard, not a physics clamp.
        lam_max_nonneg = max(lam_max, 0.0)
        omega_fast = float(np.sqrt(lam_max_nonneg / float(m.min())))
        stiffness_ratio = float(omega_fast * dt)
        if stiffness_ratio <= 0.1:
            stiffness_regime = "resolved"
        elif stiffness_ratio <= 1.0:
            stiffness_regime = "marginally_resolved"
        else:
            stiffness_regime = "underresolved_stiff"

        # --- cross-solver: independent explicit RK4 over the audit horizon ---
        # bounds: clamp the cross-solver horizon to [1, run length]. At least one
        # step is required to compare; capping at cfg.steps keeps the index in
        # range. A configuration guard, not a physics clamp — no INV applies.
        horizon = max(1, min(int(cross_solver_steps), cfg.steps))
        rk_theta_traj, rk_v_traj = self._rk4_trajectory(horizon)
        # Endpoint deviation (kept for back-compat reporting).
        deviation = float(
            max(
                np.abs(rk_theta_traj[horizon] - theta[horizon]).max(),
                np.abs(rk_v_traj[horizon] - vel[horizon]).max(),
            )
        )
        # Trajectory-wide max over EVERY step in [0, horizon]: an endpoint that
        # re-converges can mask a mid-trajectory divergence, so agreement is
        # judged on the worst step, not the last one.
        traj_theta_dev = float(np.abs(rk_theta_traj - theta[: horizon + 1]).max())
        traj_v_dev = float(np.abs(rk_v_traj - vel[: horizon + 1]).max())
        trajectory_wide_cross_solver_max = max(traj_theta_dev, traj_v_dev)
        cross_solver_agrees = bool(
            np.isfinite(trajectory_wide_cross_solver_max)
            and trajectory_wide_cross_solver_max <= agreement_tol
        )

        solver_metadata: dict[str, _MetaValue] = {
            "integrator": "stoermer_verlet",
            "order": 2,
            "symplectic": True,
            "adaptive": False,
            "fixed_step": True,
            "dt": float(dt),
            "steps": int(cfg.steps),
            "rtol": None,
            "atol": None,
            "mass_min": float(m.min()),
            "mass_max": float(m.max()),
            "damping_min": float(d.min()),
            "damping_max": float(d.max()),
            "energy_evaluator": "streamed_pairwise_potential",
            "energy_peak_memory": "O(N^2)",
        }

        # --- metric validity: the swing-energy conservation diagnostic is only
        # meaningful for a symmetric, unsigned coupling matrix (the potential
        # V = −½Σ adj cos(Δθ) is conserved only then). An asymmetric/signed
        # adjacency makes energy_like_drift physically uninterpretable. ---
        adjacency_symmetric = bool(np.allclose(adj, adj.T))
        adjacency_unsigned = bool((adj >= 0.0).all())
        energy_model_valid = adjacency_symmetric and adjacency_unsigned
        metric_validity_flags: dict[str, bool] = {
            "adjacency_symmetric": adjacency_symmetric,
            "adjacency_unsigned": adjacency_unsigned,
            "energy_model_valid": energy_model_valid,
            "phase_spread_finite": phase_spread_finite,
            "cross_solver_trajectory_wide": cross_solver_agrees,
        }

        # --- audit verdict: fail closed on any in-scope check that did not hold. ---
        failures: list[str] = []
        if conservative and energy_model_valid:
            if not (np.isfinite(energy_like_drift) and energy_like_drift <= energy_drift_tol):
                failures.append("energy_drift_exceeds_tol")
        if conservative and not energy_model_valid:
            failures.append("energy_conservation_claimed_on_invalid_model")
        if not phase_spread_finite:
            failures.append("phase_spread_nonfinite")
        if not cross_solver_agrees:
            failures.append("cross_solver_trajectory_disagreement")
        audit_passed = not failures

        remaining_gaps = (
            "full_lyapunov_spectrum",
            "long_horizon_secular_growth",
            "heterogeneous_damping_modal_analysis",
        )
        # Promotion firewall: a passing partial audit is NOT a stability
        # certificate. With remaining_gaps non-empty this is always False.
        promotion_allowed = bool(audit_passed and not remaining_gaps)

        return SecondOrderStabilityReport(
            audit_scope="energy_phase_solver_stiffness_crosssolver",
            energy_like_drift=energy_like_drift,
            energy_conservative_regime=conservative,
            phase_spread_bound=phase_spread_bound,
            phase_spread_finite=phase_spread_finite,
            stiffness_ratio=stiffness_ratio,
            stiffness_regime=stiffness_regime,
            cross_solver_reference="explicit_rk4",
            cross_solver_max_deviation=deviation,
            trajectory_wide_cross_solver_max=trajectory_wide_cross_solver_max,
            cross_solver_agrees=cross_solver_agrees,
            solver_metadata=solver_metadata,
            metric_validity_flags=metric_validity_flags,
            audit_passed=audit_passed,
            failure_reason=tuple(failures),
            promotion_allowed=promotion_allowed,
            remaining_gaps=remaining_gaps,
        )

    def _rk4_trajectory(self, steps: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Independent explicit RK4 integration of the same IVP (cross-check).

        Returns the FULL ``(steps+1, N)`` theta/velocity trajectories. A
        different integrator than the engine's symplectic Verlet, so close
        agreement at every step (not just the endpoint) is evidence the Verlet
        trajectory is correct rather than a self-consistent artefact.
        """
        dt = self._cfg.dt
        inv_m = 1.0 / self._mass
        omega, d = self._omega, self._damping
        n = self._cfg.N

        def deriv(
            theta: NDArray[np.float64], v: NDArray[np.float64]
        ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
            accel: NDArray[np.float64] = inv_m * (omega + self._coupling(theta) - d * v)
            return v, accel

        theta_traj = np.empty((steps + 1, n), dtype=np.float64)
        v_traj = np.empty((steps + 1, n), dtype=np.float64)
        theta = self._theta0.copy()
        v = self._v0.copy()
        theta_traj[0] = theta
        v_traj[0] = v
        for k in range(steps):
            k1t, k1v = deriv(theta, v)
            k2t, k2v = deriv(theta + 0.5 * dt * k1t, v + 0.5 * dt * k1v)
            k3t, k3v = deriv(theta + 0.5 * dt * k2t, v + 0.5 * dt * k2v)
            k4t, k4v = deriv(theta + dt * k3t, v + dt * k3v)
            theta = theta + (dt / 6.0) * (k1t + 2.0 * k2t + 2.0 * k3t + k4t)
            v = v + (dt / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v)
            theta_traj[k + 1] = theta
            v_traj[k + 1] = v
        return theta_traj, v_traj

    def _coupling(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Compute coupling forces Σ_j A_ij sin(θ_j - θ_i)."""
        diff = theta[np.newaxis, :] - theta[:, np.newaxis]
        result: NDArray[np.float64] = (self._adj * np.sin(diff)).sum(axis=1)
        return result

    @staticmethod
    def _resolve_ic(cfg: KuramotoConfig) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        rng = np.random.default_rng(cfg.seed)
        omega = (
            cfg.omega.astype(np.float64, copy=False)
            if cfg.omega is not None
            else rng.standard_normal(cfg.N)
        )
        theta0 = (
            cfg.theta0.astype(np.float64, copy=False)
            if cfg.theta0 is not None
            else rng.uniform(0.0, 2.0 * np.pi, cfg.N)
        )
        return omega, theta0

    @staticmethod
    def _resolve_adj(cfg: KuramotoConfig) -> NDArray[np.float64]:
        N, K = cfg.N, cfg.K
        if cfg.adjacency is not None:
            adj = K * cfg.adjacency.astype(np.float64, copy=True)
            np.fill_diagonal(adj, 0.0)
            return adj
        adj = np.full((N, N), K / N, dtype=np.float64)
        np.fill_diagonal(adj, 0.0)
        return adj
