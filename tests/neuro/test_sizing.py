# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from core.neuro.sizing import SizerConfig, position_size


def test_size_zeros_when_no_signal():
    cfg = SizerConfig()
    assert position_size(0, 10.0, 0.2, 0.01, cfg) == 0.0


def test_size_grows_with_pulse_and_precision():
    cfg = SizerConfig()
    s1 = position_size(+1, 0.5, 0.01, 0.01, cfg)
    s2 = position_size(+1, 5.0, 0.2, 0.01, cfg)
    assert abs(s2) > abs(s1)
