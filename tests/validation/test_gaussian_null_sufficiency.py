# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Task 02: i.i.d. Gaussian null is inadequate for autocorrelated series."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "audit_gns", _ROOT / "tools" / "validation" / "audit_gaussian_null_sufficiency.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_a = _load()


def test_iid_gaussian_is_inadequate_for_autocorrelated() -> None:
    audit = _a.run_audit(n=4096, phi=0.8, seed=7)
    assert audit["iid_gaussian_is_inadequate_for_autocorrelated_series"] is True
    assert abs(audit["iid_gaussian_lag1_autocorr"]) < _a.AUTOCORR_THRESHOLD
    assert audit["autocorrelated_lag1_autocorr"] >= _a.AUTOCORR_THRESHOLD
    assert audit["is_predictive_claim"] is False


def test_lag1_autocorr_white_noise_near_zero() -> None:
    rng = np.random.default_rng(0)
    assert abs(_a.lag1_autocorr(rng.standard_normal(8192))) < 0.1


def test_main_runs() -> None:
    assert _a.main(["--n", "512"]) == 0
