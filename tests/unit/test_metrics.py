# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np
import pytest

from core.metrics.direction_index import direction_index, skewness
from core.metrics.ism import ism
from core.metrics.volume_profile import (
    cumulative_volume_delta,
    imbalance,
    order_aggression,
)


def test_skewness_of_symmetric_distribution_zero() -> None:
    data = np.concatenate([np.linspace(-1, -0.1, 50), np.linspace(0.1, 1, 50)])
    assert abs(skewness(data)) < 1e-12


def test_direction_index_linear_combination() -> None:
    skew = 0.2
    delta_curv = -0.1
    bias = 0.05
    result = direction_index(skew, delta_curv, bias)
    expected = 0.5 * skew + 0.3 * delta_curv + 0.2 * bias
    assert result == pytest.approx(expected, rel=1e-12)


def test_ism_handles_zero_topology_energy() -> None:
    assert ism(0.5, 0.0) == 0.0
    assert ism(0.2, 2.0, eta=0.5) == pytest.approx(0.05)


def test_volume_profile_metrics() -> None:
    buys = np.array([10, 5])
    sells = np.array([3, 7])
    delta = cumulative_volume_delta(buys, sells)
    assert delta.tolist() == [7, 5]
    imb = imbalance(buys, sells)
    assert pytest.approx(imb, rel=1e-12) == (15 - 10) / 25
    assert imbalance(np.zeros(2), np.zeros(2)) == 0.0
    assert order_aggression(0.0, 0.0) == 0.0
    assert pytest.approx(order_aggression(3.0, 1.0), rel=1e-12) == 0.5
