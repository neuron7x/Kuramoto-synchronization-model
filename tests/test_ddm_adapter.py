# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from geosync.core.neuro.dopamine import adapt_ddm_parameters


def test_ddm_adapter_increases_drift_and_reduces_boundary() -> None:
    adjustment = adapt_ddm_parameters(0.8, base_drift=0.5, base_boundary=1.0)
    assert adjustment.drift > 0.5
    assert adjustment.boundary < 1.0


def test_ddm_adapter_handles_low_dopamine() -> None:
    adjustment = adapt_ddm_parameters(0.1, base_drift=0.5, base_boundary=1.0)
    assert adjustment.drift < 0.5
    assert adjustment.boundary > 0.7


def test_ddm_adapter_validation() -> None:
    with pytest.raises(ValueError):
        adapt_ddm_parameters(float("nan"), 0.5, 1.0)
    with pytest.raises(ValueError):
        adapt_ddm_parameters(0.5, -0.1, 1.0)
    with pytest.raises(ValueError):
        adapt_ddm_parameters(0.5, 0.5, -1.0)
