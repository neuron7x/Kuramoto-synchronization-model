# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Canonical market data models used across TradePulse.

The platform expects a single, strongly typed representation for all market
data payloads (ticks, OHLCV bars, aggregates) so downstream components can rely
on consistent validation semantics.  The models below are implemented with
``pydantic`` which provides strict runtime validation while keeping
ergonomic factory helpers for callers.

All timestamps are normalised to UTC, numeric values are coerced to ``Decimal``
and validated to avoid silent precision loss, and instrument metadata is shared
across every payload variant.  ``Ticker`` remains an alias for ``PriceTick`` to
preserve backwards compatibility with existing ingestion pipelines.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from core.data.catalog import normalize_symbol, normalize_venue

__all__ = [
    "AggregateMetric",
    "DataKind",
    "InstrumentType",
    "MarketDataPoint",
    "MarketMetadata",
    "OHLCVBar",
    "PriceTick",
    "Ticker",
]


class InstrumentType(str, Enum):
    """Enumerates the supported instrument categories."""

    SPOT = "spot"
    FUTURES = "futures"


class DataKind(str, Enum):
    """Enumerates the supported market data granularities."""

    TICK = "tick"
    OHLCV = "ohlcv"
    AGGREGATE = "aggregate"


def _to_decimal(value: Union[Decimal, float, int, str]) -> Decimal:
    """Convert arbitrary numeric inputs to ``Decimal`` safely."""

    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is a subclass of int – avoid silent bugs
        raise TypeError("boolean values are not valid decimal inputs")
    try:
        return Decimal(str(value))
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:  # pragma: no cover - defensive guard
        raise TypeError(f"Unable to convert {value!r} to Decimal") from exc


class _FrozenModel(BaseModel):
    """Base configuration shared by immutable market data models."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=False,
    )

    @field_serializer("*", when_used="json")
    def _serialize_decimal(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        return value


class MarketMetadata(_FrozenModel):
    """Common metadata shared by all market data payloads."""

    symbol: StrictStr = Field(
        ..., min_length=1, description="Instrument symbol, e.g. BTCUSD"
    )
    venue: StrictStr = Field(..., min_length=1, description="Market venue identifier")
    instrument_type: InstrumentType = Field(
        default=InstrumentType.SPOT,
        description="Instrument category (spot or futures)",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value: str, info: ValidationInfo) -> str:
        instrument_type = info.data.get("instrument_type")
        return normalize_symbol(value, instrument_type_hint=instrument_type)

    @field_validator("venue", mode="before")
    @classmethod
    def _normalise_venue(cls, value: str) -> str:
        return normalize_venue(value)

    @field_validator("symbol", "venue")
    @classmethod
    def _ensure_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be a non-empty string")
        return stripped


class MarketDataPoint(_FrozenModel):
    """Base class for all market data records."""

    metadata: MarketMetadata
    timestamp: datetime
    kind: DataKind

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: Union[datetime, float, int]) -> datetime:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:  # pragma: no cover - defensive guard
            raise TypeError("timestamp must be datetime or epoch seconds")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator("kind", mode="before")
    @classmethod
    def _ensure_kind(cls, value: Union[None, DataKind, str]) -> DataKind:
        if value is None:
            raise ValueError("kind must be provided")
        if isinstance(value, DataKind):
            return value
        return DataKind(str(value))

    @model_validator(mode="after")
    def _enforce_utc(self) -> "MarketDataPoint":
        ts = self.timestamp
        if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
            raise ValueError("timestamp must be timezone-aware")
        if ts.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be normalised to UTC")
        return self

    @property
    def symbol(self) -> str:
        return self.metadata.symbol

    @property
    def venue(self) -> str:
        return self.metadata.venue

    @property
    def instrument_type(self) -> InstrumentType:
        return self.metadata.instrument_type

    @property
    def ts(self) -> float:
        """Return the timestamp as epoch seconds."""

        return self.timestamp.timestamp()


class PriceTick(MarketDataPoint):
    """Tick-level price update."""

    price: Decimal = Field(..., description="Last traded price")
    volume: Decimal = Field(
        default=Decimal("0"), description="Trade volume at the tick"
    )
    trade_id: Optional[str] = Field(
        default=None, description="Exchange trade identifier"
    )
    kind: Literal[DataKind.TICK] = DataKind.TICK

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: Union[Decimal, float, int, str, None]) -> Decimal:
        if value is None:
            raise ValueError("price must be provided")
        try:
            return _to_decimal(value)
        except TypeError as exc:  # pragma: no cover - propagated via ValidationError
            raise ValueError(str(exc)) from exc

    @field_validator("volume", mode="before")
    @classmethod
    def _coerce_volume(cls, value: Union[Decimal, float, int, str, None]) -> Decimal:
        if value is None:
            return Decimal("0")
        try:
            return _to_decimal(value)
        except TypeError as exc:  # pragma: no cover - propagated via ValidationError
            raise ValueError(str(exc)) from exc

    @field_validator("price", "volume")
    @classmethod
    def _validate_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("numeric values must be non-negative")
        return value

    @field_validator("trade_id")
    @classmethod
    def _strip_trade_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _guard_finite_values(self) -> "PriceTick":
        max_magnitude = Decimal("1e12")
        for field_name in ("price", "volume"):
            value: Decimal = getattr(self, field_name)
            if not value.is_finite():
                raise ValueError(f"{field_name} must be a finite decimal value")
            if abs(value) > max_magnitude:
                raise ValueError(
                    f"{field_name} magnitude {value} exceeds the allowed bound of {max_magnitude}"
                )
        return self

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        venue: str,
        price: Union[Decimal, float, int, str],
        timestamp: Union[datetime, float, int],
        volume: Union[Decimal, float, int, str, None] = None,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        trade_id: Optional[str] = None,
    ) -> "PriceTick":
        """Factory helper that builds the metadata block for convenience."""

        meta = MarketMetadata(
            symbol=symbol, venue=venue, instrument_type=instrument_type
        )
        return cls(
            metadata=meta,
            timestamp=timestamp,
            price=price,
            volume=volume,
            trade_id=trade_id,
        )


class OHLCVBar(MarketDataPoint):
    """OHLCV bar representing aggregated price information."""

    open: Decimal = Field(..., description="Opening price")
    high: Decimal = Field(..., description="Highest price in the interval")
    low: Decimal = Field(..., description="Lowest price in the interval")
    close: Decimal = Field(..., description="Closing price")
    volume: Decimal = Field(..., description="Total traded volume")
    interval_seconds: int = Field(..., gt=0, description="Bar interval in seconds")
    kind: Literal[DataKind.OHLCV] = DataKind.OHLCV

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def _coerce_decimal_values(cls, value: Union[Decimal, float, int, str]) -> Decimal:
        try:
            return _to_decimal(value)
        except TypeError as exc:  # pragma: no cover - propagated via ValidationError
            raise ValueError(str(exc)) from exc

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def _validate_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("OHLCV values must be non-negative")
        return value

    @model_validator(mode="after")
    def _validate_price_relationships(self) -> "OHLCVBar":
        low = self.low
        high = self.high
        open_price = self.open
        close_price = self.close
        if low is not None and high is not None and high < low:
            raise ValueError("high price must be greater or equal to low price")
        if low is not None and high is not None:
            if open_price is not None and not (low <= open_price <= high):
                raise ValueError("open price must lie between low and high")
            if close_price is not None and not (low <= close_price <= high):
                raise ValueError("close price must lie between low and high")
        return self

    @model_validator(mode="after")
    def _guard_finite_ohlcv(self) -> "OHLCVBar":
        max_magnitude = Decimal("1e12")
        for field_name in ("open", "high", "low", "close", "volume"):
            value: Decimal = getattr(self, field_name)
            if not value.is_finite():
                raise ValueError(f"{field_name} must be a finite decimal value")
            if abs(value) > max_magnitude:
                raise ValueError(
                    f"{field_name} magnitude {value} exceeds the allowed bound of {max_magnitude}"
                )
        return self


class AggregateMetric(MarketDataPoint):
    """Generic aggregated value produced from raw market data."""

    metric: StrictStr = Field(..., min_length=1, description="Metric name")
    value: Decimal = Field(..., description="Metric value")
    window_seconds: int = Field(..., gt=0, description="Window size in seconds")
    kind: Literal[DataKind.AGGREGATE] = DataKind.AGGREGATE

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("metric must be a non-empty string")
        return stripped

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, value: Union[Decimal, float, int, str]) -> Decimal:
        try:
            return _to_decimal(value)
        except TypeError as exc:  # pragma: no cover - propagated via ValidationError
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _guard_finite_value(self) -> "AggregateMetric":
        if not self.value.is_finite():
            raise ValueError("value must be a finite decimal")
        if abs(self.value) > Decimal("1e12"):
            raise ValueError("value magnitude exceeds the allowed bound of 1e12")
        return self


# Backwards compatibility export ---------------------------------------------------------

Ticker = PriceTick
