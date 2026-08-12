# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CALIB-GRID-001 — external ground-truth calibration of the Kuramoto stack.

This is *not* a new hypothesis. It feeds simulated swing-equation phase
data, generated from the published admittance / injection data of a
canonical IEEE test system, into GeoSync's coupling inverse machinery
and measures how well GeoSync recovers what is already known exactly.

Pipeline (mirrors ``PROTOCOL.md``):

1. ``simulate`` — integrate the 2nd-order (swing) Kuramoto model on the
   true coupling :math:`K_{\\mathrm{true}}` with the system's published
   inertia / damping using the existing
   :class:`core.kuramoto.second_order.SecondOrderKuramotoEngine`.
2. ``recover`` — feed the wrapped phase trajectory into the existing
   :class:`core.kuramoto.coupling_estimator.CouplingEstimator`.
3. ``score`` — relative Frobenius error, thresholded-topology F1,
   natural-frequency relative error, and the relative error of
   GeoSync's implied critical-coupling vs the Dörfler–Bullo closed form.

The acceptance gates live in ``PREREGISTRATION.md`` and are *read* (not
re-defined) by :func:`evaluate_gates` so the verdict cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
    estimate_swing_coupling,
)
from core.kuramoto.second_order import SecondOrderKuramotoEngine

from . import frozen_replay
from ._substrate import topology_f1 as _topology_f1
from .grid_data import (
    GridSystem,
    coupling_from_susceptance,
    dorfler_bullo_critical_coupling,
    natural_frequency_from_injection,
)

__all__ = [
    "SimConfig",
    "CalibrationMetrics",
    "ground_truth",
    "simulate_phases",
    "recover_coupling",
    "recover_coupling_swing",
    "score_recovery",
    "run_calibration",
]


@dataclass(frozen=True)
class SimConfig:
    """Pre-registered simulation + recovery configuration.

    Every numeric here is committed in ``PREREGISTRATION.md`` before the
    full run; post-data edits invalidate the artifact (fail-closed).
    """

    coupling_scale: float = 8.0
    dt: float = 0.01
    steps: int = 8000
    keep_frac: float = 0.6
    theta0_perturb: float = 0.6
    seed: int = 42
    noise_sigma: float = 0.02
    lambda_reg: float = 0.02
    penalty: str = "mcp"
    topology_rel_threshold: float = 0.10

    def __post_init__(self) -> None:
        if self.coupling_scale <= 0.0:
            raise ValueError("coupling_scale must be > 0")
        if not 0.0 < self.keep_frac <= 1.0:
            raise ValueError("keep_frac must lie in (0, 1]")
        if self.theta0_perturb <= 0.0:
            raise ValueError(
                "theta0_perturb must be > 0 — a frozen equilibrium "
                "carries no identification signal (persistent-excitation "
                "condition for second-order Kuramoto identification)"
            )
        if self.noise_sigma < 0.0:
            raise ValueError("noise_sigma must be ≥ 0")
        if self.dt <= 0.0:
            raise ValueError("dt must be > 0")
        if self.steps < 100:
            raise ValueError("steps must be ≥ 100 for a usable trajectory")


@dataclass(frozen=True)
class CalibrationMetrics:
    """Machine-readable result ledger for one regime."""

    regime: str
    frobenius_rel_error: float
    topology_f1: float
    omega_rel_error: float
    critical_coupling_rel_error: float
    n_nodes: int
    n_true_edges: int
    n_recovered_edges: int
    s_crit_true: float
    s_crit_hat: float
    coupling_condition_number: float
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable view (sorted keys downstream)."""
        return {
            "regime": self.regime,
            "frobenius_rel_error": self.frobenius_rel_error,
            "topology_f1": self.topology_f1,
            "omega_rel_error": self.omega_rel_error,
            "critical_coupling_rel_error": self.critical_coupling_rel_error,
            "n_nodes": self.n_nodes,
            "n_true_edges": self.n_true_edges,
            "n_recovered_edges": self.n_recovered_edges,
            "s_crit_true": self.s_crit_true,
            "s_crit_hat": self.s_crit_hat,
            "coupling_condition_number": self.coupling_condition_number,
            "extra": self.extra,
        }


def ground_truth(
    system: GridSystem,
    scale: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    r"""Return the scaled true coupling :math:`s\,K` and true :math:`\omega`.

    The uniform scale ``s`` lifts the published per-unit coupling above
    the Dörfler–Bullo critical scale so the swing model phase-locks (a
    locked trajectory is what the row-regression estimator needs).
    """
    k_true = scale * coupling_from_susceptance(system.susceptance, system.voltage)
    np.fill_diagonal(k_true, 0.0)
    omega_true = natural_frequency_from_injection(system.injection, system.damping)
    return np.asarray(k_true, dtype=np.float64), omega_true


def simulate_phases(
    system: GridSystem,
    k_true: NDArray[np.float64],
    omega_true: NDArray[np.float64],
    cfg: SimConfig,
) -> tuple[PhaseMatrix, NDArray[np.float64]]:
    """Integrate the swing model on ``k_true`` → wrapped ``PhaseMatrix``.

    A pre-registered initial-phase perturbation ``cfg.theta0_perturb``
    displaces the rotor angles off the synchronous equilibrium. The
    *early* damped oscillatory transient that follows is what carries
    the identification signal: a fully phase-locked trajectory has
    ``dθ/dt → const`` and ``sin(θ_j−θ_i) → const``, so the row design
    matrix degenerates (the persistent-excitation condition for
    second-order Kuramoto identification). We therefore keep the first
    ``cfg.keep_frac`` of the trajectory — the excited transient — not a
    post-lock slice. Additive Gaussian measurement noise of std
    ``cfg.noise_sigma`` is applied to the wrapped phase (noisy regime);
    pass ``noise_sigma == 0`` for the noiseless run.
    """
    n = system.n
    rng_ic = np.random.default_rng(cfg.seed)
    theta0 = rng_ic.uniform(-cfg.theta0_perturb, cfg.theta0_perturb, size=n).astype(np.float64)
    theta0 = theta0 - float(np.mean(theta0))
    k_config = KuramotoConfig(
        N=n,
        K=1.0,
        omega=omega_true,
        dt=cfg.dt,
        steps=cfg.steps,
        adjacency=k_true,
        theta0=theta0,
        seed=cfg.seed,
    )
    engine = SecondOrderKuramotoEngine(
        k_config,
        mass=system.inertia,
        damping=system.damping,
    )
    # Epistemic-integrity insulation: the pre-registered ledgers reproduce the
    # frozen experiment by replaying a committed trajectory snapshot, so the
    # byte-frozen artifacts are decoupled from the live (BBK) integrator. A
    # configuration absent from the snapshot falls through to the live engine.
    # See frozen_replay.py.
    key = frozen_replay.trajectory_key(
        system_name=system.name,
        inertia=np.asarray(system.inertia, dtype=np.float64),
        damping=np.asarray(system.damping, dtype=np.float64),
        k_true=np.asarray(k_true, dtype=np.float64),
        omega_true=np.asarray(omega_true, dtype=np.float64),
        dt=cfg.dt,
        steps=cfg.steps,
        seed=cfg.seed,
        theta0_perturb=cfg.theta0_perturb,
    )
    result = frozen_replay.obtain_trajectory(key, engine.run)

    phases = np.asarray(result.phases, dtype=np.float64)
    velocities = np.asarray(result.velocities, dtype=np.float64)
    t_total = phases.shape[0]
    keep = max(2, int(cfg.keep_frac * t_total))
    phases = phases[:keep]
    velocities = velocities[:keep]

    if cfg.noise_sigma > 0.0:
        rng = np.random.default_rng(cfg.seed + 1)
        phases = phases + rng.normal(0.0, cfg.noise_sigma, size=phases.shape)

    wrapped = np.mod(phases, 2.0 * np.pi)
    # Guard the [0, 2π) contract: 2π·(1−eps) maps strictly below 2π.
    # bounds: PhaseMatrix._validate requires max < 2π exactly.
    wrapped = np.clip(wrapped, 0.0, np.nextafter(2.0 * np.pi, 0.0))
    timestamps = np.arange(wrapped.shape[0], dtype=np.float64) * cfg.dt

    pm = PhaseMatrix(
        theta=wrapped,
        timestamps=timestamps,
        asset_ids=system.bus_ids,
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )
    return pm, velocities


def recover_coupling(
    phases: PhaseMatrix,
    cfg: SimConfig,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Run GeoSync's inverse machinery → ``(K_hat, omega_hat)``.

    ``omega_hat`` is the estimator's internal natural-frequency estimate
    (the temporal median of the instantaneous frequency), recomputed
    here from the same unwrap/gradient the estimator uses so the two
    halves of the inverse problem are scored consistently.
    """
    est_cfg = CouplingEstimationConfig(
        penalty=cfg.penalty,
        lambda_reg=cfg.lambda_reg,
        dt=cfg.dt,
        standardize=True,
    )
    estimator = CouplingEstimator(est_cfg)
    coupling = estimator.estimate(phases)
    k_hat = np.asarray(coupling.K, dtype=np.float64)

    theta = np.asarray(phases.theta, dtype=np.float64)
    unwrapped = np.unwrap(theta, axis=0)
    omega_inst = np.gradient(unwrapped, cfg.dt, axis=0)
    omega_hat = np.median(omega_inst, axis=0)
    omega_hat = omega_hat - float(np.mean(omega_hat))
    return k_hat, np.asarray(omega_hat, dtype=np.float64)


def recover_coupling_swing(
    phases: PhaseMatrix,
    system: GridSystem,
    cfg: SimConfig,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    r"""CALIB-GRID-001 R1 — recover ``(K_hat, omega_hat)`` via the swing path.

    Feeds the same frozen trajectory into the second-order identification
    path :func:`core.kuramoto.coupling_estimator.estimate_swing_coupling`.
    The published machine constants (``system.inertia``, ``system.damping``)
    are the *known* swing parameters; coupling and injection are the
    unknowns. ``omega_hat`` is the estimator's own ``ω = P̂ / d``
    (mean-centred to the rotating reference gauge, matching the
    ground-truth convention), so both halves of the inverse problem are
    scored consistently.

    The persistent-excitation guard is active (fail-closed): a
    phase-locked / rank-deficient design raises
    :class:`~core.kuramoto.coupling_estimator.PersistentExcitationError`
    rather than emitting a misleading ``K̂``.

    Two solver choices are *pre-committed on physics grounds* (not by
    inspecting the frozen result, which would be a protocol violation):

    * ``symmetric=True`` — a lossless power-network coupling is
      physically symmetric (PREREGISTRATION § 2).
    * Savitzky–Golay ``window=7, polyorder=4`` — the WSCC-9 / scale-8
      swing response is *over-damped* (the relative rotor angles slew
      monotonically to the locked state with no ringing — verified: no
      zero-crossings of the detrended relative angle). An over-damped
      monotone transient carries no high-frequency content to suppress,
      so the *minimal-smoothing* SG stencil consistent with a degree-4
      local fit (the smallest odd window > polyorder) is the
      least-biased derivative. This is a stencil choice dictated by the
      signal class, the analogue of "use the smallest consistent
      finite-difference stencil", and is fixed independently of the
      gate value.
    """
    est = estimate_swing_coupling(
        phases,
        np.asarray(system.inertia, dtype=np.float64),
        np.asarray(system.damping, dtype=np.float64),
        dt=cfg.dt,
        symmetric=True,
        savgol_window=7,
        savgol_polyorder=4,
        pe_guard=True,
    )
    k_hat = np.asarray(est.K, dtype=np.float64)
    omega_hat = np.asarray(est.omega, dtype=np.float64)
    omega_hat = omega_hat - float(np.mean(omega_hat))
    return k_hat, np.asarray(omega_hat, dtype=np.float64)


def _symmetrise(k: NDArray[np.float64]) -> NDArray[np.float64]:
    """Symmetric part — power-grid coupling is physically symmetric."""
    return np.asarray(0.5 * (k + k.T), dtype=np.float64)


def score_recovery(
    k_true: NDArray[np.float64],
    omega_true: NDArray[np.float64],
    k_hat: NDArray[np.float64],
    omega_hat: NDArray[np.float64],
    regime: str,
    cfg: SimConfig,
) -> CalibrationMetrics:
    """Compute the full pre-registered metric set for one regime.

    The row-regression estimator returns a possibly-asymmetric ``K_hat``
    (it does not impose symmetry). The grid coupling is physically
    symmetric, so the Frobenius / critical-coupling comparison uses the
    symmetric part of ``K_hat`` (documented localisation choice — an
    antisymmetric residual would localise the miss to the estimator's
    symmetry-agnostic row solver, reported in ``extra``).
    """
    k_hat_sym = _symmetrise(k_hat)

    fro_true = float(np.linalg.norm(k_true, ord="fro"))
    fro_err = float(np.linalg.norm(k_hat_sym - k_true, ord="fro"))
    frob_rel = fro_err / fro_true if fro_true > 0.0 else float("inf")

    f1, n_true_edges, n_hat_edges = _topology_f1(k_true, k_hat_sym, cfg.topology_rel_threshold)

    w_norm = float(np.linalg.norm(omega_true))
    omega_rel = (
        float(np.linalg.norm(omega_hat - omega_true)) / w_norm if w_norm > 0.0 else float("inf")
    )

    s_crit_true = dorfler_bullo_critical_coupling(k_true, omega_true)
    try:
        s_crit_hat = dorfler_bullo_critical_coupling(np.abs(k_hat_sym), omega_hat)
    except ValueError:
        # Recovered graph disconnected → infinite critical scale; the
        # miss localises to topology recovery, not the analytic formula.
        s_crit_hat = float("inf")
    s_crit_rel = (
        abs(s_crit_hat - s_crit_true) / s_crit_true
        if np.isfinite(s_crit_hat) and s_crit_true > 0.0
        else float("inf")
    )

    antisym = float(np.linalg.norm(0.5 * (k_hat - k_hat.T), ord="fro"))
    cond = float(np.linalg.cond(k_true + np.eye(k_true.shape[0])))

    return CalibrationMetrics(
        regime=regime,
        frobenius_rel_error=frob_rel,
        topology_f1=f1,
        omega_rel_error=omega_rel,
        critical_coupling_rel_error=s_crit_rel,
        n_nodes=int(k_true.shape[0]),
        n_true_edges=n_true_edges,
        n_recovered_edges=n_hat_edges,
        s_crit_true=s_crit_true,
        s_crit_hat=s_crit_hat,
        coupling_condition_number=cond,
        extra={
            "antisymmetric_residual_fro": antisym,
            "fro_true": fro_true,
            "fro_abs_error": fro_err,
        },
    )


def run_calibration(
    system: GridSystem,
    cfg: SimConfig,
    *,
    noisy: bool,
    estimator_path: str = "first_order",
) -> CalibrationMetrics:
    """End-to-end one-regime calibration: simulate → recover → score.

    ``estimator_path`` selects the inverse machinery:

    * ``"first_order"`` (default) — the frozen CALIB-GRID-001 path
      (``coupling_estimator`` MCP row regression). Unchanged so the
      pre-registered NEGATIVE artifact and its tests stay bit-stable.
    * ``"swing"`` — the CALIB-GRID-001 R1 second-order identification
      path (:func:`recover_coupling_swing`). Estimator-only change; the
      simulation, seeds, σ, θ₀ perturbation and gates are identical.
    """
    if estimator_path not in ("first_order", "swing"):
        raise ValueError(f"estimator_path must be 'first_order' or 'swing'; got {estimator_path!r}")
    regime = "noisy" if noisy else "noiseless"
    run_cfg = cfg if noisy else replace(cfg, noise_sigma=0.0)
    k_true, omega_true = ground_truth(system, run_cfg.coupling_scale)
    phases, _ = simulate_phases(system, k_true, omega_true, run_cfg)
    if estimator_path == "swing":
        k_hat, omega_hat = recover_coupling_swing(phases, system, run_cfg)
    else:
        k_hat, omega_hat = recover_coupling(phases, run_cfg)
    return score_recovery(k_true, omega_true, k_hat, omega_hat, regime, run_cfg)
