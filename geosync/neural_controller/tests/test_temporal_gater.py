# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from ..core.temporal_gater import TemporalGater


def test_temporal_gater_discrete_updates() -> None:
    gater = TemporalGater(frequency=0.5, cadence="step")
    values: list[int] = []
    updates: list[bool] = []
    counter = 0

    def compute() -> int:
        nonlocal counter
        counter += 1
        return counter

    for _ in range(5):
        value, updated = gater.step(compute)
        values.append(value)
        updates.append(updated)

    assert values == [1, 1, 2, 2, 3]
    assert updates == [True, False, True, False, True]
