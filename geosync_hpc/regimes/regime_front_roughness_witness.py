# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regime-front roughness witness — engineering analog of KPZ-class discipline.

pattern_id:        P7_REGIME_FRONT_ROUGHNESS
source_id:         S7_KPZ_2D_UNIVERSALITY
claim_tier:        ENGINEERING_ANALOG

A regime boundary may roughen; smooth-transition assumption is not
default truth. The named lie blocked here is "regime transitions are
smooth unless proven otherwise". A boundary is classified as
ROUGH_FRONT only when its measured roughness exceeds a shuffled-
trajectory null by a documented threshold.

Statuses:
    ROUGH_FRONT          observed roughness exceeds shuffled-null
                          roughness by ``roughness_threshold``
    SMOOTH_FRONT         observed roughness sits below the null;
                          smooth-front baseline holds
    NULL_MATCH           observed roughness indistinguishable from
                          shuffled null within threshold
    INSUFFICIENT_HISTORY series shorter than ``minimum_length`` or
                          window
    INVALID_INPUT        non-finite values or rejected shape

Non-claims: no one-to-one correspondence with KPZ physics; no forecast,
signal, or trading interpretation. Determinism: identical inputs at
fixed seed produce byte-identical witnesses; RNG is local.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

__all__ = [
    "FrontStatus",
    "FrontInput",
    "FrontWitness",
    "assess_regime_front_roughness",
]


_FALSIFIER_TEXT = (
    "ROUGH_FRONT was returned but the observed roughness did NOT exceed "
    "the shuffled-trajectory null roughness by the documented "
    "roughness_threshold. OR: the shuffled-null comparison was bypassed "
    "and any non-zero roughness was reported as ROUGH_FRONT. OR: the "
    "witness produced different verdicts for identical inputs at fixed "
    "seed."
)


class FrontStatus(str, Enum):
    ROUGH_FRONT = "ROUGH_FRONT"
    SMOOTH_FRONT = "SMOOTH_FRONT"
    NULL_MATCH = "NULL_MATCH"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INVALID_INPUT = "INVALID_INPUT"


def _roughness(series: np.ndarray, window: int) -> float:
    """Mean local standard deviation in non-overlapping windows.

    A perfectly straight (smooth) boundary has roughness ≈ 0; a
    KPZ-class roughened boundary has roughness > 0 with magnitude
    determined by window size.
    """
    n = series.size
    if n < window or window < 2:
        return float("nan")
    n_windows = n // window
    if n_windows == 0:
        return float("nan")
    chunks = series[: n_windows * window].reshape(n_windows, window)
    return float(chunks.std(axis=1, ddof=0).mean())


@dataclass(frozen=True)
class FrontInput:
    """One regime-front-roughness question.

    ``boundary_series`` and ``time_index`` are paired (same length,
    finite). ``time_index`` must be strictly monotonic increasing.
    ``window`` is the local-stdev window used to compute roughness.
    ``null_shuffle_seed`` makes the shuffled null deterministic.
    ``roughness_threshold`` is the absolute gap by which observed
    roughness must exceed the shuffled-null 95th percentile to be
    called ROUGH_FRONT. ``minimum_length`` is the smallest series
    length the witness will assess.
    """

    boundary_series: tuple[float, ...]
    time_index: tuple[float, ...]
    window: int
    null_shuffle_seed: int
    roughness_threshold: float
    minimum_length: int

    def __post_init__(self) -> None:
        for name, series in (
            ("boundary_series", self.boundary_series),
            ("time_index", self.time_index),
        ):
            if not isinstance(series, tuple):
                raise TypeError(f"{name} must be a tuple of floats")
            for i, v in enumerate(series):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise TypeError(f"{name}[{i}] must be a finite float")
                if not math.isfinite(float(v)):
                    raise ValueError(f"{name}[{i}] must be finite (got {v!r})")
        if len(self.boundary_series) != len(self.time_index):
            raise ValueError(
                f"boundary_series and time_index must have equal length "
                f"(got {len(self.boundary_series)} vs {len(self.time_index)})"
            )

        for i in range(1, len(self.time_index)):
            if not float(self.time_index[i]) > float(self.time_index[i - 1]):
                raise ValueError(
                    f"time_index must be strictly monotonic increasing (violated at index {i})"
                )

        if not isinstance(self.window, int) or isinstance(self.window, bool):
            raise TypeError("window must be a positive int")
        if self.window < 2:
            raise ValueError(f"window must be >= 2 (got {self.window!r})")

        if not isinstance(self.null_shuffle_seed, int) or isinstance(self.null_shuffle_seed, bool):
            raise TypeError("null_shuffle_seed must be an int")

        if not isinstance(self.roughness_threshold, (int, float)) or isinstance(
            self.roughness_threshold, bool
        ):
            raise TypeError("roughness_threshold must be a finite, non-negative float")
        if not math.isfinite(float(self.roughness_threshold)):
            raise ValueError(
                f"roughness_threshold must be finite (got {self.roughness_threshold!r})"
            )
        if float(self.roughness_threshold) < 0.0:
            raise ValueError(f"roughness_threshold must be >= 0 (got {self.roughness_threshold!r})")

        if not isinstance(self.minimum_length, int) or isinstance(self.minimum_length, bool):
            raise TypeError("minimum_length must be a non-negative int")
        if self.minimum_length < 0:
            raise ValueError(f"minimum_length must be >= 0 (got {self.minimum_length!r})")


@dataclass(frozen=True)
class FrontWitness:
    """One regime-front roughness verdict."""

    status: FrontStatus
    roughness_value: float
    shuffled_null_roughness: float
    exceeds_null: bool
    threshold_used: float
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_regime_front_roughness(input_: FrontInput) -> FrontWitness:
    """Pure roughness classifier with shuffled-null gate.

    Priority (first failing condition wins):
        1. len < minimum_length OR len < window → INSUFFICIENT_HISTORY
        2. observed roughness NaN              → INVALID_INPUT
        3. roughness > null_p95 + threshold    → ROUGH_FRONT
        4. roughness < null_p95 - threshold    → SMOOTH_FRONT
        5. otherwise (within ±threshold)       → NULL_MATCH
    """
    series = np.asarray(input_.boundary_series, dtype=float)
    n = series.size
    threshold = float(input_.roughness_threshold)

    observed = _roughness(series, input_.window) if n >= input_.window else float("nan")

    rng = np.random.default_rng(input_.null_shuffle_seed)
    null_samples: list[float] = []
    if n >= input_.window:
        for _ in range(200):
            permuted = rng.permutation(series)
            r = _roughness(permuted, input_.window)
            if math.isfinite(r):
                null_samples.append(r)
    null_p95 = float(np.quantile(null_samples, 0.95)) if null_samples else float("nan")

    def _build(status: FrontStatus, *, exceeds: bool, reason: str) -> FrontWitness:
        evidence = MappingProxyType(
            {
                "n": n,
                "window": input_.window,
                "minimum_length": input_.minimum_length,
                "roughness_value": observed,
                "shuffled_null_p95": null_p95,
                "null_sample_count": len(null_samples),
                "threshold": threshold,
                "seed": input_.null_shuffle_seed,
            }
        )
        return FrontWitness(
            status=status,
            roughness_value=observed,
            shuffled_null_roughness=null_p95,
            exceeds_null=exceeds,
            threshold_used=threshold,
            reason=reason,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if n < input_.minimum_length or n < input_.window:
        return _build(FrontStatus.INSUFFICIENT_HISTORY, exceeds=False, reason="SERIES_TOO_SHORT")

    if not math.isfinite(observed) or not math.isfinite(null_p95):
        return _build(FrontStatus.INVALID_INPUT, exceeds=False, reason="DEGENERATE_ROUGHNESS")

    if observed > null_p95 + threshold:
        return _build(
            FrontStatus.ROUGH_FRONT,
            exceeds=True,
            reason="OK_ROUGHNESS_EXCEEDS_SHUFFLED_NULL",
        )
    if observed < null_p95 - threshold:
        return _build(
            FrontStatus.SMOOTH_FRONT,
            exceeds=False,
            reason="ROUGHNESS_BELOW_SHUFFLED_NULL",
        )
    return _build(
        FrontStatus.NULL_MATCH,
        exceeds=False,
        reason="ROUGHNESS_INDISTINGUISHABLE_FROM_NULL",
    )
