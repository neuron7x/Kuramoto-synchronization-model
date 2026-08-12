# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import warnings

import numpy as np

from core.indicators.kuramoto import compute_phase, kuramoto_order


def test_compute_phase_no_copy_warning():
    data = np.random.randn(256)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = compute_phase(data)
    assert result.shape == data.shape


def test_kuramoto_order_fast_path():
    phases = np.linspace(-np.pi, np.pi, 64)
    value = kuramoto_order(phases)
    assert 0.0 <= float(value) <= 1.0
