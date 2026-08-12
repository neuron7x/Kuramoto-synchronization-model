# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DDMAdjustment:
    """Container describing drift and boundary adjustments."""

    drift: float
    boundary: float


@dataclass(frozen=True)
class DDMThresholds:
    """Policy temperature scaling and gate thresholds derived from DDM."""

    temperature_scale: float
    go_threshold: float
    hold_threshold: float
    no_go_threshold: float


def adapt_ddm_parameters(
    dopamine_level: float,
    base_drift: float,
    base_boundary: float,
    drift_gain: float = 0.5,
    boundary_gain: float = 0.3,
    min_boundary: float = 0.1,
) -> DDMAdjustment:
    """Translate dopamine level into DDM drift/boundary adjustments.

    Dopamine increases drift (action confidence) while reducing the boundary to
    accelerate exploitative decisions. Gains are bounded to maintain numerical
    stability.
    """

    if not math.isfinite(dopamine_level):
        raise ValueError("dopamine_level must be finite")
    if not math.isfinite(base_drift) or base_drift <= 0.0:
        raise ValueError("base_drift must be positive and finite")
    if not math.isfinite(base_boundary) or base_boundary <= 0.0:
        raise ValueError("base_boundary must be positive and finite")
    dopamine_level = min(1.0, max(0.0, dopamine_level))  # INV-DA3: DA ∈ [0,1]

    centred = dopamine_level - 0.5
    drift = base_drift * (1.0 + drift_gain * centred * 2.0)
    boundary = max(min_boundary, base_boundary * (1.0 - boundary_gain * dopamine_level))
    return DDMAdjustment(drift=drift, boundary=boundary)


def ddm_thresholds(
    v: float,
    a: float,
    t0: float,
    *,
    temp_gain: float,
    threshold_gain: float,
    hold_gain: float,
    min_temp_scale: float,
    max_temp_scale: float,
    baseline_a: float,
    baseline_t0: float,
    eps: float,
) -> DDMThresholds:
    """Project DDM parameters into policy temperature and Go/No-Go thresholds."""

    for name, value in ("v", v), ("a", a), ("t0", t0):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if a <= 0.0:
        raise ValueError("a must be positive")
    if t0 < 0.0:
        raise ValueError("t0 must be non-negative")
    if eps <= 0.0:
        raise ValueError("eps must be positive")
    if min_temp_scale <= 0.0 or max_temp_scale <= 0.0:
        raise ValueError("temperature scales must be positive")
    if min_temp_scale > max_temp_scale:
        raise ValueError("min_temp_scale must be ≤ max_temp_scale")

    coherence = math.tanh(v / (a + eps))
    boundary_delta = math.tanh((a - baseline_a) / (baseline_a + eps))
    if baseline_t0 > 0.0:
        hold_drive = math.tanh((t0 - baseline_t0) / (baseline_t0 + eps))
    else:
        hold_drive = math.tanh(t0)

    temperature_scale = 1.0 - temp_gain * coherence + temp_gain * boundary_delta
    temperature_scale = min(max_temp_scale, max(min_temp_scale, temperature_scale))

    go_threshold = 0.5 + threshold_gain * (coherence - boundary_delta)
    no_go_threshold = 0.5 - threshold_gain * (coherence + boundary_delta)
    hold_threshold = 0.5 + hold_gain * hold_drive

    go_threshold = min(1.0, max(0.0, go_threshold))  # INV-DA3: threshold ∈ [0,1]
    no_go_threshold = min(1.0, max(0.0, no_go_threshold))  # INV-DA3: threshold ∈ [0,1]
    hold_threshold = min(1.0, max(0.0, hold_threshold))  # INV-DA3: threshold ∈ [0,1]

    if go_threshold < no_go_threshold:
        mid = (go_threshold + no_go_threshold) / 2.0
        go_threshold = mid
        no_go_threshold = mid

    return DDMThresholds(
        temperature_scale=float(temperature_scale),
        go_threshold=float(go_threshold),
        hold_threshold=float(hold_threshold),
        no_go_threshold=float(no_go_threshold),
    )
