# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim gauge witness — engineering analog of S10 local-consistency gauging.

pattern_id:        P10_CLAIM_GAUGE_WITNESS
source_id:         S10_LOGICAL_GAUGING_LOCAL_SYMMETRY
claim_tier:        ENGINEERING_ANALOG

A claim about a global property must be gauged against the local-
consistency constraints it implies. The named lie blocked here is
"a single local check is a global proof". A claim is GAUGE_PASS only
when every required local-consistency constraint is satisfied.

Statuses:
    GAUGE_PASS                every required constraint is satisfied
    GAUGE_REFUSED             at least one required constraint reports
                              unsatisfied; ``failing_constraints`` lists
                              the offenders
    UNKNOWN_CONSTRAINT         a required constraint is missing from
                              the satisfaction map
    INVALID_INPUT             malformed constraint shape

Non-claims: no one-to-one correspondence with logical-gauging physics;
no forecast / signal / trading interpretation; the witness reports a
boolean AND over named local surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "GaugeStatus",
    "GaugeInput",
    "GaugeWitness",
    "assess_claim_gauge",
]


_FALSIFIER_TEXT = (
    "GAUGE_PASS was returned but at least one required local-consistency "
    "constraint reported unsatisfied. OR: the required-constraints set "
    "was silently emptied or its intersection with the satisfaction map "
    "was bypassed. OR: a missing required constraint was treated as "
    "satisfied."
)


class GaugeStatus(str, Enum):
    GAUGE_PASS = "GAUGE_PASS"
    GAUGE_REFUSED = "GAUGE_REFUSED"
    UNKNOWN_CONSTRAINT = "UNKNOWN_CONSTRAINT"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class GaugeInput:
    """One claim-gauge question.

    ``claim_id`` is a stable identifier for the global claim under
    test. ``local_constraints`` is the full set of constraint names the
    caller has measured. ``constraint_satisfaction`` maps each constraint
    name to a bool. ``required_constraints`` is the subset the gauge
    enforces; it must be a non-empty subset of ``local_constraints``.
    """

    claim_id: str
    local_constraints: tuple[str, ...]
    constraint_satisfaction: Mapping[str, bool]
    required_constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")

        if not isinstance(self.local_constraints, tuple):
            raise TypeError("local_constraints must be a tuple of strings")
        if len(self.local_constraints) == 0:
            raise ValueError("local_constraints must be non-empty")
        for i, c in enumerate(self.local_constraints):
            if not isinstance(c, str) or not c.strip():
                raise ValueError(f"local_constraints[{i}] must be a non-empty string")

        if not isinstance(self.constraint_satisfaction, Mapping):
            raise TypeError("constraint_satisfaction must be a Mapping[str, bool]")
        for k, v in self.constraint_satisfaction.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("constraint_satisfaction keys must be non-empty strings")
            if not isinstance(v, bool):
                raise TypeError(f"constraint_satisfaction[{k!r}] must be a bool")

        if not isinstance(self.required_constraints, tuple):
            raise TypeError("required_constraints must be a tuple of strings")
        if len(self.required_constraints) == 0:
            raise ValueError("required_constraints must be non-empty")
        for i, c in enumerate(self.required_constraints):
            if not isinstance(c, str) or not c.strip():
                raise ValueError(f"required_constraints[{i}] must be a non-empty string")

        local_set = set(self.local_constraints)
        for c in self.required_constraints:
            if c not in local_set:
                raise ValueError(
                    f"required constraint {c!r} not present in local_constraints; "
                    "every required constraint must be declared as local first"
                )


@dataclass(frozen=True)
class GaugeWitness:
    """One claim-gauge verdict."""

    status: GaugeStatus
    claim_id: str
    failing_constraints: tuple[str, ...]
    missing_constraints: tuple[str, ...]
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_claim_gauge(input_: GaugeInput) -> GaugeWitness:
    """Pure local-consistency gauge.

    Priority (first failing condition wins):
        1. any required constraint missing from satisfaction map
                                          → UNKNOWN_CONSTRAINT
        2. any required constraint False  → GAUGE_REFUSED
        3. otherwise                       → GAUGE_PASS
    """
    sat = input_.constraint_satisfaction
    required = input_.required_constraints

    missing: list[str] = [c for c in required if c not in sat]
    failing: list[str] = [c for c in required if c in sat and not sat[c]]

    evidence = MappingProxyType(
        {
            "claim_id": input_.claim_id,
            "local_count": len(input_.local_constraints),
            "required_count": len(required),
            "missing_count": len(missing),
            "failing_count": len(failing),
            "missing_constraints": tuple(missing),
            "failing_constraints": tuple(failing),
        }
    )

    if missing:
        return GaugeWitness(
            status=GaugeStatus.UNKNOWN_CONSTRAINT,
            claim_id=input_.claim_id,
            failing_constraints=tuple(failing),
            missing_constraints=tuple(missing),
            reason="REQUIRED_CONSTRAINT_NOT_MEASURED",
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )
    if failing:
        return GaugeWitness(
            status=GaugeStatus.GAUGE_REFUSED,
            claim_id=input_.claim_id,
            failing_constraints=tuple(failing),
            missing_constraints=(),
            reason="REQUIRED_CONSTRAINT_UNSATISFIED",
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )
    return GaugeWitness(
        status=GaugeStatus.GAUGE_PASS,
        claim_id=input_.claim_id,
        failing_constraints=(),
        missing_constraints=(),
        reason="OK_ALL_REQUIRED_CONSTRAINTS_SATISFIED",
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )
