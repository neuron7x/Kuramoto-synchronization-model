# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Edge-contract tests for pure API service helpers."""

from __future__ import annotations

import os

import pandas as pd
import pytest
from fastapi import HTTPException

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")

from application.api.service import (
    _filter_feature_values,
    _paginate_frame,
    _parse_confidence_param,
    _validate_idempotency_key,
)


def test_idempotency_key_is_trimmed_and_preserves_allowed_charset() -> None:
    assert (
        _validate_idempotency_key("  order-ABC_123.:retry  ")
        == "order-ABC_123.:retry"
    )


@pytest.mark.parametrize("raw", ["", "   ", "bad/key", "x" * 129])
def test_invalid_idempotency_key_raises_bad_request(raw: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        _validate_idempotency_key(raw)

    assert excinfo.value.status_code == 400


def test_confidence_parser_accepts_closed_unit_interval() -> None:
    assert _parse_confidence_param(None) is None
    assert _parse_confidence_param("0") == pytest.approx(0.0)
    assert _parse_confidence_param("0.75") == pytest.approx(0.75)
    assert _parse_confidence_param("1") == pytest.approx(1.0)


@pytest.mark.parametrize("raw", ["nan?", "-0.001", "1.001"])
def test_confidence_parser_rejects_invalid_or_out_of_range_values(raw: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        _parse_confidence_param(raw)

    assert excinfo.value.status_code == 422


def test_filter_feature_values_combines_prefix_and_explicit_keys() -> None:
    vector = pd.Series(
        {
            "rsi": 55.0,
            "macd_signal": 0.12,
            "macd": 0.2,
            "macd_histogram": -0.03,
            "volume": 100.0,
        }
    )

    macd_values = _filter_feature_values(vector, feature_prefix="macd", feature_keys=())
    keyed_values = _filter_feature_values(
        vector,
        feature_prefix=None,
        feature_keys=("rsi", "missing"),
    )
    combined_values = _filter_feature_values(
        vector,
        feature_prefix="macd",
        feature_keys=("macd", "rsi"),
    )

    assert list(macd_values) == ["macd", "macd_histogram", "macd_signal"]
    assert keyed_values == {"rsi": 55.0}
    assert combined_values == {"macd": 0.2}


def test_paginate_frame_orders_descending_and_uses_exclusive_cursor() -> None:
    index = pd.to_datetime(
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:01:00Z",
            "2026-01-01T00:02:00Z",
        ],
        utc=True,
    )
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=index)

    first_page, next_cursor = _paginate_frame(frame, limit=2, cursor=None)
    second_page, second_cursor = _paginate_frame(frame, limit=2, cursor=next_cursor)

    assert list(first_page["value"]) == [3.0, 2.0]
    assert next_cursor == index[1].to_pydatetime()
    assert list(second_page["value"]) == [1.0]
    assert second_cursor == index[0].to_pydatetime()
