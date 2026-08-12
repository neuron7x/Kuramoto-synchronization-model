# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based tests for microstructure metrics."""

from __future__ import annotations

import numpy as np
import pytest

from core.metrics.microstructure import hasbrouck_information_impulse


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_hasbrouck_transformation_invariants(seed: int) -> None:
    """The Hasbrouck impulse should be invariant to affine transformations.

    Shifting or rescaling the raw data should not change the statistic because
    the implementation normalizes both the transformed volume and returns.
    """

    rng = np.random.default_rng(seed)
    returns = rng.normal(size=128)
    signed_volume = rng.normal(size=128)

    base = hasbrouck_information_impulse(returns, signed_volume)

    shifted = hasbrouck_information_impulse(returns + 5.0, signed_volume - 3.0)
    assert shifted == pytest.approx(base, rel=1e-9, abs=1e-9)

    scaled = hasbrouck_information_impulse(returns * 2.5, signed_volume * 4.0)
    assert scaled == pytest.approx(base, rel=1e-9, abs=1e-9)
