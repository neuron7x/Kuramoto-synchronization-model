# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np

from core.phase.detector import PhaseThresholds, composite_transition, phase_flags


def test_phase_flags_detects_proto_state() -> None:
    state = phase_flags(R=0.2, dH=0.1, kappa_mean=0.05, H=1.0)
    assert state == "proto"


def test_phase_flags_emergent_requires_negative_curvature() -> None:
    state = phase_flags(R=0.8, dH=-0.2, kappa_mean=-0.1, H=0.5)
    assert state == "emergent"


def test_phase_flags_precognitive_when_entropy_declines() -> None:
    state = phase_flags(R=0.55, dH=-0.05, kappa_mean=0.0, H=0.8)
    assert state == "precognitive"


def test_phase_flags_post_emergent_requires_positive_entropy_shift() -> None:
    state = phase_flags(R=0.65, dH=0.12, kappa_mean=0.0, H=0.9)
    assert state == "post-emergent"


def test_phase_flags_neutral_when_no_category_matches() -> None:
    state = phase_flags(R=0.85, dH=0.03, kappa_mean=0.05, H=0.4)
    assert state == "neutral"


def test_phase_flags_respect_custom_thresholds() -> None:
    thresholds = PhaseThresholds(
        proto_R_max=0.3,
        proto_entropy_slope_min=-0.05,
        emergent_R_min=0.6,
        emergent_entropy_slope_max=-0.05,
        emergent_kappa_max=-0.02,
        neutral_band=(0.3, 0.55),
    )

    proto_state = phase_flags(R=0.29, dH=-0.01, kappa_mean=-0.01, H=0.9, thresholds=thresholds)
    emergent_state = phase_flags(
        R=0.7,
        dH=-0.08,
        kappa_mean=-0.05,
        H=0.6,
        thresholds=thresholds,
    )

    assert proto_state == "proto"
    assert emergent_state == "emergent"


def test_composite_transition_weighted_sum_behavior() -> None:
    R = 0.6
    dH = -0.1
    kappa = -0.2
    H = 1.0
    result = composite_transition(R, dH, kappa, H)
    expected = 0.4 * R + 0.3 * (-dH) + 0.3 * (-kappa)
    assert np.isclose(result, expected)
