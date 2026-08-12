# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Task 03: structure-preserving null enforcement primitive."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "null_adequacy", _ROOT / "tools" / "validation" / "null_adequacy.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_na = _load()


def _ar1(n: int, phi: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    out[0] = rng.standard_normal()
    for t in range(1, n):
        out[t] = phi * out[t - 1] + rng.standard_normal()
    return out


def test_autocorrelated_series_with_iid_null_is_refused() -> None:
    with pytest.raises(ValueError, match="structure-preserving"):
        _na.require_structure_preserving_null(_ar1(2048, 0.8, 1), "gaussian")


def test_autocorrelated_series_with_structure_preserving_null_ok() -> None:
    _na.require_structure_preserving_null(_ar1(2048, 0.8, 1), "iaaft")


def test_white_noise_with_iid_null_ok() -> None:
    rng = np.random.default_rng(0)
    _na.require_structure_preserving_null(rng.standard_normal(2048), "gaussian")


def test_unknown_null_kind_refused() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="unknown null"):
        _na.require_structure_preserving_null(rng.standard_normal(64), "magic")
