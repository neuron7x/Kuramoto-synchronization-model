# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the deterministic null-baseline descriptor fixtures.

Covers the null-baseline contract properties: determinism for a fixed
seed, sensitivity to the seed, length / shape fidelity, metadata
completeness and boundary disclaimer, fail-closed rejection of n <= 0 and
invalid seeds, the never-non-finite guarantee, power-spectrum preservation
of the surrogate, and the absence of forecasting / trading language on the
metadata surface.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, cast

import numpy as np
import pytest

from analytics.signals.null_baseline import (
    CLAIM_BOUNDARY,
    make_constant_null,
    make_gaussian_null,
    make_phase_shuffled_surrogate,
)

_REQUIRED_META_KEYS = {
    "method",
    "seed",
    "length",
    "dtype",
    "claim_boundary",
    "not_predictive_claim",
    "not_financial_advice",
    "research_only",
}


# ── determinism for the same seed ────────────────────────────────────────
def test_gaussian_deterministic_for_same_seed() -> None:
    a, meta_a = make_gaussian_null(n=64, seed=11)
    b, meta_b = make_gaussian_null(n=64, seed=11)
    np.testing.assert_array_equal(a, b)
    assert dict(meta_a) == dict(meta_b)


def test_surrogate_deterministic_for_same_seed() -> None:
    series = np.sin(np.linspace(0.0, 8.0, 128)).tolist()
    a, _ = make_phase_shuffled_surrogate(series, seed=3)
    b, _ = make_phase_shuffled_surrogate(series, seed=3)
    np.testing.assert_array_equal(a, b)


# ── different seed yields a different series ──────────────────────────────
def test_gaussian_different_seed_differs() -> None:
    a, _ = make_gaussian_null(n=64, seed=1)
    b, _ = make_gaussian_null(n=64, seed=2)
    assert not np.array_equal(a, b)


def test_surrogate_different_seed_differs() -> None:
    series = np.sin(np.linspace(0.0, 8.0, 128)).tolist()
    a, _ = make_phase_shuffled_surrogate(series, seed=1)
    b, _ = make_phase_shuffled_surrogate(series, seed=2)
    assert not np.array_equal(a, b)


# ── length / shape fidelity ──────────────────────────────────────────────
def test_lengths_and_dtype() -> None:
    g, _ = make_gaussian_null(n=17, seed=0)
    c, _ = make_constant_null(n=17, value=2.5)
    s, _ = make_phase_shuffled_surrogate([float(i) for i in range(17)], seed=0)
    for arr in (g, c, s):
        assert arr.shape == (17,)
        assert arr.dtype == np.float64


def test_constant_null_is_constant() -> None:
    arr, meta = make_constant_null(n=10, value=4.0)
    assert np.all(arr == 4.0)
    assert arr.var() == 0.0
    assert meta["seed"] is None


# ── metadata completeness and boundary disclaimer ────────────────────────
def test_metadata_completeness_and_boundary() -> None:
    for arr_meta in (
        make_gaussian_null(n=8, seed=5),
        make_constant_null(n=8),
        make_phase_shuffled_surrogate([float(i) for i in range(8)], seed=5),
    ):
        _, meta = arr_meta
        assert _REQUIRED_META_KEYS.issubset(meta.keys())
        assert meta["claim_boundary"] == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
        assert meta["not_predictive_claim"] is True
        assert meta["not_financial_advice"] is True
        assert meta["length"] == 8


def test_metadata_is_immutable() -> None:
    _, meta = make_gaussian_null(n=4, seed=0)
    assert isinstance(meta, MappingProxyType)
    mutable_view = cast(Any, meta)
    with pytest.raises(TypeError):
        mutable_view["method"] = "tampered"


# ── fail closed on n <= 0 and invalid seed ───────────────────────────────
@pytest.mark.parametrize("bad_n", [0, -1, -100])
def test_fail_closed_on_nonpositive_length(bad_n: int) -> None:
    with pytest.raises(ValueError):
        make_gaussian_null(n=bad_n, seed=0)
    with pytest.raises(ValueError):
        make_constant_null(n=bad_n)


@pytest.mark.parametrize("bad_seed", [-1, -7])
def test_fail_closed_on_negative_seed(bad_seed: int) -> None:
    with pytest.raises(ValueError):
        make_gaussian_null(n=4, seed=bad_seed)
    with pytest.raises(ValueError):
        make_phase_shuffled_surrogate([1.0, 2.0, 3.0], seed=bad_seed)


def test_fail_closed_on_bool_arguments() -> None:
    # ``bool`` is an ``int`` subclass; it must be rejected, not coerced.
    # ``cast`` keeps the static contract intact while exercising the
    # runtime guard against a boolean masquerading as an int.
    with pytest.raises(ValueError):
        make_gaussian_null(n=cast(int, True), seed=0)
    with pytest.raises(ValueError):
        make_gaussian_null(n=4, seed=cast(int, True))


def test_fail_closed_on_nonfinite_constant_value() -> None:
    with pytest.raises(ValueError):
        make_constant_null(n=4, value=float("nan"))
    with pytest.raises(ValueError):
        make_constant_null(n=4, value=float("inf"))


def test_fail_closed_on_nonfinite_surrogate_input() -> None:
    with pytest.raises(ValueError):
        make_phase_shuffled_surrogate([1.0, float("nan"), 3.0], seed=0)
    with pytest.raises(ValueError):
        make_phase_shuffled_surrogate([], seed=0)


# ── NaN / inf are never produced ─────────────────────────────────────────
def test_never_produces_nonfinite() -> None:
    g, _ = make_gaussian_null(n=256, seed=99, loc=1e6, scale=1e3)
    c, _ = make_constant_null(n=256, value=-3.0)
    s, _ = make_phase_shuffled_surrogate(
        np.cos(np.linspace(0.0, 20.0, 256)).tolist(), seed=99
    )
    for arr in (g, c, s):
        assert np.all(np.isfinite(arr))


# ── surrogate preserves the power spectrum ───────────────────────────────
def test_surrogate_preserves_power_spectrum() -> None:
    series = np.sin(np.linspace(0.0, 12.0, 200)) + 0.3 * np.cos(
        np.linspace(0.0, 30.0, 200)
    )
    surrogate, meta = make_phase_shuffled_surrogate(series.tolist(), seed=42)
    orig_power = np.abs(np.fft.rfft(series))
    surr_power = np.abs(np.fft.rfft(surrogate))
    np.testing.assert_allclose(orig_power, surr_power, atol=1e-8, rtol=1e-6)
    assert meta["preserves_power_spectrum"] is True


# ── no forecasting / trading language on the metadata surface ────────────
def test_no_predictive_or_trading_language() -> None:
    banned = (
        "buy",
        "sell",
        "alpha",
        "signal",
        "profit",
        "return",
        "predict",
        "forecast",
        "trade",
    )
    disclaimer_keys = {
        "claim_boundary",
        "not_predictive_claim",
        "not_financial_advice",
    }
    for arr_meta in (
        make_gaussian_null(n=8, seed=0),
        make_constant_null(n=8),
        make_phase_shuffled_surrogate([float(i) for i in range(8)], seed=0),
    ):
        _, meta = arr_meta
        for key, val in meta.items():
            if key in disclaimer_keys:
                continue
            text = f"{key} {val}".lower()
            for token in banned:
                assert token not in text, f"banned token {token!r} in metadata {key!r}"
