# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Motional-correlation witness — engineering analog of trajectory-Bell discipline.

pattern_id:        P5_MOTIONAL_CORRELATION_WITNESS
source_id:         S5_HELIUM_MOTIONAL_BELL
claim_tier:        ENGINEERING_ANALOG

A correlation that survives time-axis shuffling is static, not dynamic.
The named lie blocked here is "static correlation = dynamic relation":
a relation between two trajectories is *dynamic* only when the
trajectory-ordered score beats a shuffled-trajectory null at a
documented margin.

Statuses:
    DYNAMIC_RELATION_CONFIRMED  trajectory score > static score by margin
    STATIC_ONLY                 trajectory score and shuffled null
                                indistinguishable within margin
    INSUFFICIENT_DATA           series too short to seed the shuffle
    UNKNOWN                     degenerate inputs (e.g. constant series)

Non-claims: no one-to-one correspondence with helium-Bell physics; the
witness emits no forecast, signal, or trading instruction. Determinism:
identical inputs (including identical seed) produce byte-identical
witnesses. No I/O, no clock, no random side-effects (RNG is a local
``np.random.default_rng(seed)``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

__all__ = [
    "MotionalStatus",
    "MotionalInput",
    "MotionalWitness",
    "assess_motional_correlation",
]


_FALSIFIER_TEXT = (
    "DYNAMIC_RELATION_CONFIRMED was returned but the trajectory-ordered "
    "score did NOT exceed the shuffled-trajectory null distribution by "
    "the documented margin. OR: a STATIC_ONLY case (shuffled null and "
    "trajectory score indistinguishable) was reported as dynamic. OR: "
    "the witness produced different verdicts for identical inputs at "
    "fixed seed."
)


class MotionalStatus(str, Enum):
    DYNAMIC_RELATION_CONFIRMED = "DYNAMIC_RELATION_CONFIRMED"
    STATIC_ONLY = "STATIC_ONLY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNKNOWN = "UNKNOWN"


def _trajectory_score(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation of paired increments (lag-1 trajectory score).

    Trajectory ordering enters via ``np.diff``; a shuffled time axis
    destroys this signal because the increments come from a permuted
    series.
    """
    if x.size < 2 or y.size < 2:
        return float("nan")
    dx = np.diff(x)
    dy = np.diff(y)
    sd_x = float(dx.std())
    sd_y = float(dy.std())
    if sd_x == 0.0 or sd_y == 0.0:
        return float("nan")
    return float(np.corrcoef(dx, dy)[0, 1])


def _static_score(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation of the raw values (insensitive to ordering)."""
    if x.size < 2 or y.size < 2:
        return float("nan")
    sd_x = float(x.std())
    sd_y = float(y.std())
    if sd_x == 0.0 or sd_y == 0.0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


@dataclass(frozen=True)
class MotionalInput:
    """One motional-correlation question.

    ``x`` and ``y`` are paired trajectories (same length, finite).
    ``shuffle_count`` is the number of permutation draws that build the
    null. ``margin`` is the absolute gap by which the trajectory score
    must exceed the 95th-percentile shuffled null to be called dynamic.
    ``minimum_length`` is the smallest series length below which the
    witness returns INSUFFICIENT_DATA. ``seed`` makes the shuffled null
    deterministic.
    """

    x: tuple[float, ...]
    y: tuple[float, ...]
    shuffle_count: int
    margin: float
    minimum_length: int
    seed: int

    def __post_init__(self) -> None:
        for name, series in (("x", self.x), ("y", self.y)):
            if not isinstance(series, tuple):
                raise TypeError(f"{name} must be a tuple of floats")
            for i, v in enumerate(series):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise TypeError(f"{name}[{i}] must be a finite float")
                if not np.isfinite(float(v)):
                    raise ValueError(f"{name}[{i}] must be finite (got {v!r})")
        if len(self.x) != len(self.y):
            raise ValueError(f"x and y must have equal length (got {len(self.x)} vs {len(self.y)})")

        if not isinstance(self.shuffle_count, int) or isinstance(self.shuffle_count, bool):
            raise TypeError("shuffle_count must be a non-negative int")
        if self.shuffle_count < 0:
            raise ValueError(f"shuffle_count must be >= 0 (got {self.shuffle_count!r})")

        if not isinstance(self.margin, (int, float)) or isinstance(self.margin, bool):
            raise TypeError("margin must be a finite, non-negative float")
        if not np.isfinite(float(self.margin)):
            raise ValueError(f"margin must be finite (got {self.margin!r})")
        if float(self.margin) < 0.0:
            raise ValueError(f"margin must be >= 0 (got {self.margin!r})")

        if not isinstance(self.minimum_length, int) or isinstance(self.minimum_length, bool):
            raise TypeError("minimum_length must be a non-negative int")
        if self.minimum_length < 0:
            raise ValueError(f"minimum_length must be >= 0 (got {self.minimum_length!r})")

        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("seed must be an int")


@dataclass(frozen=True)
class MotionalWitness:
    """One motional-correlation verdict."""

    status: MotionalStatus
    dynamic_relation_detected: bool
    static_correlation: float
    trajectory_relation: float
    null_p95: float
    margin_used: float
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_motional_correlation(input_: MotionalInput) -> MotionalWitness:
    """Pure dynamic-relation classifier.

    Priority (first failing condition wins):
        1. len < minimum_length          → INSUFFICIENT_DATA
        2. trajectory or static is NaN   → UNKNOWN
        3. trajectory score ≤ p95(null) + margin → STATIC_ONLY
        4. otherwise                     → DYNAMIC_RELATION_CONFIRMED
    """
    n = len(input_.x)
    x_arr = np.asarray(input_.x, dtype=float)
    y_arr = np.asarray(input_.y, dtype=float)

    static = _static_score(x_arr, y_arr)
    traj = _trajectory_score(x_arr, y_arr)

    rng = np.random.default_rng(input_.seed)
    null_scores: list[float] = []
    if n >= 2 and input_.shuffle_count > 0 and np.isfinite(traj):
        for _ in range(input_.shuffle_count):
            permuted = rng.permutation(y_arr)
            score = _trajectory_score(x_arr, permuted)
            if np.isfinite(score):
                null_scores.append(abs(score))
    null_p95 = float(np.quantile(null_scores, 0.95)) if null_scores else float("nan")

    def _build(
        status: MotionalStatus,
        *,
        dynamic: bool,
        reason: str,
    ) -> MotionalWitness:
        evidence = MappingProxyType(
            {
                "n": n,
                "minimum_length": input_.minimum_length,
                "shuffle_count": input_.shuffle_count,
                "static_correlation": static,
                "trajectory_relation": traj,
                "null_p95": null_p95,
                "margin": float(input_.margin),
                "null_sample_count": len(null_scores),
                "seed": input_.seed,
            }
        )
        return MotionalWitness(
            status=status,
            dynamic_relation_detected=dynamic,
            static_correlation=static,
            trajectory_relation=traj,
            null_p95=null_p95,
            margin_used=float(input_.margin),
            reason=reason,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if n < input_.minimum_length:
        return _build(
            MotionalStatus.INSUFFICIENT_DATA,
            dynamic=False,
            reason="SERIES_BELOW_MINIMUM_LENGTH",
        )

    if not np.isfinite(traj) or not np.isfinite(static):
        return _build(
            MotionalStatus.UNKNOWN,
            dynamic=False,
            reason="DEGENERATE_SERIES_NO_VARIANCE",
        )

    if not np.isfinite(null_p95) or abs(traj) <= null_p95 + float(input_.margin):
        return _build(
            MotionalStatus.STATIC_ONLY,
            dynamic=False,
            reason="TRAJECTORY_SCORE_INDISTINGUISHABLE_FROM_NULL",
        )

    return _build(
        MotionalStatus.DYNAMIC_RELATION_CONFIRMED,
        dynamic=True,
        reason="OK_TRAJECTORY_BEATS_SHUFFLED_NULL",
    )
