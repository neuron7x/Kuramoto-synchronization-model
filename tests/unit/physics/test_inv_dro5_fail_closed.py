# SPDX-License-Identifier: MIT
"""INV-DRO5 — fail-closed rejection of degenerate inputs in derive_gamma.

INV-DRO5 (universal, P0): NaN / ±Inf / constant / rank / short
input → ``ValueError``. Fail-closed; no silent numeric repair.

This test file pins the fail-closed contract that
:func:`core.dro_ara.engine.derive_gamma` must enforce. Prior to
this PR the function silently passed degenerate inputs through to
``_hurst_dfa`` which absorbed them and emitted bogus (gamma, H,
r2) triples — INV-DRO5 was documented in CLAUDE.md but **not**
enforced in code. The PR adds a one-line ``_validate(arr,
min_len=64)`` call at the top of ``derive_gamma``; this file
falsifies the absence of that guard going forward.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.dro_ara.engine import derive_gamma


def test_inv_dro5_rejects_nan_in_input() -> None:
    """NaN anywhere in the input must raise ValueError, not propagate."""
    series = np.full(256, 1.0, dtype=np.float64)
    series[100] = np.nan
    with pytest.raises(ValueError, match="NaN/Inf"):
        derive_gamma(series)


def test_inv_dro5_rejects_positive_inf_in_input() -> None:
    series = np.full(256, 1.0, dtype=np.float64)
    series[50] = np.inf
    with pytest.raises(ValueError, match="NaN/Inf"):
        derive_gamma(series)


def test_inv_dro5_rejects_negative_inf_in_input() -> None:
    series = np.full(256, 1.0, dtype=np.float64)
    series[200] = -np.inf
    with pytest.raises(ValueError, match="NaN/Inf"):
        derive_gamma(series)


def test_inv_dro5_rejects_constant_series() -> None:
    """A constant series carries no Hurst signal; must reject."""
    series = np.full(256, 3.14, dtype=np.float64)
    with pytest.raises(ValueError, match="constant"):
        derive_gamma(series)


def test_inv_dro5_rejects_too_short_input() -> None:
    """Below the 64-sample DFA floor: must reject."""
    series = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    with pytest.raises(ValueError, match=r"need ≥64"):
        derive_gamma(series)


def test_inv_dro5_rejects_non_one_dim_input() -> None:
    """Non-1D ndarray must reject; rank guard is part of fail-closed."""
    arr2d = np.ones((16, 16), dtype=np.float64)
    with pytest.raises(ValueError, match="1-D"):
        derive_gamma(arr2d)


def test_inv_dro5_accepts_legitimate_random_walk() -> None:
    """Sanity inverse: a clean 256-sample random walk must NOT raise.

    Without this companion, a regression that loosened the
    floor or relaxed `_validate` could pass the rejection tests
    while breaking the legitimate happy-path. The pair forms a
    boundary witness.
    """
    rng = np.random.default_rng(seed=42)
    series = np.cumsum(rng.standard_normal(256))
    gamma, H, r2 = derive_gamma(series)
    assert isinstance(gamma, float)
    assert isinstance(H, float)
    assert isinstance(r2, float)
    # All three fields finite per INV-HPC2.
    for name, val in [("gamma", gamma), ("H", H), ("r2", r2)]:
        assert np.isfinite(val), (
            f"INV-DRO5 happy-path VIOLATED: {name}={val!r} non-finite "
            "on a clean random-walk input. The fail-closed guard must "
            "not strip valid data."
        )
