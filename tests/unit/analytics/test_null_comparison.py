# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the descriptor-vs-null comparison harness.

Covers the comparison contract: determinism for equal inputs, percentile
correctness on a known null, mid-rank tie handling, fail-closed rejection
of an empty / all-non-finite null and a non-finite observed value, dropping
of non-finite samples inside an otherwise-usable null (reported through
``n_null``), band edge behaviour and band validation, metadata
completeness and boundary disclaimer, and the absence of forecasting /
trading language on the result surface.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from analytics.signals.null_baseline import make_gaussian_null
from analytics.signals.null_comparison import (
    CLAIM_BOUNDARY,
    DEFAULT_BAND,
    NullComparison,
    compare_to_null,
)

_REQUIRED_META_KEYS = {
    "method",
    "seed",
    "n_null",
    "band",
    "percentile",
    "rank",
    "is_outside_null_band",
    "claim_boundary",
    "not_predictive_claim",
    "not_financial_advice",
    "research_only",
}


# ── determinism for equal inputs ─────────────────────────────────────────
def test_deterministic_for_equal_inputs() -> None:
    null = np.arange(0.0, 100.0)
    a = compare_to_null(42.0, null, band=0.05)
    b = compare_to_null(42.0, null, band=0.05)
    assert a == b
    assert a.percentile == b.percentile
    assert a.rank == b.rank


def test_deterministic_against_seeded_null_generator() -> None:
    null, meta = make_gaussian_null(n=256, seed=9)
    a = compare_to_null(0.0, null, seed=int(meta["seed"]))
    b = compare_to_null(0.0, null, seed=int(meta["seed"]))
    assert a == b
    assert a.seed == 9


# ── percentile correctness on a known null ───────────────────────────────
def test_percentile_correct_on_known_input() -> None:
    null = np.arange(0.0, 100.0)  # 0..99, 100 samples
    # 50 samples are strictly below 50.0; one equals it -> mid-rank.
    result = compare_to_null(50.0, null, band=0.05)
    assert result.rank == 50
    assert result.n_null == 100
    assert result.percentile == pytest.approx(50.5)


def test_percentile_extremes() -> None:
    null = np.arange(0.0, 100.0)
    low = compare_to_null(-10.0, null, band=0.05)
    high = compare_to_null(1000.0, null, band=0.05)
    assert low.rank == 0
    assert low.percentile == pytest.approx(0.0)
    assert high.rank == 100
    assert high.percentile == pytest.approx(100.0)


def test_midrank_ties() -> None:
    null = np.array([1.0, 1.0, 1.0, 1.0])
    result = compare_to_null(1.0, null, band=0.1)
    # 0 strictly below, 4 equal -> (0 + 0.5*4)/4 * 100 = 50.0
    assert result.rank == 0
    assert result.percentile == pytest.approx(50.0)


# ── fail-closed: empty null ──────────────────────────────────────────────
def test_fail_closed_on_empty_null() -> None:
    with pytest.raises(ValueError):
        compare_to_null(1.0, np.array([], dtype=np.float64))


def test_fail_closed_on_all_nonfinite_null() -> None:
    with pytest.raises(ValueError):
        compare_to_null(1.0, np.array([np.nan, np.inf, -np.inf]))


# ── fail-closed: non-finite observed ─────────────────────────────────────
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_fail_closed_on_nonfinite_observed(bad: float) -> None:
    with pytest.raises(ValueError):
        compare_to_null(bad, np.arange(0.0, 10.0))


def test_fail_closed_on_bool_observed() -> None:
    bad_observed: float = True  # bool is a subtype of int; must be rejected
    with pytest.raises(ValueError):
        compare_to_null(bad_observed, np.arange(0.0, 10.0))


# ── non-finite samples inside a usable null are dropped and counted ──────
def test_drops_nonfinite_samples_and_reports_count() -> None:
    null = np.array([0.0, 1.0, np.nan, 2.0, np.inf, 3.0])
    result = compare_to_null(2.5, null, band=0.1)
    assert result.n_null == 4  # 0,1,2,3 survive
    assert result.rank == 3  # 0,1,2 strictly below 2.5
    assert result.percentile == pytest.approx(75.0)


# ── band edge behaviour and validation ───────────────────────────────────
def test_band_flags_outside_in_lower_tail() -> None:
    null = np.arange(0.0, 100.0)
    result = compare_to_null(-5.0, null, band=0.1)
    assert result.percentile == pytest.approx(0.0)
    assert result.is_outside_null_band is True


def test_band_flags_inside_for_central_value() -> None:
    null = np.arange(0.0, 100.0)
    result = compare_to_null(50.0, null, band=0.1)
    assert result.is_outside_null_band is False


def test_band_upper_tail() -> None:
    null = np.arange(0.0, 100.0)
    result = compare_to_null(98.0, null, band=0.05)  # percentile ~98.5 > 95
    assert result.percentile > 95.0
    assert result.is_outside_null_band is True


@pytest.mark.parametrize("bad_band", [0.0, 0.5, 0.7, -0.1, np.nan, np.inf])
def test_fail_closed_on_invalid_band(bad_band: float) -> None:
    with pytest.raises(ValueError):
        compare_to_null(1.0, np.arange(0.0, 10.0), band=bad_band)


def test_fail_closed_on_bool_band() -> None:
    with pytest.raises(ValueError):
        compare_to_null(1.0, np.arange(0.0, 10.0), band=True)


# ── metadata completeness and boundary disclaimer ────────────────────────
def test_metadata_completeness_and_boundary() -> None:
    result = compare_to_null(3.0, np.arange(0.0, 10.0), band=0.05, seed=7)
    meta = result.metadata
    assert set(meta.keys()) == _REQUIRED_META_KEYS
    assert meta["claim_boundary"] == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert meta["not_predictive_claim"] is True
    assert meta["not_financial_advice"] is True
    assert meta["research_only"] is True
    assert meta["seed"] == 7
    assert meta["n_null"] == 10


def test_result_disclaimer_fields() -> None:
    result = compare_to_null(3.0, np.arange(0.0, 10.0))
    assert result.claim_boundary == "descriptor_only_not_predictor"
    assert result.not_predictive_claim is True
    assert result.not_financial_advice is True
    assert result.research_only is True
    assert result.band == DEFAULT_BAND


def test_metadata_is_immutable() -> None:
    result = compare_to_null(3.0, np.arange(0.0, 10.0))
    mutable: dict[str, Any] = cast("dict[str, Any]", result.metadata)
    with pytest.raises(TypeError):
        mutable["method"] = "tampered"


def test_result_dataclass_is_frozen() -> None:
    result = compare_to_null(3.0, np.arange(0.0, 10.0))
    assert isinstance(result, NullComparison)
    with pytest.raises(AttributeError):
        setattr(result, "percentile", 0.0)


# ── no forecasting / trading language on the result surface ──────────────
def test_no_predictive_or_trading_language() -> None:
    result = compare_to_null(3.0, np.arange(0.0, 10.0))
    surface = " ".join(str(v) for v in result.metadata.keys())
    surface += " " + str(result.method)
    surface_l = surface.lower()
    forbidden = (
        "predict",
        "forecast",
        "alpha",
        "buy",
        "sell",
        "profit",
        "pvalue",
        "p-value",
        "significant",
    )
    for token in forbidden:
        # The disclaimer keys themselves contain "predict" only inside
        # "not_predictive_claim", which is an explicit negation.
        if token == "predict":
            assert all(
                ("not_predictive" in k or "predict" not in k) for k in result.metadata.keys()
            )
            continue
        assert token not in surface_l
