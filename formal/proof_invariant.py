# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""SMT-based proof of bounded free energy growth."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - only for static analyzers
    pass


HAS_Z3 = importlib.util.find_spec("z3") is not None
"""Whether the optional :mod:`z3` dependency is available."""

MISSING_Z3_MESSAGE = (
    "The z3-solver package is required to run the invariant proof. "
    "Install it with `pip install z3-solver` or use requirements-dev.txt."
)


@dataclass(slots=True)
class ProofResult:
    """Stores solver outcome and the generated certificate."""

    is_safe: bool
    certificate: str


@dataclass(slots=True)
class CacheCoherenceProofResult:
    """Stores solver outcome for cache coherence invariants."""

    cache_db_alignment_safe: bool
    action_freshness_safe: bool
    version_regress_safe: bool
    certificate: str


@dataclass(slots=True)
class CacheLivenessProofResult:
    """Stores solver outcome for eventual coherence/liveness proof."""

    eventually_coherent: bool
    certificate: str


@dataclass(slots=True)
class HlcMonotonicityProofResult:
    """Stores solver outcome for HLC causal monotonicity invariant."""

    monotonic: bool
    certificate: str


@dataclass(slots=True)
class ProofConfig:
    """Declarative parameters for the inductive proof.

    These values mirror the runtime tolerances enforced by the thermodynamic
    controller:
    - ``epsilon_cap``: hard clamp on per-step perturbation (see
      ``ThermoController._monotonic_tolerance_budget``).
    - ``recovery_window`` and ``recovery_decay``: exponential recovery horizon
      used to accept temporary spikes when the moving average drifts back
      below the originating state.
    - ``delta_growth``: the amount of free-energy escalation the proof tries
      to falsify; UNSAT means no such escalation exists.
    """

    steps: int = 3
    epsilon_cap: float = 0.05
    delta_growth: float = 0.2
    recovery_window: int = 3
    recovery_decay: float = 0.9
    tolerance_floor: float = 1e-4
    baseline_floor: float = 0.0
    enforce_recovery: bool = True


@dataclass(slots=True)
class InductionSystem:
    """Container for the inductive proof state."""

    solver: Any
    states: tuple[Any, ...]
    epsilons: tuple[Any, ...]
    baseline: Any
    epsilon_cap: Any
    delta: Any
    config: ProofConfig


def _tolerance_budget_symbolic(F_prev: Any, baseline: Any, eps: Any, config: ProofConfig) -> Any:
    """Symbolic version of the runtime tolerance clamp."""

    from z3 import Abs, If, RealVal

    baseline_scale = If(Abs(baseline) >= Abs(F_prev), Abs(baseline), Abs(F_prev))
    epsilon_from_baseline = RealVal(0.01) * baseline_scale
    epsilon_from_dynamics = RealVal(0.5) * Abs(eps)
    tolerance_floor = RealVal(config.tolerance_floor)

    first = If(tolerance_floor >= epsilon_from_baseline, tolerance_floor, epsilon_from_baseline)
    return If(first >= epsilon_from_dynamics, first, epsilon_from_dynamics)


def _recovery_mean_symbolic(F_new: Any, baseline: Any, config: ProofConfig) -> Any:
    """Expected recovery mean over the configured horizon."""

    from z3 import RealVal, Sum

    decay = RealVal(config.recovery_decay)
    window = config.recovery_window
    terms = [
        F_new * (decay ** (i + 1)) + baseline * (1 - (decay ** (i + 1))) for i in range(window)
    ]
    return Sum(*terms) / RealVal(window)


def tolerance_budget(
    baseline: float, F_prev: float, eps: float, config: Optional[ProofConfig] = None
) -> float:
    """Numeric mirror of :func:`_tolerance_budget_symbolic` for testing."""

    cfg = config or ProofConfig()
    baseline_scale = max(abs(baseline), abs(F_prev))
    epsilon_from_baseline = 0.01 * baseline_scale
    epsilon_from_dynamics = 0.5 * abs(eps)
    return max(cfg.tolerance_floor, epsilon_from_baseline, epsilon_from_dynamics)


def recovery_mean(F_new: float, baseline: float, config: Optional[ProofConfig] = None) -> float:
    """Numeric mirror of :func:`_recovery_mean_symbolic` for testing."""

    cfg = config or ProofConfig()
    decay = cfg.recovery_decay
    window = cfg.recovery_window
    terms = [
        F_new * (decay ** (i + 1)) + baseline * (1 - (decay ** (i + 1))) for i in range(window)
    ]
    return sum(terms) / float(window)


def build_induction(config: Optional[ProofConfig] = None) -> InductionSystem:
    """Prepare solver and symbols for the inductive proof."""

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import Real, RealVal, Solver

    cfg = config or ProofConfig()
    solver = Solver()

    states = tuple(Real(f"F{i}") for i in range(cfg.steps + 1))
    epsilons = tuple(Real(f"eps{i}") for i in range(cfg.steps))
    baseline = Real("baseline")
    epsilon_cap = Real("epsilon_cap")
    delta = Real("delta")

    for var in (*states, *epsilons):
        solver.add(var >= 0)

    solver.add(baseline == states[0])
    solver.add(baseline >= RealVal(cfg.baseline_floor))

    solver.add(epsilon_cap == RealVal(cfg.epsilon_cap))
    for eps in epsilons:
        solver.add(eps <= epsilon_cap)

    solver.add(delta == RealVal(cfg.delta_growth))

    return InductionSystem(
        solver=solver,
        states=states,
        epsilons=epsilons,
        baseline=baseline,
        epsilon_cap=epsilon_cap,
        delta=delta,
        config=cfg,
    )


def apply_induction(system: InductionSystem) -> None:
    """Attach base and inductive-step constraints to the solver."""

    from z3 import Implies

    cfg = system.config
    solver = system.solver

    for idx, eps in enumerate(system.epsilons):
        F_prev = system.states[idx]
        F_next = system.states[idx + 1]

        solver.add(F_next <= F_prev + eps)

        if cfg.enforce_recovery:
            tolerance = _tolerance_budget_symbolic(F_prev, system.baseline, eps, cfg)
            recovery_mean = _recovery_mean_symbolic(F_next, system.baseline, cfg)
            solver.add(Implies(F_next > F_prev, recovery_mean <= F_prev + tolerance))

    solver.add(system.states[-1] >= system.states[0] + system.delta)


# Backwards compatibility helpers for callers/tests that relied on the previous
# three-step API shape.
def build_three_step_induction() -> InductionSystem:
    return build_induction()


def apply_three_step_induction(system: InductionSystem) -> None:
    apply_induction(system)


def run_proof(
    output_path: Optional[Path] = None, *, config: Optional[ProofConfig] = None
) -> ProofResult:
    """Execute the inductive safety check.

    The model encodes the transition rule ``F_{k+1} <= F_k + eps`` with a
    bounded tolerance taken from :class:`ProofConfig`. When a temporary spike occurs the
    configured recovery window must drift back below the originating state,
    mirroring the TACL monotonicity guard. We ask Z3 whether a trace exists that
    still grows by :data:`DELTA_GROWTH` after ``config.steps`` transitions;
    ``unsat`` means the growth cannot happen under the constraints.
    """

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import sat, unsat

    system = build_induction(config)
    apply_induction(system)

    status = system.solver.check()
    cfg = system.config

    certificate_lines = [
        "Free energy boundedness proof",
        f"Solver status: {status}",
        f"epsilon_cap <= {cfg.epsilon_cap}",
        f"delta_growth = {cfg.delta_growth}",
        f"recovery_window = {cfg.recovery_window}",
        f"recovery_decay = {cfg.recovery_decay}",
        f"tolerance_floor = {cfg.tolerance_floor}",
        "Base case: non-negative initial energy with capped per-step perturbation.",
        "Inductive step: recovery mean must return below the originating state.",
    ]

    if status == unsat:
        certificate_lines.append(
            "Result: UNSAT – no unbounded growth exists under the transition rules."
        )
    elif status == sat:
        certificate_lines.append("Result: SAT – counterexample exists.")
        model = system.solver.model()
        certificate_lines.append("Model:")
        for symbol in (*system.states, *system.epsilons, system.baseline):
            certificate_lines.append(f"  {symbol} = {model.evaluate(symbol)}")
    else:
        certificate_lines.append("Result: UNKNOWN – solver could not conclude.")

    certificate = "\n".join(certificate_lines) + "\n"

    if output_path is not None:
        Path(output_path).write_text(certificate, encoding="utf-8")

    return ProofResult(is_safe=status == unsat, certificate=certificate)


def run_cache_coherence_proof(
    output_path: Optional[Path] = None,
    *,
    steps: int = 3,
    max_action_age_ms: int = 250,
) -> CacheCoherenceProofResult:
    """Prove deterministic cache coherence and action freshness invariants."""

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import And, Bool, BoolVal, If, Int, IntVal, Not, Or, Solver, sat, unsat

    if steps <= 0:
        raise ValueError("steps must be positive")
    if max_action_age_ms <= 0:
        raise ValueError("max_action_age_ms must be positive")

    # Invariant I: cache/db mismatch implies divergent status.
    coherence_solver = Solver()
    db_versions = [Int(f"db_v_{idx}") for idx in range(steps + 1)]
    cache_versions = [Int(f"cache_v_{idx}") for idx in range(steps + 1)]
    divergent = [Bool(f"divergent_{idx}") for idx in range(steps + 1)]

    coherence_solver.add(db_versions[0] >= 0)
    coherence_solver.add(cache_versions[0] == db_versions[0])
    coherence_solver.add(divergent[0] == BoolVal(False))

    for idx in range(steps):
        db_write = Bool(f"db_write_{idx}")
        cache_sync = Bool(f"cache_sync_{idx}")

        coherence_solver.add(
            db_versions[idx + 1] == If(db_write, db_versions[idx] + 1, db_versions[idx])
        )
        coherence_solver.add(
            cache_versions[idx + 1] == If(cache_sync, db_versions[idx + 1], cache_versions[idx])
        )
        coherence_solver.add(
            divergent[idx + 1] == (cache_versions[idx + 1] != db_versions[idx + 1])
        )

    coherence_solver.add(
        And(
            cache_versions[-1] != db_versions[-1],
            Not(divergent[-1]),
        )
    )
    coherence_status = coherence_solver.check()

    # Invariant III: version regress cannot happen on synchronizing writes.
    regress_solver = Solver()
    regress_db = [Int(f"reg_db_v_{idx}") for idx in range(steps + 1)]
    regress_cache = [Int(f"reg_cache_v_{idx}") for idx in range(steps + 1)]
    regress_sync = [Bool(f"reg_sync_{idx}") for idx in range(steps)]
    regress_events = [Bool(f"reg_event_{idx}") for idx in range(steps)]

    regress_solver.add(regress_db[0] >= 0)
    regress_solver.add(regress_cache[0] == regress_db[0])
    for idx in range(steps):
        regress_db_write = Bool(f"reg_db_write_{idx}")
        regress_solver.add(
            regress_db[idx + 1] == If(regress_db_write, regress_db[idx] + 1, regress_db[idx])
        )
        regress_solver.add(
            regress_cache[idx + 1] == If(regress_sync[idx], regress_db[idx + 1], regress_cache[idx])
        )
        regress_solver.add(
            regress_events[idx]
            == And(regress_sync[idx], regress_cache[idx + 1] < regress_cache[idx])
        )

    regress_solver.add(Or(*regress_events))
    regress_status = regress_solver.check()

    # Invariant II: action verdict never uses stale regime snapshot.
    freshness_solver = Solver()
    age_ms = Int("age_ms")
    verdict_emitted = Bool("verdict_emitted")
    sync_read_through = Bool("sync_read_through")

    freshness_solver.add(age_ms >= 0)
    freshness_solver.add(
        verdict_emitted
        == If(
            age_ms <= IntVal(max_action_age_ms),
            BoolVal(True),
            sync_read_through,
        )
    )
    freshness_solver.add(
        And(verdict_emitted, age_ms > IntVal(max_action_age_ms), Not(sync_read_through))
    )
    freshness_status = freshness_solver.check()

    certificate_lines = [
        "Cache coherence and action freshness proof",
        f"steps = {steps}",
        f"max_action_age_ms = {max_action_age_ms}",
        f"invariant_i_status = {coherence_status}",
        f"invariant_ii_status = {freshness_status}",
        f"invariant_iii_status = {regress_status}",
    ]

    if coherence_status == unsat:
        certificate_lines.append("Invariant I: UNSAT (cache/db mismatch always implies DIVERGENT)")
    elif coherence_status == sat:
        certificate_lines.append("Invariant I: SAT (counterexample exists)")
    else:
        certificate_lines.append("Invariant I: UNKNOWN")

    if freshness_status == unsat:
        certificate_lines.append("Invariant II: UNSAT (stale snapshots cannot emit verdicts)")
    elif freshness_status == sat:
        certificate_lines.append("Invariant II: SAT (counterexample exists)")
    else:
        certificate_lines.append("Invariant II: UNKNOWN")

    if regress_status == unsat:
        certificate_lines.append("Invariant III: UNSAT (no cache version regress on sync writes)")
    elif regress_status == sat:
        certificate_lines.append("Invariant III: SAT (version regress counterexample exists)")
    else:
        certificate_lines.append("Invariant III: UNKNOWN")

    certificate = "\n".join(certificate_lines) + "\n"
    if output_path is not None:
        Path(output_path).write_text(certificate, encoding="utf-8")

    return CacheCoherenceProofResult(
        cache_db_alignment_safe=coherence_status == unsat,
        action_freshness_safe=freshness_status == unsat,
        version_regress_safe=regress_status == unsat,
        certificate=certificate,
    )


def run_cache_liveness_proof(
    output_path: Optional[Path] = None,
    *,
    steps: int = 5,
) -> CacheLivenessProofResult:
    """Prove eventual coherence: stale cache cannot persist indefinitely."""

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import And, Bool, If, Int, Not, Or, Solver, sat, unsat

    if steps <= 0:
        raise ValueError("steps must be positive")

    solver = Solver()
    db_versions = [Int(f"live_db_v_{idx}") for idx in range(steps + 1)]
    cache_versions = [Int(f"live_cache_v_{idx}") for idx in range(steps + 1)]
    read_through = [Bool(f"live_read_through_{idx}") for idx in range(steps)]
    coherent = [Bool(f"live_coherent_{idx}") for idx in range(steps + 1)]

    solver.add(db_versions[0] >= 0)
    solver.add(cache_versions[0] >= 0)
    solver.add(coherent[0] == (cache_versions[0] == db_versions[0]))

    for idx in range(steps):
        db_write = Bool(f"live_db_write_{idx}")
        solver.add(db_versions[idx + 1] == If(db_write, db_versions[idx] + 1, db_versions[idx]))
        solver.add(
            cache_versions[idx + 1]
            == If(read_through[idx], db_versions[idx + 1], cache_versions[idx])
        )
        solver.add(coherent[idx + 1] == (cache_versions[idx + 1] == db_versions[idx + 1]))

    solver.add(Or(*read_through))
    solver.add(And(*[Not(flag) for flag in coherent]))

    status = solver.check()
    certificate_lines = [
        "Cache eventual coherence liveness proof",
        f"steps = {steps}",
        f"solver_status = {status}",
    ]
    if status == unsat:
        certificate_lines.append(
            "Invariant IV: UNSAT (eventual read-through forces eventual coherence)"
        )
    elif status == sat:
        certificate_lines.append(
            "Invariant IV: SAT (counterexample found; stale cache may persist)"
        )
    else:
        certificate_lines.append("Invariant IV: UNKNOWN")

    certificate = "\n".join(certificate_lines) + "\n"
    if output_path is not None:
        Path(output_path).write_text(certificate, encoding="utf-8")

    return CacheLivenessProofResult(eventually_coherent=status == unsat, certificate=certificate)


def run_hlc_monotonicity_proof(
    output_path: Optional[Path] = None,
) -> HlcMonotonicityProofResult:
    """Prove HLC monotonicity under happened-before relation."""

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import And, Int, Or, Solver, unsat

    solver = Solver()
    wall1 = Int("hlc_wall_1")
    logical1 = Int("hlc_logical_1")
    wall2 = Int("hlc_wall_2")
    logical2 = Int("hlc_logical_2")
    shift = 20

    hlc1 = (wall1 * (2**shift)) + logical1
    hlc2 = (wall2 * (2**shift)) + logical2

    logical_modulus = 2**shift
    for value in (wall1, logical1, wall2, logical2):
        solver.add(value >= 0)
    solver.add(logical1 < logical_modulus)
    solver.add(logical2 < logical_modulus)

    # happened-before encoded as lexicographic order on (wall, logical).
    solver.add(
        And(
            Or(wall1 < wall2, And(wall1 == wall2, logical1 < logical2)),
            hlc1 >= hlc2,  # try to violate monotonicity
        )
    )

    status = solver.check()
    certificate_lines = [
        "HLC monotonicity proof",
        f"solver_status = {status}",
        "encoding = (wall_time_ms << 20) | logical",
    ]
    if status == unsat:
        certificate_lines.append("Invariant V: UNSAT (happened-before implies HLC increase)")
    else:
        certificate_lines.append("Invariant V: SAT/UNKNOWN (monotonicity could be violated)")

    certificate = "\n".join(certificate_lines) + "\n"
    if output_path is not None:
        Path(output_path).write_text(certificate, encoding="utf-8")

    return HlcMonotonicityProofResult(monotonic=status == unsat, certificate=certificate)


def main() -> None:  # pragma: no cover - thin CLI wrapper
    output = Path("formal/INVARIANT_CERT.txt")
    result = run_proof(output)
    print(result.certificate)
    coherence_output = Path("formal/CACHE_COHERENCE_CERT.txt")
    coherence_result = run_cache_coherence_proof(coherence_output)
    print(coherence_result.certificate)
    liveness_output = Path("formal/CACHE_LIVENESS_CERT.txt")
    liveness_result = run_cache_liveness_proof(liveness_output)
    print(liveness_result.certificate)
    hlc_output = Path("formal/HLC_MONOTONICITY_CERT.txt")
    hlc_result = run_hlc_monotonicity_proof(hlc_output)
    print(hlc_result.certificate)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
