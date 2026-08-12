# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PhaseThresholds:
    """Configurable thresholds for phase classification."""

    proto_R_max: float = 0.4
    proto_entropy_slope_min: float = 0.0
    emergent_R_min: float = 0.75
    emergent_entropy_slope_max: float = -1e-8
    emergent_kappa_max: float = -1e-8
    neutral_band: tuple[float, float] = (0.4, 0.7)


def phase_flags(
    R: float,
    dH: float,
    kappa_mean: float,
    H: float,
    thresholds: PhaseThresholds | None = None,
) -> Literal["proto", "precognitive", "emergent", "post-emergent", "neutral"]:
    """Derive qualitative market phase labels from indicator summary stats."""

    cfg = thresholds or PhaseThresholds()
    if R < cfg.proto_R_max and dH > cfg.proto_entropy_slope_min:
        return "proto"
    low, high = cfg.neutral_band
    if low <= R <= high and dH <= 0:
        return "precognitive"
    if (
        R >= cfg.emergent_R_min
        and dH <= cfg.emergent_entropy_slope_max
        and kappa_mean <= cfg.emergent_kappa_max
    ):
        return "emergent"
    if R <= high and dH > cfg.proto_entropy_slope_min:
        return "post-emergent"
    return "neutral"


def composite_transition(R: float, dH: float, kappa_mean: float, H: float) -> float:
    """Blended transition score; tune weights via walk-forward analysis."""

    weights = (0.4, 0.3, 0.3)
    return float(weights[0] * R + weights[1] * (-dH) + weights[2] * (-kappa_mean))
