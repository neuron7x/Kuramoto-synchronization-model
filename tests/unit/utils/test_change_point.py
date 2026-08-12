# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for change point detection helpers."""

from __future__ import annotations

import numpy as np

from utils.change_point import cusum_score, vol_shock


def test_cusum_score_handles_empty_and_constant_series() -> None:
    assert cusum_score([]) == 0.0
    assert cusum_score([1.0] * 20) == 0.0


def test_cusum_score_counts_multiple_alarms() -> None:
    abrupt_shift = [0.0] * 10 + [10.0] * 5

    score = cusum_score(abrupt_shift, drift=0.0, threshold=5.0)

    assert score == 2.0


def test_vol_shock_requires_sufficient_history() -> None:
    assert vol_shock([0.1, 0.2], window=3) == 0.0


def test_vol_shock_signals_volatility_changes() -> None:
    spike_series = [0.0, 1.0, 0.0, 0.0, 5.0, 0.0]
    calm_series = [0.0, 5.0, 0.0, 0.0, 1.0, 0.0]

    spike = vol_shock(spike_series, window=3)
    compression = vol_shock(calm_series, window=3)

    assert np.isclose(spike, 4.0, atol=1e-6)
    assert compression < 0.0
