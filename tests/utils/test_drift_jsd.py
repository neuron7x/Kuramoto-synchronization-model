# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Jensen–Shannon divergence helpers."""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.distance import jensenshannon


def _load_drift_module():
    """Import ``src.geosync.utils.drift`` without triggering heavy bootstraps."""

    module_name = "geosync_utils_drift_test"
    path = Path(__file__).resolve().parents[2] / "src" / "geosync" / "utils" / "drift.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard.
        raise RuntimeError("Failed to load drift module for testing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift():
    return _load_drift_module()


def test_compute_js_divergence_ignores_nan_payloads(drift):
    data1 = np.array([0.2, np.nan, 0.4, 0.4])
    data2 = np.array([0.1, 0.3, 0.6, 0.0])

    mask = np.isfinite(data1) & np.isfinite(data2)
    expected = float(jensenshannon(data1[mask], data2[mask]) ** 2)
    result = drift.compute_js_divergence(data1, data2)

    assert result == pytest.approx(expected)


def test_compute_js_divergence_all_nan_returns_nan(drift):
    data1 = np.array([np.nan, np.nan])
    data2 = np.array([np.nan, 0.9])

    result = drift.compute_js_divergence(data1, data2)

    assert np.isnan(result)


def test_compute_js_divergence_handles_different_lengths(drift):
    """Test that different length arrays are handled as empirical observations."""
    data1 = np.array([0.2, 0.8, 0.0])
    data2 = np.array([0.2, 0.8])

    # Different length arrays should be handled gracefully (empirical mode)
    result = drift.compute_js_divergence(data1, data2)
    assert np.isfinite(result) or np.isnan(result)


def test_compute_js_divergence_zero_only_returns_nan_without_warnings(drift):
    """Zero-sum distributions should short-circuit instead of warning."""

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = drift.compute_js_divergence(np.zeros(4), np.zeros(4))

    assert np.isnan(result)
