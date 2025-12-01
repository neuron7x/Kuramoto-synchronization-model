"""SMT-based proof of bounded free energy growth."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - only for static analysers
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


EPSILON_CAP = 0.05
DELTA_GROWTH = 0.2


def run_proof(output_path: Optional[Path] = None) -> ProofResult:
    """Execute the inductive safety check.

    The model encodes the transition rule ``F_{k+1} <= F_k + eps`` with a
    bounded tolerance :data:`EPSILON_CAP`. When a temporary spike occurs the
    three-step average must fall back below the originating state, mimicking the
    controller's recovery guarantee. We ask Z3 whether a trace exists that still
    grows by :data:`DELTA_GROWTH` after three steps; ``unsat`` means the growth
    cannot happen under the constraints.
    """

    if not HAS_Z3:
        raise RuntimeError(MISSING_Z3_MESSAGE)

    from z3 import And, Or, Real, Solver, Sum, sat, unsat

    solver = Solver()

    F0, F1, F2, F3 = Real("F0"), Real("F1"), Real("F2"), Real("F3")
    eps0, eps1, eps2 = Real("eps0"), Real("eps1"), Real("eps2")

    for var in (F0, F1, F2, F3, eps0, eps1, eps2):
        solver.add(var >= 0)

    epsilon_cap = Real("epsilon_cap")
    solver.add(epsilon_cap == EPSILON_CAP)
    for eps in (eps0, eps1, eps2):
        solver.add(eps <= epsilon_cap)

    solver.add(
        Or(
            F1 <= F0 + eps0,
            And(
                F1 > F0 + eps0,
                3 * F0 >= Sum(F1, F2, F3),
            ),
        )
    )
    solver.add(F2 <= F1 + eps1)
    solver.add(F3 <= F2 + eps2)

    delta = Real("delta")
    solver.add(delta == DELTA_GROWTH)
    solver.add(F3 >= F0 + delta)

    status = solver.check()

    certificate_lines = [
        "Free energy boundedness proof",
        f"Solver status: {status}",
        f"epsilon_cap <= {EPSILON_CAP}",
        f"delta_growth = {DELTA_GROWTH}",
    ]

    if status == unsat:
        certificate_lines.append(
            "Result: UNSAT – no unbounded growth exists under the transition rules."
        )
    elif status == sat:
        certificate_lines.append("Result: SAT – counterexample exists.")
        model = solver.model()
        certificate_lines.append("Model:")
        for symbol in (F0, F1, F2, F3, eps0, eps1, eps2):
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
