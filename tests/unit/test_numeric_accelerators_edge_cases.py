# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib
import sys
from typing import Iterable

import numpy as np
import pytest

from core.accelerators import convolve, quantiles, sliding_windows


def test_sliding_windows_validates_arguments() -> None:
    data = np.arange(5, dtype=float)
    with pytest.raises(ValueError):
        sliding_windows(data, window=0)
    with pytest.raises(ValueError):
        sliding_windows(data, window=2, step=0)


def test_sliding_windows_handles_short_input() -> None:
    data = np.arange(3, dtype=float)
    result = sliding_windows(data, window=5, use_rust=False)
    assert result.shape == (0, 5)


@pytest.mark.parametrize(
    "probabilities",
    [
        np.array([[0.1, 0.2]]),
        [float("nan")],
        [-0.1, 0.5],
    ],
)
def test_quantiles_validates_probabilities(probabilities: Iterable[float]) -> None:
    data = np.linspace(0.0, 1.0, 4)
    with pytest.raises(ValueError):
        quantiles(data, probabilities, use_rust=False)


def test_quantiles_empty_input_returns_nan() -> None:
    data = np.array([], dtype=float)
    result = quantiles(data, [0.25, 0.5, 0.75], use_rust=False)
    assert np.isnan(result).all()


def test_convolve_rejects_invalid_mode() -> None:
    signal = np.array([1.0, 2.0], dtype=float)
    kernel = np.array([1.0], dtype=float)
    with pytest.raises(ValueError):
        convolve(signal, kernel, mode="diagonal", use_rust=False)


def test_python_vector_validator_rejects_nested_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "numpy", None)
    importlib.invalidate_caches()
    sys.modules.pop("core.accelerators.numeric", None)
    numeric = importlib.import_module("core.accelerators.numeric")

    with pytest.raises(ValueError):
        numeric._ensure_vector_python([[1.0, 2.0]])

    sys.modules.pop("core.accelerators.numeric", None)
