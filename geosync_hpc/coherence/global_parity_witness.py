# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Global parity witness — engineering analog of Kitaev-readout discipline.

pattern_id:        P4_GLOBAL_PARITY_WITNESS
source_id:         S4_KITAEV_PARITY_READOUT
claim_tier:        ENGINEERING_ANALOG

Local probes cannot decide a global property: required global surfaces
(claim ledger, dependency truth, invariant coverage, CI gate) must
independently agree. The named lie blocked here is "local pass = global
pass". The witness is a pure AND-aggregation; there is no numeric
score, no confidence float, no percent.

Status priority (first failing surface wins): LOCAL_FAILURE >
CLAIM_LEDGER_FAILURE > DEPENDENCY_TRUTH_FAILURE >
INVARIANT_COVERAGE_FAILURE > CI_GATE_FAILURE > CI_GATE_UNKNOWN >
GLOBAL_PASS. ``failed_surfaces`` is locals (sorted, ``local:`` prefix)
then globals in canonical order.

Non-claims: no one-to-one correspondence with quantum-parity physics;
GLOBAL_PASS is not a forecast or trading signal; the witness is exactly
the AND-aggregation of declared surfaces.

Determinism: ``assess_global_parity`` is pure. No I/O, no clock, no
random, no module-level mutable state. Identical inputs produce
byte-identical witnesses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

__all__ = [
    "GlobalParityStatus",
    "LocalWitness",
    "GlobalParityInput",
    "GlobalParityWitness",
    "assess_global_parity",
]


_SURFACE_CLAIM_LEDGER = "claim_ledger"
_SURFACE_DEPENDENCY_TRUTH = "dependency_truth"
_SURFACE_INVARIANT_COVERAGE = "invariant_coverage"
_SURFACE_CI_GATE = "ci_gate"

_GLOBAL_SURFACES: tuple[str, ...] = (
    _SURFACE_CLAIM_LEDGER,
    _SURFACE_DEPENDENCY_TRUTH,
    _SURFACE_INVARIANT_COVERAGE,
    _SURFACE_CI_GATE,
)

_VALID_TIERS: frozenset[str] = frozenset(
    {"FACT", "ENGINEERING_ANALOG", "HYPOTHESIS", "SPECULATIVE"}
)


_FALSIFIER_TEXT = (
    "GLOBAL_PASS was returned but at least one of the following held: "
    "any local witness reported passed=False; claim_ledger_ok was False; "
    "dependency_truth_ok was False; invariant_coverage_ok was False; "
    "ci_gate_ok was False or None. OR: a required global surface was "
    "silently ignored by the aggregation. OR: failed_surfaces was "
    "non-deterministic across identical inputs."
)


GlobalParityStatus = Literal[
    "GLOBAL_PASS",
    "LOCAL_FAILURE",
    "CLAIM_LEDGER_FAILURE",
    "DEPENDENCY_TRUTH_FAILURE",
    "INVARIANT_COVERAGE_FAILURE",
    "CI_GATE_UNKNOWN",
    "CI_GATE_FAILURE",
]


@dataclass(frozen=True)
class LocalWitness:
    """One local check entering the global aggregation."""

    name: str
    passed: bool
    tier: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("LocalWitness.name must be a non-empty string")
        if not isinstance(self.passed, bool):
            raise TypeError("LocalWitness.passed must be a bool")
        if not isinstance(self.tier, str) or self.tier not in _VALID_TIERS:
            raise ValueError(
                f"LocalWitness.tier must be one of {sorted(_VALID_TIERS)} (got {self.tier!r})"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("LocalWitness.reason must be a non-empty string")


@dataclass(frozen=True)
class GlobalParityInput:
    """Inputs to one global-parity assessment.

    ``required_surfaces`` declares which canonical globals the caller
    enforces; entries must come from ``canonical_surfaces()``.
    ``ci_gate_ok=None`` is a distinct verdict (CI_GATE_UNKNOWN), not a
    pass.
    """

    local_witnesses: tuple[LocalWitness, ...]
    claim_ledger_ok: bool
    dependency_truth_ok: bool
    invariant_coverage_ok: bool
    ci_gate_ok: bool | None
    required_surfaces: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.local_witnesses, tuple):
            raise TypeError("local_witnesses must be a tuple of LocalWitness")
        if len(self.local_witnesses) == 0:
            raise ValueError("local_witnesses must be non-empty")
        for i, lw in enumerate(self.local_witnesses):
            if not isinstance(lw, LocalWitness):
                raise TypeError(f"local_witnesses[{i}] must be a LocalWitness instance")

        for name, value in (
            ("claim_ledger_ok", self.claim_ledger_ok),
            ("dependency_truth_ok", self.dependency_truth_ok),
            ("invariant_coverage_ok", self.invariant_coverage_ok),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a bool")
        if self.ci_gate_ok is not None and not isinstance(self.ci_gate_ok, bool):
            raise TypeError("ci_gate_ok must be a bool or None")

        if not isinstance(self.required_surfaces, tuple):
            raise TypeError("required_surfaces must be a tuple of strings")
        for s in self.required_surfaces:
            if not isinstance(s, str) or not s.strip():
                raise ValueError("required_surfaces entries must be non-empty strings")
            if s not in _GLOBAL_SURFACES:
                raise ValueError(
                    f"required_surfaces contains unknown surface {s!r}; "
                    f"valid surfaces are {_GLOBAL_SURFACES}"
                )

    @staticmethod
    def canonical_surfaces() -> tuple[str, ...]:
        return _GLOBAL_SURFACES


@dataclass(frozen=True)
class GlobalParityWitness:
    """One global-parity verdict.

    ``globally_consistent`` is True iff status == "GLOBAL_PASS".
    ``failed_surfaces`` is locals (sorted, ``local:`` prefix) then
    globals in canonical order.
    """

    globally_consistent: bool
    status: GlobalParityStatus
    failed_surfaces: tuple[str, ...]
    local_pass_count: int
    local_fail_count: int
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_global_parity(input_: GlobalParityInput) -> GlobalParityWitness:
    """Pure AND-aggregation of locals and required globals."""
    required = frozenset(input_.required_surfaces)

    failed_locals = [lw.name for lw in input_.local_witnesses if not lw.passed]
    pass_count = len(input_.local_witnesses) - len(failed_locals)

    failed_globals: list[str] = []
    if _SURFACE_CLAIM_LEDGER in required and not input_.claim_ledger_ok:
        failed_globals.append(_SURFACE_CLAIM_LEDGER)
    if _SURFACE_DEPENDENCY_TRUTH in required and not input_.dependency_truth_ok:
        failed_globals.append(_SURFACE_DEPENDENCY_TRUTH)
    if _SURFACE_INVARIANT_COVERAGE in required and not input_.invariant_coverage_ok:
        failed_globals.append(_SURFACE_INVARIANT_COVERAGE)
    if _SURFACE_CI_GATE in required and (input_.ci_gate_ok is None or not input_.ci_gate_ok):
        failed_globals.append(_SURFACE_CI_GATE)

    failed_surfaces: tuple[str, ...] = tuple(f"local:{n}" for n in sorted(failed_locals)) + tuple(
        failed_globals
    )

    # Status priority: locals > claim > deps > invar > ci(False) > ci(None) > pass.
    status: GlobalParityStatus
    if failed_locals:
        status, reason = "LOCAL_FAILURE", "LOCAL_WITNESS_REPORTED_FAILURE"
    elif _SURFACE_CLAIM_LEDGER in required and not input_.claim_ledger_ok:
        status, reason = "CLAIM_LEDGER_FAILURE", "CLAIM_LEDGER_REPORTED_FAILURE"
    elif _SURFACE_DEPENDENCY_TRUTH in required and not input_.dependency_truth_ok:
        status, reason = "DEPENDENCY_TRUTH_FAILURE", "DEPENDENCY_TRUTH_REPORTED_FAILURE"
    elif _SURFACE_INVARIANT_COVERAGE in required and not input_.invariant_coverage_ok:
        status, reason = "INVARIANT_COVERAGE_FAILURE", "INVARIANT_COVERAGE_REPORTED_FAILURE"
    elif _SURFACE_CI_GATE in required and input_.ci_gate_ok is False:
        status, reason = "CI_GATE_FAILURE", "CI_GATE_REPORTED_FAILURE"
    elif _SURFACE_CI_GATE in required and input_.ci_gate_ok is None:
        status, reason = "CI_GATE_UNKNOWN", "CI_GATE_STATUS_UNKNOWN"
    else:
        status, reason = "GLOBAL_PASS", "OK_ALL_REQUIRED_SURFACES_AGREE"

    evidence = MappingProxyType(
        {
            "local_count": len(input_.local_witnesses),
            "local_pass_count": pass_count,
            "local_fail_count": len(failed_locals),
            "required_surfaces": tuple(sorted(required)),
            "failed_surfaces": failed_surfaces,
            "claim_ledger_ok": input_.claim_ledger_ok,
            "dependency_truth_ok": input_.dependency_truth_ok,
            "invariant_coverage_ok": input_.invariant_coverage_ok,
            "ci_gate_ok": input_.ci_gate_ok,
        }
    )

    return GlobalParityWitness(
        globally_consistent=(status == "GLOBAL_PASS"),
        status=status,
        failed_surfaces=failed_surfaces,
        local_pass_count=pass_count,
        local_fail_count=len(failed_locals),
        reason=reason,
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )
