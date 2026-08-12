# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from pydantic import ValidationError

from core.data.models import (
    AggregateMetric,
    MarketMetadata,
    OHLCVBar,
    PriceTick,
)


def _assert_validation_error(
    exc: ValidationError,
    *,
    contains: str | None = None,
    error_type: str | None = None,
) -> None:
    for error in exc.errors():
        if contains and contains in error["msg"]:
            return
        if error_type and error["type"] == error_type:
            return
    criteria = contains or error_type or "expected validation error"
    raise AssertionError(f"Expected {criteria!r} in validation errors: {exc.errors()}")


def test_ohlcv_validates_price_ordering() -> None:
    with pytest.raises(ValidationError) as exc:
        OHLCVBar(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            open=Decimal("100"),
            high=Decimal("90"),
            low=Decimal("95"),
            close=Decimal("98"),
            volume=Decimal("1"),
            interval_seconds=60,
        )
    _assert_validation_error(exc.value, contains="greater or equal")

    with pytest.raises(ValidationError) as exc:
        OHLCVBar(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            open=Decimal("50"),
            high=Decimal("100"),
            low=Decimal("60"),
            close=Decimal("70"),
            volume=Decimal("1"),
            interval_seconds=60,
        )
    _assert_validation_error(exc.value, contains="open price must lie")

    with pytest.raises(ValidationError) as exc:
        OHLCVBar(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            open=Decimal("80"),
            high=Decimal("100"),
            low=Decimal("60"),
            close=Decimal("120"),
            volume=Decimal("1"),
            interval_seconds=60,
        )
    _assert_validation_error(exc.value, contains="close price must lie")


def test_ohlcv_rejects_non_finite_values() -> None:
    with pytest.raises(ValidationError) as exc:
        OHLCVBar(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            open=Decimal("NaN"),
            high=Decimal("100"),
            low=Decimal("90"),
            close=Decimal("95"),
            volume=Decimal("1"),
            interval_seconds=60,
        )
    _assert_validation_error(exc.value, error_type="finite_number")

    with pytest.raises(ValidationError) as exc:
        OHLCVBar(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            open=Decimal("10000000000000"),
            high=Decimal("10000000000001"),
            low=Decimal("10000000000000"),
            close=Decimal("10000000000000"),
            volume=Decimal("1"),
            interval_seconds=60,
        )
    _assert_validation_error(exc.value, contains="exceeds the allowed bound")


def test_aggregate_metric_validates_inputs() -> None:
    with pytest.raises(ValidationError) as exc:
        AggregateMetric(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            metric="  ",
            value=Decimal("1"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            window_seconds=60,
        )
    _assert_validation_error(exc.value, error_type="string_too_short")

    with pytest.raises(ValidationError) as exc:
        AggregateMetric(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            metric="mean",
            value=Decimal("NaN"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            window_seconds=60,
        )
    _assert_validation_error(exc.value, error_type="finite_number")

    with pytest.raises(ValidationError) as exc:
        AggregateMetric(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            metric="mean",
            value=Decimal("10000000000000"),
            timestamp=pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
            window_seconds=60,
        )
    _assert_validation_error(exc.value, contains="exceeds the allowed bound")


def test_market_metadata_requires_non_empty_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        MarketMetadata(symbol=" ", venue="BINANCE")
    _assert_validation_error(exc.value, contains="non-empty")

    with pytest.raises(ValidationError) as exc:
        MarketMetadata(symbol="BTCUSD", venue=" ")
    _assert_validation_error(exc.value, contains="non-empty")


def test_price_tick_requires_kind_value() -> None:
    with pytest.raises(ValidationError) as exc:
        PriceTick.model_validate(
            {
                "metadata": MarketMetadata(symbol="AAPL", venue="XNYS").model_dump(),
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "price": "1.0",
                "volume": "0.1",
                "kind": None,
            }
        )
    _assert_validation_error(exc.value, contains="kind must be provided")


def test_market_data_point_enforce_utc_rejects_invalid_timezone() -> None:
    tick = PriceTick.create(
        symbol="AAPL",
        venue="XNYS",
        price="100",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    object.__setattr__(tick, "timestamp", datetime(2024, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        tick._enforce_utc()

    object.__setattr__(
        tick, "timestamp", datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    )
    with pytest.raises(ValueError, match="normalised to UTC"):
        tick._enforce_utc()


def test_price_tick_rejects_infinite_and_extreme_values() -> None:
    with pytest.raises(ValidationError) as exc:
        PriceTick(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            price=Decimal("Infinity"),
            volume=Decimal("1"),
        )
    _assert_validation_error(exc.value, error_type="finite_number")

    with pytest.raises(ValidationError) as exc:
        PriceTick(
            metadata=MarketMetadata(symbol="AAPL", venue="XNYS"),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            price=Decimal("1.0"),
            volume=Decimal("10000000000000"),
        )
    _assert_validation_error(exc.value, contains="exceeds the allowed bound")
