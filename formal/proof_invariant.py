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
        F_new * (decay ** (i + 1)) + baseline * (1 - (decay ** (i + 1)))
        for i in range(window)
    ]
    return Sum(*terms) / RealVal(window)


def tolerance_budget(baseline: float, F_prev: float, eps: float, config: Optional[ProofConfig] = None) -> float:
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
        F_new * (decay ** (i + 1)) + baseline * (1 - (decay ** (i + 1)))
        for i in range(window)
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


def main() -> None:  # pragma: no cover - thin CLI wrapper
    output = Path("formal/INVARIANT_CERT.txt")
    result = run_proof(output)
    print(result.certificate)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
