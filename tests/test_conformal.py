# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the conformal calibration module."""

from __future__ import annotations

import numpy as np

from geosync_hpc.conformal import ConformalCQR


def test_cqr_qhat_nonnegative() -> None:
    cqr = ConformalCQR(alpha=0.1, decay=0.01, window=50)
    lower = np.array([-0.01] * 100)
    upper = np.array([0.01] * 100)
    targets = np.concatenate([np.random.normal(0, 0.005, 95), np.array([0.05] * 5)])
    cqr.fit_calibrate(lower, upper, targets)
    assert cqr.qhat is not None and cqr.qhat >= 0.0
