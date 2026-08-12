# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Composite binding structure — engineering analog of doubly-charmed-baryon discipline.

pattern_id:        P6_COMPOSITE_BINDING_STRUCTURE
source_id:         S6_LHCB_DOUBLY_CHARMED_BARYON
claim_tier:        ENGINEERING_ANALOG

A high correlation across an asset cluster is *transient* unless it
survives both a documented persistence window AND a documented
perturbation-response check. The named lie blocked here is
"correlation = binding": clusters that dissolve under perturbation must
be reported as TRANSIENT_CORRELATION, not as PERSISTENT_BINDING.

Statuses:
    PERSISTENT_BINDING       relation persists across window AND
                             survives perturbation
    TRANSIENT_CORRELATION    relation seen, but it dissolves under
                             perturbation OR fails to persist
    INSUFFICIENT_PERSISTENCE relation persists for fewer than the
                             required window samples
    UNKNOWN                  degenerate inputs (empty cluster after
                             validation, all-NaN windows)

Non-claims: no one-to-one correspondence with quantum-baryon physics;
PERSISTENT_BINDING is not a forecast, signal, or trading instruction.
Determinism: pure function, no I/O, no clock, no random.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "BindingStatus",
    "BindingInput",
    "BindingWitness",
    "assess_composite_binding",
]


_FALSIFIER_TEXT = (
    "PERSISTENT_BINDING was returned but the cluster's correlation "
    "dissolved under the documented perturbation; OR the relation did "
    "not survive the persistence window; OR a TRANSIENT_CORRELATION "
    "case was silently upgraded to PERSISTENT_BINDING because the "
    "perturbation_response check was bypassed."
)


class BindingStatus(str, Enum):
    PERSISTENT_BINDING = "PERSISTENT_BINDING"
    TRANSIENT_CORRELATION = "TRANSIENT_CORRELATION"
    INSUFFICIENT_PERSISTENCE = "INSUFFICIENT_PERSISTENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BindingInput:
    """One composite-binding question.

    ``correlation_window`` is a tuple of correlation values observed at
    successive time slices for the cluster. ``correlation_threshold``
    is the floor above which a slice is considered "in cluster".
    ``persistence_window`` is the minimum number of in-cluster slices
    required to consider persistence achieved. ``perturbation_response``
    is a tuple of correlation values observed under the documented
    perturbation; the binding survives if the median perturbation-
    response value remains above ``correlation_threshold``.
    """

    asset_cluster: tuple[str, ...]
    correlation_window: tuple[float, ...]
    correlation_threshold: float
    persistence_window: int
    perturbation_response: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.asset_cluster, tuple):
            raise TypeError("asset_cluster must be a tuple of strings")
        if len(self.asset_cluster) == 0:
            raise ValueError("asset_cluster must be non-empty")
        for i, name in enumerate(self.asset_cluster):
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"asset_cluster[{i}] must be a non-empty string")

        for name, series in (
            ("correlation_window", self.correlation_window),
            ("perturbation_response", self.perturbation_response),
        ):
            if not isinstance(series, tuple):
                raise TypeError(f"{name} must be a tuple of floats")
            for i, v in enumerate(series):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise TypeError(f"{name}[{i}] must be a finite float")
                if not math.isfinite(float(v)):
                    raise ValueError(f"{name}[{i}] must be finite (got {v!r})")
                if not -1.0 <= float(v) <= 1.0:
                    raise ValueError(
                        f"{name}[{i}] must be in [-1, 1] (got {v!r}); "
                        "this witness assumes correlation-coefficient inputs"
                    )

        if not isinstance(self.correlation_threshold, (int, float)) or isinstance(
            self.correlation_threshold, bool
        ):
            raise TypeError("correlation_threshold must be a finite float in [-1, 1]")
        if not math.isfinite(float(self.correlation_threshold)):
            raise ValueError(
                f"correlation_threshold must be finite (got {self.correlation_threshold!r})"
            )
        if not -1.0 <= float(self.correlation_threshold) <= 1.0:
            raise ValueError(
                f"correlation_threshold must be in [-1, 1] (got {self.correlation_threshold!r})"
            )

        if not isinstance(self.persistence_window, int) or isinstance(
            self.persistence_window, bool
        ):
            raise TypeError("persistence_window must be a positive int")
        if self.persistence_window <= 0:
            raise ValueError(f"persistence_window must be > 0 (got {self.persistence_window!r})")


@dataclass(frozen=True)
class BindingWitness:
    """One composite-binding verdict."""

    binding_status: BindingStatus
    transient_correlation: bool
    persistent_binding: bool
    persistent_slice_count: int
    perturbation_median: float
    threshold_used: float
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def _median(values: tuple[float, ...]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float(0.5 * (s[mid - 1] + s[mid]))


def assess_composite_binding(input_: BindingInput) -> BindingWitness:
    """Pure binding classifier.

    Priority (first failing condition wins):
        1. correlation_window empty            → UNKNOWN
        2. perturbation_response empty         → UNKNOWN
        3. persistent_slice_count < window     → INSUFFICIENT_PERSISTENCE
        4. perturbation_median < threshold     → TRANSIENT_CORRELATION
        5. otherwise                           → PERSISTENT_BINDING
    """
    threshold = float(input_.correlation_threshold)
    persistent_count = sum(1 for v in input_.correlation_window if float(v) >= threshold)
    perturb_median = _median(input_.perturbation_response)

    def _build(
        status: BindingStatus,
        *,
        transient: bool,
        persistent: bool,
        reason: str,
    ) -> BindingWitness:
        evidence = MappingProxyType(
            {
                "asset_cluster": input_.asset_cluster,
                "correlation_window_len": len(input_.correlation_window),
                "perturbation_response_len": len(input_.perturbation_response),
                "persistent_slice_count": persistent_count,
                "perturbation_median": perturb_median,
                "correlation_threshold": threshold,
                "persistence_window": input_.persistence_window,
            }
        )
        return BindingWitness(
            binding_status=status,
            transient_correlation=transient,
            persistent_binding=persistent,
            persistent_slice_count=persistent_count,
            perturbation_median=perturb_median,
            threshold_used=threshold,
            reason=reason,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if len(input_.correlation_window) == 0:
        return _build(
            BindingStatus.UNKNOWN,
            transient=False,
            persistent=False,
            reason="EMPTY_CORRELATION_WINDOW",
        )
    if len(input_.perturbation_response) == 0:
        return _build(
            BindingStatus.UNKNOWN,
            transient=False,
            persistent=False,
            reason="EMPTY_PERTURBATION_RESPONSE",
        )

    if persistent_count < input_.persistence_window:
        return _build(
            BindingStatus.INSUFFICIENT_PERSISTENCE,
            transient=False,
            persistent=False,
            reason="PERSISTENT_SLICES_BELOW_WINDOW",
        )

    if perturb_median < threshold:
        return _build(
            BindingStatus.TRANSIENT_CORRELATION,
            transient=True,
            persistent=False,
            reason="PERTURBATION_DISSOLVED_RELATION",
        )

    return _build(
        BindingStatus.PERSISTENT_BINDING,
        transient=False,
        persistent=True,
        reason="OK_RELATION_SURVIVES_PERTURBATION_AND_WINDOW",
    )
