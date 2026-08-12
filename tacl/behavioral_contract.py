# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral contract enforcement for the TACL energy model.

The controller driving GeoSync automation must never drift outside of the
mandate granted by human operators.  In practice this means three invariants:

* Free energy must keep trending down (Monotonic Free Energy Descent).
* Energy must remain inside the admissible envelope bounded by a rest
  potential (the stabilised baseline) and an action potential (the maximum
  tolerable stress before the external kill-switch fires).
* Any override requires dual approval from explicitly authorised roles.

This module provides an ergonomic way to express and enforce those
constraints.  It layers on top of :class:`~tacl.energy_model.EnergyModel`
metrics without modifying the core thermodynamic equations which keeps the
implementation auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .energy_model import EnergyValidationResult


@dataclass(frozen=True, slots=True)
class ContractBreach:
    """Structured description of a behavioural contract violation."""

    kind: str
    sample_index: int
    free_energy: float
    bound: float
    message: str


@dataclass(frozen=True, slots=True)
class BehavioralContractReport:
    """Summary of an enforcement pass for audit trails."""

    compliant: bool
    approvals: frozenset[str]
    breaches: tuple[ContractBreach, ...]
    overrides_applied: bool
    kill_switch_authority: str


class BehavioralContractViolation(RuntimeError):
    """Raised when the behavioural contract cannot be satisfied."""

    def __init__(self, message: str, report: BehavioralContractReport) -> None:
        super().__init__(message)
        self.report = report


@dataclass(slots=True)
class BehavioralContract:
    """Enforce monotonic descent and safe operating bounds for free energy."""

    rest_potential: float = 1.0
    action_potential: float = 1.35
    monotonic_tolerance: float = 5e-3
    required_approvals: frozenset[str] = frozenset({"operations", "safety"})
    kill_switch_authority: str = "external"

    def __post_init__(self) -> None:
        if self.action_potential <= self.rest_potential:
            raise ValueError("action_potential must exceed rest_potential")
        if self.monotonic_tolerance < 0:
            raise ValueError("monotonic_tolerance must be non-negative")
        if not isinstance(self.required_approvals, frozenset):
            self.required_approvals = frozenset(self.required_approvals)

    def enforce(
        self,
        results: Sequence[EnergyValidationResult] | Iterable[EnergyValidationResult],
        *,
        approvals: Iterable[str] | None = None,
    ) -> BehavioralContractReport:
        """Evaluate a sequence of validation results against the contract."""

        approvals_set = frozenset(approvals or ())
        timeline = tuple(results)
        breaches: list[ContractBreach] = []
        previous_energy: float | None = None

        for index, result in enumerate(timeline):
            energy = float(result.free_energy)

            if energy < self.rest_potential - self.monotonic_tolerance:
                breaches.append(
                    ContractBreach(
                        kind="rest_potential",
                        sample_index=index,
                        free_energy=energy,
                        bound=self.rest_potential,
                        message=(
                            "free energy dropped below rest potential "
                            f"({energy:.6f} < {self.rest_potential:.6f})"
                        ),
                    )
                )

            if energy > self.action_potential + self.monotonic_tolerance:
                breaches.append(
                    ContractBreach(
                        kind="action_potential",
                        sample_index=index,
                        free_energy=energy,
                        bound=self.action_potential,
                        message=(
                            "free energy exceeded action potential "
                            f"({energy:.6f} > {self.action_potential:.6f})"
                        ),
                    )
                )

            if previous_energy is not None and energy - previous_energy > self.monotonic_tolerance:
                breaches.append(
                    ContractBreach(
                        kind="monotonicity",
                        sample_index=index,
                        free_energy=energy,
                        bound=previous_energy,
                        message=(
                            "free energy increased despite monotonic contract "
                            f"({previous_energy:.6f} -> {energy:.6f})"
                        ),
                    )
                )

            previous_energy = energy

        compliant = not breaches
        overrides_applied = bool(breaches) and self.required_approvals.issubset(approvals_set)

        report = BehavioralContractReport(
            compliant=compliant,
            approvals=approvals_set,
            breaches=tuple(breaches),
            overrides_applied=overrides_applied,
            kill_switch_authority=self.kill_switch_authority,
        )

        if breaches and not overrides_applied:
            first = breaches[0]
            raise BehavioralContractViolation(
                (
                    f"Behavioural contract breached ({first.kind}); "
                    f"kill-switch authority {self.kill_switch_authority} must be engaged"
                ),
                report,
            )

        return report


__all__ = [
    "BehavioralContract",
    "BehavioralContractReport",
    "BehavioralContractViolation",
    "ContractBreach",
]
