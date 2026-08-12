# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math

from core.neuro.sizing import SizerConfig, position_size, precision_weight, pulse_weight


def test_pulse_weight_clamps_between_zero_and_one() -> None:
    cfg = SizerConfig(min_pulse=0.1, max_pulse=0.3)
    assert pulse_weight(0.0, cfg) == 0.0
    assert 0.0 < pulse_weight(0.2, cfg) < 1.0
    assert pulse_weight(0.5, cfg) == 1.0


def test_precision_weight_is_sigmoid() -> None:
    low = precision_weight(0.1)
    mid = precision_weight(1.0)
    high = precision_weight(10.0)
    assert 0.0 <= low < mid < high <= 1.0
    assert math.isclose(mid, 0.5, rel_tol=1e-3)


def test_position_size_scales_with_volatility() -> None:
    cfg = SizerConfig(target_vol=0.02, max_leverage=1.0, min_pulse=0.0, max_pulse=0.5)
    long_pos = position_size(direction=1, pi=2.0, S=0.25, est_sigma=0.01, cfg=cfg)
    short_pos = position_size(direction=-1, pi=2.0, S=0.25, est_sigma=0.01, cfg=cfg)
    assert long_pos == -short_pos
    assert 0.0 < long_pos <= cfg.max_leverage


def test_position_size_returns_zero_for_safe_guards() -> None:
    cfg = SizerConfig(min_pulse=0.2, max_pulse=0.3)
    assert position_size(direction=0, pi=10.0, S=0.5, est_sigma=0.01, cfg=cfg) == 0.0
    assert position_size(direction=1, pi=10.0, S=0.1, est_sigma=0.01, cfg=cfg) == 0.0
    assert position_size(direction=1, pi=10.0, S=0.5, est_sigma=0.0, cfg=cfg) == 0.0
