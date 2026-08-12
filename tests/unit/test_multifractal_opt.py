# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for fractional Lévy updates used by FHMC agents."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from geosync_hpc.multifractal_opt import fractional_update  # noqa: E402


def test_fractional_update_descends_without_noise() -> None:
    param = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float32))
    grad = torch.tensor([0.5], dtype=torch.float32)

    fractional_update([param], [grad], eta=0.2, eta_f=0.0, alpha=1.5)

    assert param.item() == pytest.approx(0.9, rel=1e-6)


def test_fractional_update_respects_state_mask() -> None:
    param = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float32))
    grad = torch.tensor([0.5], dtype=torch.float32)

    np.random.seed(0)
    fractional_update(
        [param],
        [grad],
        eta=0.2,
        eta_f=0.05,
        alpha=1.5,
        mask_states=("SLEEP",),
        current_state="WAKE",
    )

    assert param.item() == pytest.approx(0.9, rel=1e-6)


def test_fractional_update_injects_noise_when_allowed() -> None:
    param = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float32))
    grad = torch.tensor([0.5], dtype=torch.float32)

    np.random.seed(0)
    fractional_update(
        [param],
        [grad],
        eta=0.2,
        eta_f=0.05,
        alpha=1.5,
        mask_states=("WAKE", "SLEEP"),
        current_state="WAKE",
    )

    expected = 1.0 - 0.2 * 0.5 + 0.05 * 4.40839827218306
    assert param.item() == pytest.approx(expected, rel=1e-6)
