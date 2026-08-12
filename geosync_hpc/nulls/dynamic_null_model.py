# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dynamic-null model — engineering analog of bounded-drift baseline discipline.

pattern_id:        P3_DYNAMIC_NULL_MODEL
source_id:         S3_DESI_2026
claim_tier:        ENGINEERING_ANALOG
implementation:    PR #455 (this module)

Engineering analog
==================

The DESI 2026 milestone surfaced tension in expansion-history baselines:
the null itself drifts, under bounded rules, and is not a static
reference. The drift bounds are part of the model, not implicit.

This module imports that *inference discipline*, not the cosmology. A
dynamic-null comparison in GeoSync is allowed only when the baseline
series stays within an explicit `drift_bound`. Two named lies are
blocked here:

  Lie A: "baseline is fixed forever" — pretending a static null when
         the underlying baseline is in fact moving.
  Lie B: "dynamic null may drift freely until the anomaly disappears" —
         letting the null absorb the signal by quietly drifting.

The witness's contract is symmetric:

    1. baseline_series shorter than minimum_history     → INSUFFICIENT_HISTORY
    2. observed drift exceeds drift_bound               → NULL_DRIFT_EXCEEDED
                                                          (fail closed)
    3. observed_value outside [null - tol, null + tol]  → OUTSIDE_DYNAMIC_NULL
    4. observed_value inside that band                  → WITHIN_DYNAMIC_NULL
    5. otherwise (degenerate: empty history with        → UNKNOWN
       minimum_history == 0)

Status order is contract: an excursion of the null itself ALWAYS wins
over an excursion of the observation. A model whose null has lost its
bound has no right to label observations.

Static reduction
================

When `drift_bound == 0` and `baseline_series` is constant, the dynamic
witness reduces to the static comparison `|observed - null| <= tol`.
That reduction is enforced by ``test_static_null_with_zero_drift_bound``
and by ``test_dynamic_matches_static_when_zero_drift``.

Explicit non-claims
===================

This module does NOT claim:
  - that the dynamic null is itself a forecast
  - any one-to-one correspondence with cosmological-survey reasoning
  - any market / trading / signal interpretation of an OUTSIDE_DYNAMIC_NULL
    classification

Determinism contract
====================

  - assess_dynamic_null(...) is pure: no I/O, no clock, no random, no
    global state.
  - Identical inputs produce byte-identical witness outputs.
  - Invalid inputs (NaN/inf in any numeric field, negative drift_bound,
    negative tolerance, negative minimum_history, non-tuple
    baseline_series, NaN in observed_value) raise at construction or
    at assess time — never produce a misleading classification.
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
    "NullStatus",
    "NullInput",
    "NullWitness",
    "assess_dynamic_null",
    "assess_many",
]


# Stable structured reasons. Strings are the API surface — do not
# rephrase without bumping the contract.
_REASON_WITHIN = "OK_WITHIN_DYNAMIC_NULL"
_REASON_OUTSIDE = "SIGNAL_OUTSIDE_DYNAMIC_NULL"
_REASON_DRIFT_EXCEEDED = "NULL_DRIFT_EXCEEDS_BOUND"
_REASON_INSUFFICIENT = "INSUFFICIENT_BASELINE_HISTORY"
_REASON_UNKNOWN = "UNKNOWN_NO_BASELINE"


_FALSIFIER_TEXT = (
    "WITHIN_DYNAMIC_NULL or OUTSIDE_DYNAMIC_NULL was returned but the "
    "baseline-series drift exceeded drift_bound. OR: the dynamic-null "
    "verdict differed from the static-null verdict at zero observed "
    "drift. OR: a NULL_DRIFT_EXCEEDED case silently produced a "
    "non-failing status."
)


class NullStatus(str, Enum):
    """Outcome of a dynamic-null assessment."""

    WITHIN_DYNAMIC_NULL = "WITHIN_DYNAMIC_NULL"
    OUTSIDE_DYNAMIC_NULL = "OUTSIDE_DYNAMIC_NULL"
    NULL_DRIFT_EXCEEDED = "NULL_DRIFT_EXCEEDED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NullInput:
    """Single dynamic-null inference question.

    `baseline_series` is the history of null values up to and including
    the current null. The current null is `baseline_series[-1]`. The
    drift used in the witness is `max(baseline_series) - min(baseline_series)`,
    i.e. the full span observed across the history window.

    `observed_value` is the new measurement to be classified against
    the current null with tolerance `null_tolerance`.

    `drift_bound` is the maximum acceptable span for the baseline
    history. A history whose span exceeds `drift_bound` makes the
    witness fail closed (NULL_DRIFT_EXCEEDED) regardless of where
    `observed_value` lies.

    `null_tolerance` is the half-width of the "within null" band
    around the current null. The contract is
    `|observed_value - null_value| <= null_tolerance`; equality passes.

    `minimum_history` is the floor on `len(baseline_series)` below
    which no comparison is supported.
    """

    baseline_series: tuple[float, ...]
    observed_value: float
    drift_bound: float
    null_tolerance: float
    minimum_history: int

    def __post_init__(self) -> None:
        # baseline_series: tuple of finite floats.
        if not isinstance(self.baseline_series, tuple):
            raise TypeError(
                "baseline_series must be a tuple of floats; convert via tuple(...) at the call site"
            )
        for i, value in enumerate(self.baseline_series):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"baseline_series[{i}] must be a finite float (got {value!r})")
            if not math.isfinite(float(value)):
                raise ValueError(f"baseline_series[{i}] must be finite (got {value!r})")

        # observed_value: finite float (not bool).
        if not isinstance(self.observed_value, (int, float)) or isinstance(
            self.observed_value, bool
        ):
            raise TypeError("observed_value must be a finite float")
        if not math.isfinite(float(self.observed_value)):
            raise ValueError(f"observed_value must be finite (got {self.observed_value!r})")

        # drift_bound: finite, non-negative float (not bool).
        if not isinstance(self.drift_bound, (int, float)) or isinstance(self.drift_bound, bool):
            raise TypeError("drift_bound must be a finite, non-negative float")
        if not math.isfinite(float(self.drift_bound)):
            raise ValueError(f"drift_bound must be finite (got {self.drift_bound!r})")
        if float(self.drift_bound) < 0.0:
            raise ValueError(f"drift_bound must be >= 0 (got {self.drift_bound!r})")

        # null_tolerance: finite, non-negative float (not bool).
        if not isinstance(self.null_tolerance, (int, float)) or isinstance(
            self.null_tolerance, bool
        ):
            raise TypeError("null_tolerance must be a finite, non-negative float")
        if not math.isfinite(float(self.null_tolerance)):
            raise ValueError(f"null_tolerance must be finite (got {self.null_tolerance!r})")
        if float(self.null_tolerance) < 0.0:
            raise ValueError(f"null_tolerance must be >= 0 (got {self.null_tolerance!r})")

        # minimum_history: non-negative int (not bool).
        if not isinstance(self.minimum_history, int) or isinstance(self.minimum_history, bool):
            raise TypeError("minimum_history must be a non-negative int")
        if self.minimum_history < 0:
            raise ValueError(f"minimum_history must be >= 0 (got {self.minimum_history!r})")


@dataclass(frozen=True)
class NullWitness:
    """Outcome of one dynamic-null assessment.

    `status` is the structural verdict; `within_bound` is True iff the
    drift span did not exceed `drift_bound`. `reason` is a stable
    structured tag callers may pattern-match on. `falsifier` is a
    human-readable description of what would make this witness wrong.
    """

    status: NullStatus
    null_value: float
    observed_value: float
    drift_used: float
    drift_bound: float
    within_bound: bool
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


# ---------------------------------------------------------------------------
# Pure assessment function
# ---------------------------------------------------------------------------


def _drift_span(series: tuple[float, ...]) -> float:
    """Return the span (max - min) of the baseline series.

    Empty series return 0.0; this is consumed only by callers that have
    already classified the empty case as INSUFFICIENT_HISTORY or UNKNOWN.
    """
    if not series:
        return 0.0
    return float(max(series)) - float(min(series))


def assess_dynamic_null(input_: NullInput) -> NullWitness:
    """Classify the dynamic-null question carried by ``input_``.

    Pure function. Reads only the input dataclass; no I/O, no clock,
    no global state. Returns one ``NullWitness`` describing the
    structural verdict.

    Priority order (the first failing condition wins):

        1. baseline_series shorter than minimum_history → INSUFFICIENT_HISTORY
        2. baseline_series empty (and minimum_history == 0) → UNKNOWN
        3. drift > drift_bound        → NULL_DRIFT_EXCEEDED (fail closed)
        4. |observed - null| > tol    → OUTSIDE_DYNAMIC_NULL
        5. otherwise                  → WITHIN_DYNAMIC_NULL
    """
    history_len = len(input_.baseline_series)
    drift_used = _drift_span(input_.baseline_series)
    within_bound = drift_used <= float(input_.drift_bound)

    null_value = float(input_.baseline_series[-1]) if history_len > 0 else float("nan")
    observed = float(input_.observed_value)
    tol = float(input_.null_tolerance)
    bound = float(input_.drift_bound)

    evidence = MappingProxyType(
        dict(
            {
                "history_len": history_len,
                "minimum_history": input_.minimum_history,
                "drift_used": drift_used,
                "drift_bound": bound,
                "null_tolerance": tol,
                "null_value": null_value if history_len > 0 else None,
                "observed_value": observed,
            }
        )
    )

    if history_len < input_.minimum_history:
        return NullWitness(
            status=NullStatus.INSUFFICIENT_HISTORY,
            null_value=null_value if history_len > 0 else 0.0,
            observed_value=observed,
            drift_used=drift_used,
            drift_bound=bound,
            within_bound=within_bound,
            reason=_REASON_INSUFFICIENT,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if history_len == 0:
        # minimum_history == 0 path: caller authorised "no history is
        # acceptable", but there is still no null to compare against —
        # fail closed to UNKNOWN.
        return NullWitness(
            status=NullStatus.UNKNOWN,
            null_value=0.0,
            observed_value=observed,
            drift_used=drift_used,
            drift_bound=bound,
            within_bound=within_bound,
            reason=_REASON_UNKNOWN,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if drift_used > bound:
        return NullWitness(
            status=NullStatus.NULL_DRIFT_EXCEEDED,
            null_value=null_value,
            observed_value=observed,
            drift_used=drift_used,
            drift_bound=bound,
            within_bound=False,
            reason=_REASON_DRIFT_EXCEEDED,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if abs(observed - null_value) > tol:
        return NullWitness(
            status=NullStatus.OUTSIDE_DYNAMIC_NULL,
            null_value=null_value,
            observed_value=observed,
            drift_used=drift_used,
            drift_bound=bound,
            within_bound=True,
            reason=_REASON_OUTSIDE,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    return NullWitness(
        status=NullStatus.WITHIN_DYNAMIC_NULL,
        null_value=null_value,
        observed_value=observed,
        drift_used=drift_used,
        drift_bound=bound,
        within_bound=True,
        reason=_REASON_WITHIN,
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )


def assess_many(inputs: Iterable[NullInput]) -> tuple[NullWitness, ...]:
    """Apply ``assess_dynamic_null`` to a sequence of inputs.

    Returned tuple preserves input order. Provided as a convenience for
    callers that batch many baseline-vs-signal comparisons; behaviour
    is exactly equivalent to mapping ``assess_dynamic_null`` over the
    iterable.
    """
    return tuple(assess_dynamic_null(i) for i in inputs)
