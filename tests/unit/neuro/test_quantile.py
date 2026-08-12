# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math

import numpy as np
import pytest

from core.neuro.quantile import P2Quantile


def test_quantile_monotonic_updates() -> None:
    q = P2Quantile(0.75)
    data = np.linspace(-1.0, 1.0, 21)
    outputs = [q.update(float(x)) for x in data]
    assert math.isclose(outputs[-1], np.quantile(data, 0.75), rel_tol=1e-9)
    assert outputs == sorted(outputs)


def test_quantile_handles_duplicate_values() -> None:
    q = P2Quantile(0.25)
    for value in [1.0, 1.0, 1.0, 2.0, -1.0, -1.0]:
        q.update(value)
    assert math.isfinite(q.quantile)
    assert -1.0 <= q.quantile <= 2.0


def test_quantile_reports_nan_before_updates() -> None:
    q = P2Quantile(0.5)
    assert math.isnan(q.quantile)


def test_invalid_quantile_raises() -> None:
    for p in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError):
            P2Quantile(p)
