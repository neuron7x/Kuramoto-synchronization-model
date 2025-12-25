"""Generic inductive proof engine backed by Z3.

This module centralizes mathematical induction checks so that individual
components (protocol verifiers, cryptographic proofs, etc.) can supply
their base case and inductive step predicates without duplicating solver
configuration logic.
"""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

HAS_Z3 = importlib.util.find_spec("z3") is not None
MISSING_Z3_MESSAGE = (
    "The z3-solver package is required for inductive proofs. "
    "Install it with `pip install z3-solver`."
)


@dataclass(slots=True)
class InductiveProofResult:
    """Outcome of an inductive proof."""

    base_case_unsat: bool
    inductive_step_unsat: bool
    certificate: str
    total_time_ms: float

    @property
    def proved(self) -> bool:
        """Return True if both base and inductive step were proved."""
        return self.base_case_unsat and self.inductive_step_unsat


class InductiveProofEngine:
    """Standardized engine for Z3-backed mathematical induction."""

    def __init__(self, timeout_ms: int = 30000, z3_module: Any | None = None) -> None:
        if not HAS_Z3:
            raise RuntimeError(MISSING_Z3_MESSAGE)

        self.timeout_ms = timeout_ms

        if z3_module is None:
            import z3

            self._z3 = z3
        else:
            self._z3 = z3_module

    def _create_solver(self):
        solver = self._z3.Solver()
        solver.set("timeout", self.timeout_ms)
        return solver

    def _normalize(self, constraints: Any) -> list[Any]:
        if isinstance(constraints, self._z3.BoolRef):
            return [constraints]
        if isinstance(constraints, Iterable) and not isinstance(
            constraints, (str, bytes)
        ):
            return list(constraints)
        raise TypeError(
            "Inductive predicates must return a Z3 Boolean constraint or an iterable of such constraints"
        )

    def prove(
        self,
        base_case_predicate: Callable[[Any], Any],
        inductive_step_predicate: Callable[[Any], Any],
    ) -> InductiveProofResult:
        """Run base and inductive-step proofs.

        The predicates should return constraints encoding the counterexample
        to the desired property. An ``unsat`` result indicates the property
        holds for that phase (base or inductive step).
        """

        start = time.perf_counter()

        base_solver = self._create_solver()
        base_solver.add(*self._normalize(base_case_predicate(self._z3)))
        base_status = base_solver.check()
        base_unsat = base_status == self._z3.unsat

        step_solver = self._create_solver()
        step_solver.add(*self._normalize(inductive_step_predicate(self._z3)))
        step_status = step_solver.check()
        step_unsat = step_status == self._z3.unsat

        total_time_ms = (time.perf_counter() - start) * 1000

        certificate_lines = [
            "Inductive proof",
            f"Base case: {base_status}",
            f"Inductive step: {step_status}",
            f"Total time: {total_time_ms:.2f}ms",
        ]

        certificate = "\n".join(certificate_lines)

        return InductiveProofResult(
            base_case_unsat=base_unsat,
            inductive_step_unsat=step_unsat,
            certificate=certificate,
            total_time_ms=total_time_ms,
        )


__all__ = ["InductiveProofEngine", "InductiveProofResult", "HAS_Z3", "MISSING_Z3_MESSAGE"]
