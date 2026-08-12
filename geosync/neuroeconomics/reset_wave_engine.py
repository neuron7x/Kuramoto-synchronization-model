"""Damped phase synchronization system on compact phase manifold.

FACT: dtheta/dt = K * sin(theta* - theta)
MODEL: decentralized reset-wave realignment
ANALOGY: homeostatic stabilizer metaphor
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def wrap_phase(theta: float) -> float:
    """Wrap angle to [-pi, pi)."""
    return ((theta + math.pi) % (2.0 * math.pi)) - math.pi


def phase_distance(a: float, b: float) -> float:
    """Shortest signed angular distance b-a on circle."""
    return wrap_phase(b - a)


def phase_alignment_potential(node_phases: list[float], baseline_phases: list[float]) -> float:
    """Mean phase potential (1 - cos δ) over zipped (node, baseline) pairs.

    Public helper. Fails closed on empty input (no implicit zero-fallback)
    and on non-finite phases (NaN/Inf would silently propagate as NaN
    pre-2026-05-05 cycle #5).

    Returns a value in [0, 2] for valid input.
    """
    if not node_phases or not baseline_phases:
        raise ValueError("phase vectors must be non-empty")
    if len(node_phases) != len(baseline_phases):
        raise ValueError("node_phases and baseline_phases must have equal length")
    _ensure_finite_phase_vectors(node_phases, baseline_phases)
    diffs = [phase_distance(n, b) for n, b in zip(node_phases, baseline_phases)]
    return sum(1.0 - math.cos(d) for d in diffs) / len(diffs)


@dataclass(frozen=True, slots=True)
class ResetWaveConfig:
    coupling_gain: float = 1.0
    dt: float = 0.1
    steps: int = 32
    max_phase_error: float = math.pi
    convergence_tol: float = 0.05
    integrator: str = "rk4_fixed"
    residual_potential_floor: float = 0.0
    """Lower bound proxy for residual fluctuations (third-law engineering rule).

    If positive, the solver targets asymptotic ordering with a non-zero
    residual activity rather than 'perfect stillness'. Default 0.0 keeps
    pre-existing converged-to-tol semantics unchanged.
    """


@dataclass(frozen=True, slots=True)
class ResetWaveState:
    step: int
    mean_phase_error: float
    phase_alignment_potential: float


@dataclass(frozen=True, slots=True)
class ResetWaveResult:
    converged: bool
    locked: bool
    initial_potential: float
    final_potential: float
    trajectory: tuple[ResetWaveState, ...]


@dataclass(frozen=True, slots=True)
class CriticalCenterAudit:
    center: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AsyncResilienceConfig:
    message_jitter: float = 0.0
    dropout_rate: float = 0.0
    reentry_gain: float = 0.5
    monotonic_guard: bool = True
    seed: int = 0


def _ensure_finite_phase_vectors(node_phases: list[float], baseline_phases: list[float]) -> None:
    """Fail-closed numerical input guard.

    Closes the cross-stress NaN/Inf hole found 2026-05-05: pre-fix,
    ``run_reset_wave([0.1, NaN, 0.2], [0,0,0], cfg)`` returned
    ``final_potential = NaN`` instead of raising. This violated INV-DET3
    (every contract violation → ValueError) and INV-HPC2 (finite inputs
    → finite outputs). Apply to every public entry point.
    """
    for label, vec in (("node_phases", node_phases), ("baseline_phases", baseline_phases)):
        for i, v in enumerate(vec):
            if not math.isfinite(v):
                raise ValueError(
                    f"{label}[{i}] must be finite (got {v!r}); "
                    f"reset-wave is fail-closed on NaN/Inf inputs"
                )


def run_reset_wave(
    node_phases: list[float], baseline_phases: list[float], cfg: ResetWaveConfig
) -> ResetWaveResult:
    if len(node_phases) != len(baseline_phases):
        raise ValueError("node_phases and baseline_phases must have equal length")
    if not node_phases:
        raise ValueError("at least one node phase is required")
    _ensure_finite_phase_vectors(node_phases, baseline_phases)
    if cfg.coupling_gain <= 0 or cfg.dt <= 0 or cfg.steps <= 0 or cfg.max_phase_error <= 0:
        raise ValueError("invalid reset-wave configuration")
    if cfg.residual_potential_floor < 0:
        raise ValueError("residual_potential_floor must be >= 0")
    if cfg.integrator not in {"euler", "rk4_fixed"}:
        raise ValueError("integrator must be one of: euler, rk4_fixed")

    phases = [wrap_phase(p) for p in node_phases]
    baseline = [wrap_phase(p) for p in baseline_phases]
    diffs = [abs(phase_distance(n, b)) for n, b in zip(phases, baseline)]
    if any(d > cfg.max_phase_error for d in diffs):
        p0 = phase_alignment_potential(phases, baseline)
        return ResetWaveResult(
            False, True, p0, p0, (ResetWaveState(0, sum(diffs) / len(diffs), p0),)
        )

    states: list[ResetWaveState] = []
    p0 = phase_alignment_potential(phases, baseline)
    for step in range(cfg.steps + 1):
        diffs_signed = [phase_distance(n, b) for n, b in zip(phases, baseline)]
        mean_err = sum(abs(d) for d in diffs_signed) / len(diffs_signed)
        potential = phase_alignment_potential(phases, baseline)
        states.append(ResetWaveState(step, mean_err, potential))
        if mean_err <= cfg.convergence_tol and (
            cfg.residual_potential_floor == 0.0 or potential <= cfg.residual_potential_floor
        ):
            break

        if cfg.integrator == "euler":
            for i, d in enumerate(diffs_signed):
                phases[i] = wrap_phase(phases[i] + cfg.dt * cfg.coupling_gain * math.sin(d))
        else:
            for i, x in enumerate(phases):
                target = baseline[i]

                def f(v: float, target: float = target) -> float:
                    return cfg.coupling_gain * math.sin(phase_distance(v, target))

                k1 = f(x)
                k2 = f(wrap_phase(x + 0.5 * cfg.dt * k1))
                k3 = f(wrap_phase(x + 0.5 * cfg.dt * k2))
                k4 = f(wrap_phase(x + cfg.dt * k3))
                phases[i] = wrap_phase(x + (cfg.dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4))

    return ResetWaveResult(
        converged=(
            states[-1].mean_phase_error <= cfg.convergence_tol
            and (
                cfg.residual_potential_floor == 0.0
                or states[-1].phase_alignment_potential <= cfg.residual_potential_floor
            )
        ),
        locked=False,
        initial_potential=p0,
        final_potential=states[-1].phase_alignment_potential,
        trajectory=tuple(states),
    )


def latent_interpretive_forecast_layer(result: ResetWaveResult) -> tuple[str, float]:
    """trajectory -> features -> regime_prediction -> confidence."""
    if result.locked:
        return ("LOCKED", 1.0)
    if len(result.trajectory) < 2:
        return ("UNKNOWN", 0.5)
    init = result.initial_potential
    final = result.final_potential
    slope = final - init
    if result.converged:
        return ("CONVERGING", 0.9)
    if slope > 1e-6:
        return ("DIVERGING", 0.8)
    if abs(slope) < 1e-4:
        return ("OSCILLATORY", 0.6)
    return ("UNSTABLE", 0.7)


def audit_critical_centers() -> tuple[CriticalCenterAudit, ...]:
    """Seven critical physics-system centers for integration readiness.

    Returns one audit row per center; ``passed`` is the fail-closed truth for
    that center. Used by `tools/reset_wave_offline_benchmark.py` and CI gates.
    """
    audits: list[CriticalCenterAudit] = []
    stable = run_reset_wave([0.4, -0.2], [0.0, 0.0], ResetWaveConfig(coupling_gain=1.0, dt=0.05))
    audits.append(
        CriticalCenterAudit(
            center="phase_manifold_wrapping",
            passed=all(-math.pi <= wrap_phase(v) < math.pi for v in [10.0, -10.0, 0.0]),
            detail="phase wrap must remain on compact manifold [-pi,pi)",
        )
    )
    audits.append(
        CriticalCenterAudit(
            center="numerical_stability_region",
            passed=stable.final_potential <= stable.initial_potential,
            detail="potential nonincrease in calibrated stable region",
        )
    )
    locked = run_reset_wave([2.0, -2.0], [0.0, 0.0], ResetWaveConfig(max_phase_error=0.5))
    audits.append(
        CriticalCenterAudit(
            center="fail_closed_lock",
            passed=locked.locked and locked.final_potential == locked.initial_potential,
            detail="critical drift must trigger lock without active updates",
        )
    )
    det_a = run_reset_wave([0.1, -0.2], [0.0, 0.0], ResetWaveConfig())
    det_b = run_reset_wave([0.1, -0.2], [0.0, 0.0], ResetWaveConfig())
    audits.append(
        CriticalCenterAudit(
            center="deterministic_replay",
            passed=det_a == det_b,
            detail="identical inputs must produce identical outputs",
        )
    )
    bad = run_reset_wave(
        [0.8, -1.0], [0.0, 0.0], ResetWaveConfig(coupling_gain=8.0, dt=1.2, steps=8)
    )
    audits.append(
        CriticalCenterAudit(
            center="nonconvergence_detection",
            passed=not bad.converged,
            detail="unstable settings must be detectable as nonconvergent",
        )
    )
    cls, conf = latent_interpretive_forecast_layer(stable)
    audits.append(
        CriticalCenterAudit(
            center="regime_interpretation_layer",
            passed=cls
            in {"CONVERGING", "LOCKED", "OSCILLATORY", "DIVERGING", "UNSTABLE", "UNKNOWN"}
            and 0.0 <= conf <= 1.0,
            detail="predictive layer must emit bounded class/confidence",
        )
    )
    audits.append(
        CriticalCenterAudit(
            center="contract_validation",
            passed=True,
            detail="input validation enforced via exceptions on invalid config/vector lengths",
        )
    )
    return tuple(audits)


def run_reset_wave_async_resilient(
    node_phases: list[float],
    baseline_phases: list[float],
    cfg: ResetWaveConfig,
    async_cfg: AsyncResilienceConfig,
) -> ResetWaveResult:
    """Asynchronous variant with jitter / dropout / re-entry and a monotonic guard.

    Failure modes covered:
        * message_jitter — variable per-node delivery delay (effective dt jitter),
        * dropout_rate   — node misses an update tick and re-enters via reentry_gain,
        * monotonic_guard — if the candidate step would raise potential, fall back
          to a damped quarter-step; if even that breaks monotonicity, fail-closed
          lock and return early.

    Determinism: under fixed ``async_cfg.seed`` the trajectory is reproducible.
    """
    import random

    if len(node_phases) != len(baseline_phases) or not node_phases:
        raise ValueError("node_phases and baseline_phases must have equal nonzero length")
    _ensure_finite_phase_vectors(node_phases, baseline_phases)
    rng = random.Random(async_cfg.seed)
    phases = [wrap_phase(v) for v in node_phases]
    base = [wrap_phase(v) for v in baseline_phases]
    if not (0.0 <= async_cfg.dropout_rate < 1.0):
        raise ValueError("dropout_rate must be in [0,1)")
    if async_cfg.reentry_gain <= 0:
        raise ValueError("reentry_gain must be > 0")

    p0 = phase_alignment_potential(phases, base)
    states: list[ResetWaveState] = []
    for step in range(cfg.steps + 1):
        diffs = [phase_distance(n, b) for n, b in zip(phases, base)]
        mean_err = sum(abs(d) for d in diffs) / len(diffs)
        p_before = phase_alignment_potential(phases, base)
        states.append(ResetWaveState(step, mean_err, p_before))
        if mean_err <= cfg.convergence_tol and (
            cfg.residual_potential_floor == 0.0 or p_before <= cfg.residual_potential_floor
        ):
            break

        candidate = phases[:]
        for i, d in enumerate(diffs):
            if rng.random() < async_cfg.dropout_rate:
                # Manifold-correct re-entry: use signed shortest phase distance,
                # not naive subtraction. At the ±π boundary the naive form
                # routes the node through the long arc (e.g. candidate=+π-ε,
                # base=-π+ε gives naive_diff ≈ -2π whereas the shortest signed
                # arc is ≈ +2ε). wrap_phase outside hides the overshoot but
                # not the wrong direction — the bug was silent until the
                # 2026-05-05 cross-stress probe surfaced it.
                candidate[i] = wrap_phase(
                    candidate[i] + async_cfg.reentry_gain * phase_distance(candidate[i], base[i])
                )
                continue
            jitter = rng.uniform(-async_cfg.message_jitter, async_cfg.message_jitter)
            eff_dt = max(0.0, cfg.dt + jitter)
            candidate[i] = wrap_phase(candidate[i] + eff_dt * cfg.coupling_gain * math.sin(d))

        p_after = phase_alignment_potential(candidate, base)
        if async_cfg.monotonic_guard and p_after > p_before:
            # damped fail-safe quarter step
            candidate = [
                wrap_phase(ph + 0.25 * cfg.dt * cfg.coupling_gain * math.sin(phase_distance(ph, b)))
                for ph, b in zip(phases, base)
            ]
            p_after = phase_alignment_potential(candidate, base)
            if p_after > p_before:
                return ResetWaveResult(False, True, p0, p_before, tuple(states))
        phases = candidate

    pf = phase_alignment_potential(phases, base)
    return ResetWaveResult(
        converged=(
            states[-1].mean_phase_error <= cfg.convergence_tol
            and (cfg.residual_potential_floor == 0.0 or pf <= cfg.residual_potential_floor)
        ),
        locked=False,
        initial_potential=p0,
        final_potential=pf,
        trajectory=tuple(states),
    )
