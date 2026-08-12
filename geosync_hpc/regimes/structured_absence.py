# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structured-absence inference — engineering analog of pair-instability-gap discipline.

pattern_id:        P2_STRUCTURED_ABSENCE_INFERENCE
source_id:         S2_PAIR_INSTABILITY_GAP
claim_tier:        ENGINEERING_ANALOG
implementation:    PR #454 (this module)

Engineering analog
==================

The pair-instability-gap result (Nature 2026) demonstrates that an
empty region of state space can be claimed as a TRUE_ABSENCE only
when (a) coverage of that region is sufficient and (b) selection
bias has been classified. An empty bin in a survey is not the same
as a region that is genuinely empty: it can be empty because nothing
was looked for, or because what was there was filtered out, or
because the sample is too small to populate it.

This module imports that *inference discipline*, not the physics. A
GeoSync regime / market-state inference is allowed to declare an
"absent" region only when it satisfies the same three conditions:

    1. sample_count is positive and above a documented minimum
    2. coverage_ratio is at or above a declared threshold
    3. no active selection_bias_flag is set
    AND
    4. the candidate empty region was actually observed as empty

Any failure of any condition produces a different status:

    INSUFFICIENT_COVERAGE    sample_count == 0 OR coverage < threshold
    SELECTION_BIAS           any selection_bias_flag is active
    UNKNOWN                  candidate region contains observations
                             (so it is not actually empty), or any
                             other ambiguous shape
    TRUE_ABSENCE             all four conditions hold

Status is ordinal in name only. The witness's `accepted_as_absence`
boolean is True if and only if status == TRUE_ABSENCE.

Explicit non-claims
===================

This module does NOT claim:
  - that an absence in the data implies an absence in reality without
    the four conditions
  - any forecast / signal / actionable-output use of absence
  - any one-to-one correspondence with cosmological-survey reasoning

It imports the inference discipline only. Its outputs are
classified-status records.

Determinism contract
====================

  - assess_absence(...) is pure: no I/O, no clock, no random, no
    global state.
  - Identical inputs produce byte-identical witness outputs.
  - Invalid inputs (NaN coverage, threshold outside [0, 1], negative
    sample_count, non-finite values) raise at construction or at
    assess time — never produce a misleading classification.
  - There is no module-level mutable state.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "AbsenceStatus",
    "AbsenceInput",
    "AbsenceWitness",
    "assess_absence",
]


# Stable structured reasons. Strings are the API surface — do not
# rephrase without bumping the contract.
_REASON_TRUE_ABSENCE = "OK_TRUE_ABSENCE"
_REASON_INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"
_REASON_INSUFFICIENT_COVERAGE = "COVERAGE_BELOW_THRESHOLD"
_REASON_SELECTION_BIAS = "SELECTION_BIAS_ACTIVE"
_REASON_REGION_NOT_EMPTY = "REGION_NOT_EMPTY"


class AbsenceStatus(str, Enum):
    """Outcome of an absence-inference attempt."""

    TRUE_ABSENCE = "TRUE_ABSENCE"
    SELECTION_BIAS = "SELECTION_BIAS"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AbsenceInput:
    """Single absence-inference question.

    `observed_state_space` lists the points (any hashable) actually
    observed during the survey window. The presence of a point in this
    set means it was observed at least once.

    `candidate_empty_region` is the predicate / set the caller wants
    to classify as empty. If any element of `observed_state_space`
    lies inside `candidate_empty_region`, the region is not empty and
    cannot be a TRUE_ABSENCE; the witness returns UNKNOWN with reason
    REGION_NOT_EMPTY.

    `coverage_ratio` is a float in `[0.0, 1.0]` describing how much of
    the candidate region was observable during the survey. 1.0 means
    full coverage; 0.0 means nothing was observable.

    `selection_bias_flags` is a tuple of stable string identifiers for
    bias modes that may apply. Empty tuple means no active bias.

    `sample_count` is the total number of independent samples
    contributing to the survey. Zero or negative means
    INSUFFICIENT_COVERAGE regardless of `coverage_ratio`.

    `minimum_coverage_threshold` is the floor below which
    `coverage_ratio` cannot support TRUE_ABSENCE. The contract is
    `coverage_ratio >= minimum_coverage_threshold`; equality passes.
    """

    observed_state_space: frozenset[Any]
    candidate_empty_region: frozenset[Any]
    coverage_ratio: float
    selection_bias_flags: tuple[str, ...]
    sample_count: int
    minimum_coverage_threshold: float

    def __post_init__(self) -> None:
        # observed_state_space + candidate_empty_region — must be frozensets
        # of hashable elements; the dataclass annotation is only
        # advisory, so we coerce defensively.
        if not isinstance(self.observed_state_space, frozenset):
            raise TypeError(
                "observed_state_space must be a frozenset; convert "
                "via frozenset(...) at the call site"
            )
        if not isinstance(self.candidate_empty_region, frozenset):
            raise TypeError(
                "candidate_empty_region must be a frozenset; convert "
                "via frozenset(...) at the call site"
            )

        # coverage_ratio: finite float in [0, 1].
        if not isinstance(self.coverage_ratio, (int, float)) or isinstance(
            self.coverage_ratio, bool
        ):
            raise TypeError("coverage_ratio must be a finite float in [0, 1]")
        cov = float(self.coverage_ratio)
        if not math.isfinite(cov):
            raise ValueError(f"coverage_ratio must be finite (got {cov!r})")
        if not 0.0 <= cov <= 1.0:
            raise ValueError(f"coverage_ratio must be in [0.0, 1.0] (got {cov!r})")

        # selection_bias_flags: tuple of non-empty strings.
        if not isinstance(self.selection_bias_flags, tuple):
            raise TypeError("selection_bias_flags must be a tuple of strings")
        for flag in self.selection_bias_flags:
            if not isinstance(flag, str) or not flag.strip():
                raise ValueError("selection_bias_flags entries must be non-empty strings")

        # sample_count: non-negative int (not bool).
        if not isinstance(self.sample_count, int) or isinstance(self.sample_count, bool):
            raise TypeError("sample_count must be a non-negative int")
        if self.sample_count < 0:
            raise ValueError(f"sample_count must be >= 0 (got {self.sample_count!r})")

        # minimum_coverage_threshold: finite float in [0, 1].
        if not isinstance(self.minimum_coverage_threshold, (int, float)) or isinstance(
            self.minimum_coverage_threshold, bool
        ):
            raise TypeError("minimum_coverage_threshold must be a finite float in [0, 1]")
        thr = float(self.minimum_coverage_threshold)
        if not math.isfinite(thr):
            raise ValueError(f"minimum_coverage_threshold must be finite (got {thr!r})")
        if not 0.0 <= thr <= 1.0:
            raise ValueError(f"minimum_coverage_threshold must be in [0.0, 1.0] (got {thr!r})")


@dataclass(frozen=True)
class AbsenceWitness:
    """Outcome of one assessment.

    `status` is the structural verdict; `accepted_as_absence` is True
    iff `status == TRUE_ABSENCE`. `reason` is a stable structured tag
    callers may pattern-match on. `falsifier` is a human-readable
    description of what would make this witness wrong.
    """

    status: AbsenceStatus
    accepted_as_absence: bool
    reason: str
    coverage_ratio: float
    selection_bias_present: bool
    sample_count: int
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


# ---------------------------------------------------------------------------
# Pure assessment function
# ---------------------------------------------------------------------------


_FALSIFIER_TEXT = (
    "TRUE_ABSENCE was returned but at least one of the following held: "
    "sample_count == 0; coverage_ratio < minimum_coverage_threshold; "
    "selection_bias_flags non-empty; the observed_state_space contained "
    "points inside candidate_empty_region."
)


def _region_observed_to_be_empty(input_: AbsenceInput) -> bool:
    """Return True iff candidate_empty_region contains zero observed points.

    The check is set-intersection. The candidate region is empty in the
    observed state space when it shares no element with the observed set.
    """
    return not (input_.observed_state_space & input_.candidate_empty_region)


def assess_absence(input_: AbsenceInput) -> AbsenceWitness:
    """Classify the absence-inference question carried by ``input_``.

    Pure function. Reads only the input dataclass; no I/O, no clock,
    no global state. Returns one ``AbsenceWitness`` describing the
    structural verdict.

    Priority order (the first failing condition wins):

        1. sample_count == 0           → INSUFFICIENT_COVERAGE
        2. selection_bias_flags        → SELECTION_BIAS
        3. coverage < threshold        → INSUFFICIENT_COVERAGE
        4. region observed not empty   → UNKNOWN (REGION_NOT_EMPTY)
        5. otherwise                   → TRUE_ABSENCE
    """
    bias_present = bool(input_.selection_bias_flags)
    cov = float(input_.coverage_ratio)
    thr = float(input_.minimum_coverage_threshold)
    region_empty = _region_observed_to_be_empty(input_)

    evidence = MappingProxyType(
        dict(
            {
                "coverage_ratio": cov,
                "minimum_coverage_threshold": thr,
                "sample_count": input_.sample_count,
                "selection_bias_flags": tuple(input_.selection_bias_flags),
                "observed_count_in_region": len(
                    input_.observed_state_space & input_.candidate_empty_region
                ),
            }
        )
    )

    if input_.sample_count == 0:
        return AbsenceWitness(
            status=AbsenceStatus.INSUFFICIENT_COVERAGE,
            accepted_as_absence=False,
            reason=_REASON_INSUFFICIENT_SAMPLES,
            coverage_ratio=cov,
            selection_bias_present=bias_present,
            sample_count=input_.sample_count,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if bias_present:
        return AbsenceWitness(
            status=AbsenceStatus.SELECTION_BIAS,
            accepted_as_absence=False,
            reason=_REASON_SELECTION_BIAS,
            coverage_ratio=cov,
            selection_bias_present=True,
            sample_count=input_.sample_count,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if cov < thr:
        return AbsenceWitness(
            status=AbsenceStatus.INSUFFICIENT_COVERAGE,
            accepted_as_absence=False,
            reason=_REASON_INSUFFICIENT_COVERAGE,
            coverage_ratio=cov,
            selection_bias_present=False,
            sample_count=input_.sample_count,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if not region_empty:
        return AbsenceWitness(
            status=AbsenceStatus.UNKNOWN,
            accepted_as_absence=False,
            reason=_REASON_REGION_NOT_EMPTY,
            coverage_ratio=cov,
            selection_bias_present=False,
            sample_count=input_.sample_count,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    return AbsenceWitness(
        status=AbsenceStatus.TRUE_ABSENCE,
        accepted_as_absence=True,
        reason=_REASON_TRUE_ABSENCE,
        coverage_ratio=cov,
        selection_bias_present=False,
        sample_count=input_.sample_count,
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )


def assess_many(inputs: Iterable[AbsenceInput]) -> tuple[AbsenceWitness, ...]:
    """Apply ``assess_absence`` to a sequence of inputs.

    Returned tuple preserves input order. Provided as a convenience for
    callers that batch many region inferences; behaviour is exactly
    equivalent to mapping ``assess_absence`` over the iterable.
    """
    return tuple(assess_absence(i) for i in inputs)
