# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pytest

from geosync.core.neuro.nak.metrics import rolling_std


def test_rolling_std_shapes() -> None:
    data = np.arange(10, dtype=float)
    result = rolling_std(data, window=5)
    assert result.shape == (6,)
    assert pytest.approx(result[-1], rel=1e-6) == np.std(data[-5:])


def test_rolling_std_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        rolling_std(np.arange(4.0), window=0)
    with pytest.raises(ValueError):
        rolling_std(np.arange(4.0), window=10)
