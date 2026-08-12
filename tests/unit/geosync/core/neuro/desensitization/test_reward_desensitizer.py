# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math

from geosync.core.neuro.desensitization import (
    RewardDesensitizer,
    RewardDesensitizerConfig,
)


def test_reward_desensitizer_normalization_bounds() -> None:
    des = RewardDesensitizer(RewardDesensitizerConfig(max_abs=4.0))
    norm, state = des.update(1.5)
    assert math.isfinite(norm)
    assert abs(norm) <= state["scale"] * 4.0
    assert 0.0 <= state["refractory"] <= 5.0
