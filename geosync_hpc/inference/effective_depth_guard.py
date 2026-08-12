# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Effective-depth guard — engineering analog of noise-induced shallow-circuit discipline.

pattern_id:        P9_EFFECTIVE_DEPTH_GUARD
source_id:         S9_NOISE_INDUCED_SHALLOW_CIRCUITS
claim_tier:        ENGINEERING_ANALOG

A pipeline's effective depth must be tested by comparing outputs across
depths under explicit noise; longer is not automatically deeper. The
named lie blocked here is "longer reasoning chain = deeper truth". If
a shorter pipeline produces output equivalent to a deeper one within
``tolerance``, the additional depth is REDUNDANT.

Statuses:
    EFFECTIVE_DEPTH_FOUND  the smallest non-redundant depth in
                           [minimum_depth, maximum_depth] is identified;
                           no shallower depth produces equivalent output
    REDUNDANT_DEPTH        at least one (d, d+k) pair has equivalent
                           outputs within tolerance
    NO_STABLE_DEPTH        every consecutive pair diverges; no
                           equivalence detected within range
    INVALID_INPUT          missing depth, NaN/inf, depth range invalid

Non-claims: no one-to-one correspondence with quantum-circuit physics;
no claim that depth maps to truth, intelligence, or accuracy. The guard
reports equivalence relations only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "DepthStatus",
    "DepthInput",
    "DepthWitness",
    "assess_effective_depth",
]


_FALSIFIER_TEXT = (
    "EFFECTIVE_DEPTH_FOUND was returned but a shallower depth produced "
    "output equivalent within tolerance. OR: a REDUNDANT_DEPTH pair was "
    "silently upgraded to EFFECTIVE_DEPTH_FOUND because the equivalence "
    "tolerance check was bypassed."
)


class DepthStatus(str, Enum):
    EFFECTIVE_DEPTH_FOUND = "EFFECTIVE_DEPTH_FOUND"
    REDUNDANT_DEPTH = "REDUNDANT_DEPTH"
    NO_STABLE_DEPTH = "NO_STABLE_DEPTH"
    INVALID_INPUT = "INVALID_INPUT"


def _l2_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b, strict=True)))


@dataclass(frozen=True)
class DepthInput:
    """One effective-depth question.

    ``outputs_by_depth`` is a mapping {depth: output_vector}; each
    output is a tuple of finite floats. ``tolerance`` is the L2-distance
    threshold under which two outputs are considered equivalent.
    ``noise_level`` is recorded for traceability; the guard does not
    perturb inputs itself. ``minimum_depth`` and ``maximum_depth`` bound
    which depths are considered.
    """

    outputs_by_depth: Mapping[int, tuple[float, ...]]
    tolerance: float
    noise_level: float
    minimum_depth: int
    maximum_depth: int

    def __post_init__(self) -> None:
        if not isinstance(self.outputs_by_depth, Mapping):
            raise TypeError("outputs_by_depth must be a Mapping[int, tuple[float, ...]]")
        if len(self.outputs_by_depth) == 0:
            raise ValueError("outputs_by_depth must be non-empty")
        for d, vec in self.outputs_by_depth.items():
            if not isinstance(d, int) or isinstance(d, bool):
                raise TypeError(f"outputs_by_depth keys must be int (got {d!r})")
            if d < 0:
                raise ValueError(f"outputs_by_depth keys must be >= 0 (got {d!r})")
            if not isinstance(vec, tuple):
                raise TypeError(f"outputs_by_depth[{d}] must be a tuple of floats")
            for i, v in enumerate(vec):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise TypeError(f"outputs_by_depth[{d}][{i}] must be a finite float")
                if not math.isfinite(float(v)):
                    raise ValueError(f"outputs_by_depth[{d}][{i}] must be finite (got {v!r})")

        for name, value in (("tolerance", self.tolerance), ("noise_level", self.noise_level)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be a finite, non-negative float")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite (got {value!r})")
            if float(value) < 0.0:
                raise ValueError(f"{name} must be >= 0 (got {value!r})")

        for name, value in (
            ("minimum_depth", self.minimum_depth),
            ("maximum_depth", self.maximum_depth),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be a non-negative int")
            if value < 0:
                raise ValueError(f"{name} must be >= 0 (got {value!r})")

        if self.maximum_depth < self.minimum_depth:
            raise ValueError(
                f"maximum_depth must be >= minimum_depth "
                f"(got {self.maximum_depth} < {self.minimum_depth})"
            )

        for d in range(self.minimum_depth, self.maximum_depth + 1):
            if d not in self.outputs_by_depth:
                raise ValueError(
                    f"outputs_by_depth missing required depth {d} "
                    f"in range [{self.minimum_depth}, {self.maximum_depth}]"
                )


@dataclass(frozen=True)
class DepthWitness:
    """One effective-depth verdict."""

    status: DepthStatus
    effective_depth: int | None
    redundant_depths: tuple[int, ...]
    tolerance_used: float
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_effective_depth(input_: DepthInput) -> DepthWitness:
    """Pure equivalence-relation classifier.

    Walks depths in ascending order from minimum_depth to maximum_depth.
    For each consecutive pair (d, d+1), computes L2-distance between
    outputs. If the distance is <= tolerance, depth d+1 is REDUNDANT
    (its output is equivalent to depth d).

    Priority:
        1. any redundant pair found  → REDUNDANT_DEPTH
        2. all pairs diverge AND minimum_depth output exists
                                      → EFFECTIVE_DEPTH_FOUND
                                        (effective_depth = minimum_depth)
        3. otherwise (depth range degenerate) → NO_STABLE_DEPTH
    """
    tolerance = float(input_.tolerance)
    depths = sorted(
        d for d in input_.outputs_by_depth if input_.minimum_depth <= d <= input_.maximum_depth
    )

    redundant: list[int] = []
    distances: list[float] = []
    for i in range(1, len(depths)):
        d_prev = depths[i - 1]
        d_curr = depths[i]
        dist = _l2_distance(input_.outputs_by_depth[d_prev], input_.outputs_by_depth[d_curr])
        distances.append(dist)
        if math.isfinite(dist) and dist <= tolerance:
            redundant.append(d_curr)

    evidence = MappingProxyType(
        {
            "depth_count": len(depths),
            "minimum_depth": input_.minimum_depth,
            "maximum_depth": input_.maximum_depth,
            "tolerance": tolerance,
            "noise_level": float(input_.noise_level),
            "consecutive_distances": tuple(distances),
            "redundant_depths": tuple(redundant),
        }
    )

    if redundant:
        return DepthWitness(
            status=DepthStatus.REDUNDANT_DEPTH,
            effective_depth=None,
            redundant_depths=tuple(redundant),
            tolerance_used=tolerance,
            reason="SHALLOWER_OUTPUT_EQUIVALENT_WITHIN_TOLERANCE",
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if len(depths) >= 1:
        return DepthWitness(
            status=DepthStatus.EFFECTIVE_DEPTH_FOUND,
            effective_depth=depths[0],
            redundant_depths=(),
            tolerance_used=tolerance,
            reason="OK_NO_SHALLOWER_EQUIVALENT",
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    return DepthWitness(
        status=DepthStatus.NO_STABLE_DEPTH,
        effective_depth=None,
        redundant_depths=(),
        tolerance_used=tolerance,
        reason="DEPTH_RANGE_DEGENERATE",
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )
