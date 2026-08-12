# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the claim-safe descriptor-metadata factory.

Each test maps to a property of the construction invariant: the three
claim-boundary fields are always stamped, every forbidden trading/forecast
token is rejected fail-closed, non-finite/negative counts are rejected, the
``extra`` mapping merges without ever overwriting a mandatory field, the
factory is deterministic, and the emitted block is complete.
"""

from __future__ import annotations

from typing import Any

import pytest

from analytics.signals.descriptor_metadata import (
    CLAIM_BOUNDARY,
    FORBIDDEN_DESCRIPTOR_TERMS,
    MANDATORY_KEYS,
    build_descriptor_metadata,
)


def _build_with_any(**kwargs: Any) -> dict[str, Any]:
    """Forward deliberately mis-typed inputs to the factory.

    The factory's contract is fail-closed at *runtime* for bad input
    *types* (float/bool counts, non-dict extra). Exercising that runtime
    guard requires passing values the static signature forbids; routing
    them through this ``**Any`` shim keeps the call sites type-clean under
    ``mypy --strict`` without any inline suppression.
    """
    return build_descriptor_metadata(**kwargs)


def test_stamps_three_claim_fields() -> None:
    """The block always carries the three canonical claim-boundary fields."""
    meta = build_descriptor_metadata(method="hurst_rs", source="ohlcv_close", input_count=10)
    assert meta["claim_boundary"] == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert meta["not_predictive_claim"] is True
    assert meta["not_financial_advice"] is True


def test_metadata_completeness() -> None:
    """Every mandatory key is present and the counters are consistent."""
    meta = build_descriptor_metadata(
        method="entropy_band",
        source="returns_1m",
        input_count=100,
        invalid_count=7,
    )
    assert MANDATORY_KEYS <= set(meta)
    assert meta["method"] == "entropy_band"
    assert meta["source"] == "returns_1m"
    assert meta["input_count"] == 100
    assert meta["invalid_count"] == 7
    assert meta["valid_count"] == 93


@pytest.mark.parametrize("term", sorted(FORBIDDEN_DESCRIPTOR_TERMS))
def test_rejects_each_forbidden_token_in_method(term: str) -> None:
    """Every denylisted token in ``method`` fails closed."""
    with pytest.raises(ValueError, match="forbidden descriptor term"):
        build_descriptor_metadata(method=f"my {term} method", source="ohlcv", input_count=5)


@pytest.mark.parametrize("term", sorted(FORBIDDEN_DESCRIPTOR_TERMS))
def test_rejects_each_forbidden_token_in_source(term: str) -> None:
    """Every denylisted token in ``source`` fails closed."""
    with pytest.raises(ValueError, match="forbidden descriptor term"):
        build_descriptor_metadata(method="hurst_rs", source=f"feed.{term} stream", input_count=5)


def test_rejects_forbidden_token_in_extra_value() -> None:
    """A forbidden token hidden in an ``extra`` value fails closed."""
    with pytest.raises(ValueError, match="forbidden descriptor term"):
        build_descriptor_metadata(
            method="hurst_rs",
            source="ohlcv",
            input_count=5,
            extra={"note": "use this to forecast price"},
        )


def test_rejects_forbidden_token_in_nested_extra() -> None:
    """A forbidden token nested deep inside ``extra`` still fails closed."""
    with pytest.raises(ValueError, match="forbidden descriptor term"):
        build_descriptor_metadata(
            method="hurst_rs",
            source="ohlcv",
            input_count=5,
            extra={"tags": ["clean", {"label": "alpha"}]},
        )


def test_rejects_forbidden_token_in_extra_key() -> None:
    """A forbidden token used as an ``extra`` key fails closed."""
    with pytest.raises(ValueError, match="forbidden descriptor term"):
        build_descriptor_metadata(
            method="hurst_rs",
            source="ohlcv",
            input_count=5,
            extra={"profit": 1.0},
        )


def test_whole_word_matching_allows_innocuous_substrings() -> None:
    """Substrings of innocuous words are not false positives.

    ``shortfall`` contains ``short`` and ``methodology`` contains ``method``
    only as substrings; whole-word matching must let them through.
    """
    meta = build_descriptor_metadata(
        method="methodology_v2",
        source="shortfall_ledger",
        input_count=3,
    )
    assert meta["method"] == "methodology_v2"
    assert meta["source"] == "shortfall_ledger"


def test_rejects_negative_input_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_descriptor_metadata(method="hurst_rs", source="ohlcv", input_count=-1)


def test_rejects_negative_invalid_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_descriptor_metadata(
            method="hurst_rs", source="ohlcv", input_count=5, invalid_count=-2
        )


def test_rejects_nan_count() -> None:
    """A float NaN is not a valid int counter and is rejected."""
    with pytest.raises(ValueError, match="must be an int"):
        _build_with_any(
            method="hurst_rs",
            source="ohlcv",
            input_count=float("nan"),
        )


def test_rejects_inf_count() -> None:
    """A float inf is not a valid int counter and is rejected."""
    with pytest.raises(ValueError, match="must be an int"):
        _build_with_any(
            method="hurst_rs",
            source="ohlcv",
            input_count=float("inf"),
        )


def test_rejects_bool_count() -> None:
    """``bool`` is an int subclass but is rejected as a counter type."""
    with pytest.raises(ValueError, match="must be an int"):
        _build_with_any(
            method="hurst_rs",
            source="ohlcv",
            input_count=True,
        )


def test_rejects_invalid_exceeding_input() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        build_descriptor_metadata(
            method="hurst_rs", source="ohlcv", input_count=3, invalid_count=4
        )


def test_extra_merges_without_overwriting_mandatory_fields() -> None:
    """Benign ``extra`` keys merge in; mandatory keys stay canonical."""
    meta = build_descriptor_metadata(
        method="hurst_rs",
        source="ohlcv",
        input_count=10,
        extra={"window": 64, "config_hash": "deadbeef"},
    )
    assert meta["window"] == 64
    assert meta["config_hash"] == "deadbeef"
    # Mandatory fields untouched.
    assert meta["claim_boundary"] == CLAIM_BOUNDARY
    assert meta["not_predictive_claim"] is True
    assert meta["not_financial_advice"] is True


@pytest.mark.parametrize("key", sorted(MANDATORY_KEYS))
def test_extra_cannot_overwrite_any_mandatory_key(key: str) -> None:
    """An ``extra`` collision with any mandatory key fails closed."""
    with pytest.raises(ValueError, match="must not overwrite mandatory key"):
        build_descriptor_metadata(
            method="hurst_rs",
            source="ohlcv",
            input_count=5,
            extra={key: "tampered"},
        )


def test_rejects_empty_method_and_source() -> None:
    with pytest.raises(ValueError, match="method must be a non-empty string"):
        build_descriptor_metadata(method="   ", source="ohlcv", input_count=1)
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        build_descriptor_metadata(method="hurst_rs", source="", input_count=1)


def test_rejects_non_dict_extra() -> None:
    with pytest.raises(ValueError, match="extra must be a dict"):
        _build_with_any(
            method="hurst_rs",
            source="ohlcv",
            input_count=5,
            extra=["not", "a", "dict"],
        )


def test_determinism() -> None:
    """Identical inputs yield an equal block, and the result is a fresh dict."""
    kwargs: dict[str, Any] = {
        "method": "hurst_rs",
        "source": "ohlcv",
        "input_count": 42,
        "invalid_count": 2,
        "extra": {"window": 64},
    }
    first = build_descriptor_metadata(**kwargs)
    second = build_descriptor_metadata(**kwargs)
    assert first == second
    assert first is not second
    # Mutating one result does not affect a freshly built one.
    first["window"] = 9999
    third = build_descriptor_metadata(**kwargs)
    assert third["window"] == 64
