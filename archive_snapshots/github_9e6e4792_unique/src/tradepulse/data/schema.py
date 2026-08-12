# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unified market data schema for TradePulse.

This module provides the canonical data models used across the entire
TradePulse platform. All strategies, backtests, and live trading systems
must consume market data through these standardized schemas.

**Core Principles**

1. Single source of truth - one set of schemas for all data flows
2. Strict validation - price > 0, volume >= 0, monotonic timestamps
3. Type safety - proper types (Decimal for prices, datetime with UTC timezone)
4. Immutability - frozen dataclasses prevent accidental mutations

**Models**

- ``Bar`` / ``Candle``: OHLCV bar data
- ``Tick``: Tick-level price updates
- ``FeatureVector``: Structured features for strategies
- ``MarketSnapshot``: Point-in-time market state

Example:
    >>> from tradepulse.data.schema import Bar, Timeframe
    >>> bar = Bar(
    ...     timestamp=datetime.now(timezone.utc),
    ...     symbol="BTCUSDT",
    ...     timeframe=Timeframe.M1,
    ...     open=Decimal("45000"),
    ...     high=Decimal("45100"),
    ...     low=Decimal("44900"),
    ...     close=Decimal("45050"),
    ...     volume=Decimal("100.5"),
    ... )
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

__all__ = [
    "Bar",
    "Candle",
    "DataQualityStatus",
    "FeatureVector",
    "MarketSnapshot",
    "OrderSide",
    "Tick",
    "Timeframe",
]


class Timeframe(str, Enum):
    """Supported timeframes for bar aggregation.

    Follows standard market data conventions.
    """

    S1 = "1s"  # 1 second
    S5 = "5s"  # 5 seconds
    S15 = "15s"  # 15 seconds
    S30 = "30s"  # 30 seconds
    M1 = "1m"  # 1 minute
    M5 = "5m"  # 5 minutes
    M15 = "15m"  # 15 minutes
    M30 = "30m"  # 30 minutes
    H1 = "1h"  # 1 hour
    H4 = "4h"  # 4 hours
    D1 = "1d"  # 1 day
    W1 = "1w"  # 1 week
    MN1 = "1M"  # 1 month

    @property
    def seconds(self) -> int:
        """Return timeframe duration in seconds."""
        mapping = {
            "1s": 1,
            "5s": 5,
            "15s": 15,
            "30s": 30,
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
            "1M": 2592000,  # Approximate: 30 days
        }
        return mapping[self.value]

    @classmethod
    def from_string(cls, value: str) -> "Timeframe":
        """Parse timeframe from string representation."""
        normalized = value.lower().strip()
        # Handle common aliases
        aliases = {
            "1min": "1m",
            "5min": "5m",
            "15min": "15m",
            "30min": "30m",
            "1hour": "1h",
            "4hour": "4h",
            "1day": "1d",
            "1week": "1w",
            "1month": "1M",
        }
        normalized = aliases.get(normalized, normalized)
        for tf in cls:
            if tf.value.lower() == normalized:
                return tf
        raise ValueError(f"Unknown timeframe: {value}")


class OrderSide(str, Enum):
    """Order side for trading."""

    BUY = "BUY"
    SELL = "SELL"


class DataQualityStatus(str, Enum):
    """Data quality status levels."""

    OK = "OK"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


def _to_decimal(value: Union[Decimal, float, int, str]) -> Decimal:
    """Safely convert numeric input to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("boolean values are not valid decimal inputs")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TypeError(f"Unable to convert {value!r} to Decimal") from exc


class _FrozenModel(BaseModel):
    """Base configuration for immutable market data models."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=False,
    )

    @field_serializer("*", when_used="json")
    @classmethod
    def _serialize_special_types(cls, value: Any) -> Any:
        """Serialize Decimal and other types for JSON export."""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value


class Bar(_FrozenModel):
    """OHLCV bar representing aggregated price data for a time interval.

    This is the primary data structure for historical and live market data.
    All price values are stored as Decimal for precision, and timestamps
    must be timezone-aware UTC.

    Attributes:
        timestamp: Bar open time (must be UTC timezone-aware)
        symbol: Trading symbol (e.g., "BTCUSDT", "AAPL")
        timeframe: Bar aggregation timeframe
        open: Opening price (must be > 0)
        high: Highest price (must be >= open, close, low)
        low: Lowest price (must be <= open, close, high)
        close: Closing price (must be > 0)
        volume: Trading volume (must be >= 0)
        trades: Number of trades in the bar (optional)
        vwap: Volume-weighted average price (optional)

    Example:
        >>> bar = Bar(
        ...     timestamp=datetime.now(timezone.utc),
        ...     symbol="BTCUSDT",
        ...     timeframe=Timeframe.M1,
        ...     open=Decimal("45000"),
        ...     high=Decimal("45100"),
        ...     low=Decimal("44900"),
        ...     close=Decimal("45050"),
        ...     volume=Decimal("100.5"),
        ... )
    """

    timestamp: datetime
    symbol: StrictStr = Field(..., min_length=1, description="Trading symbol")
    timeframe: Timeframe
    open: Decimal = Field(..., description="Opening price")
    high: Decimal = Field(..., description="Highest price in interval")
    low: Decimal = Field(..., description="Lowest price in interval")
    close: Decimal = Field(..., description="Closing price")
    volume: Decimal = Field(..., description="Trading volume")
    trades: Optional[int] = Field(default=None, ge=0, description="Number of trades")
    vwap: Optional[Decimal] = Field(
        default=None, description="Volume-weighted average price"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: Union[datetime, float, int]) -> datetime:
        """Convert epoch seconds or naive datetime to UTC-aware datetime."""
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError("timestamp must be datetime or epoch seconds")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Union[Decimal, float, int, str]) -> Decimal:
        """Convert numeric inputs to Decimal."""
        try:
            return _to_decimal(value)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("vwap", mode="before")
    @classmethod
    def _coerce_vwap(
        cls, value: Optional[Union[Decimal, float, int, str]]
    ) -> Optional[Decimal]:
        """Convert VWAP to Decimal if provided."""
        if value is None:
            return None
        try:
            return _to_decimal(value)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Ensure symbol is non-empty after stripping."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("symbol must be non-empty")
        return stripped.upper()

    @field_validator("open", "high", "low", "close")
    @classmethod
    def _validate_positive_price(cls, value: Decimal) -> Decimal:
        """Ensure prices are positive."""
        if value <= 0:
            raise ValueError("price must be positive (> 0)")
        return value

    @field_validator("volume")
    @classmethod
    def _validate_non_negative_volume(cls, value: Decimal) -> Decimal:
        """Ensure volume is non-negative."""
        if value < 0:
            raise ValueError("volume must be non-negative (>= 0)")
        return value

    @model_validator(mode="after")
    def _validate_ohlc_relationships(self) -> "Bar":
        """Validate OHLC price relationships."""
        if self.high < self.low:
            raise ValueError("high price must be >= low price")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open price must be between low and high")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close price must be between low and high")
        return self

    @model_validator(mode="after")
    def _validate_utc_timezone(self) -> "Bar":
        """Ensure timestamp is UTC."""
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return self

    @model_validator(mode="after")
    def _validate_finite_values(self) -> "Bar":
        """Ensure all numeric values are finite."""
        max_magnitude = Decimal("1e15")
        for field_name in ("open", "high", "low", "close", "volume"):
            value: Decimal = getattr(self, field_name)
            if not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
            if abs(value) > max_magnitude:
                raise ValueError(f"{field_name} exceeds maximum magnitude")
        if self.vwap is not None:
            if not self.vwap.is_finite():
                raise ValueError("vwap must be finite")
            if abs(self.vwap) > max_magnitude:
                raise ValueError("vwap exceeds maximum magnitude")
        return self

    @property
    def ts(self) -> float:
        """Return timestamp as epoch seconds."""
        return self.timestamp.timestamp()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with string values for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "trades": self.trades,
            "vwap": str(self.vwap) if self.vwap is not None else None,
        }


# Alias for backward compatibility
Candle = Bar


class Tick(_FrozenModel):
    """Tick-level price update representing a single trade or quote.

    Attributes:
        timestamp: Time of the tick (must be UTC)
        symbol: Trading symbol
        price: Trade/quote price (must be > 0)
        volume: Trade volume (must be >= 0)
        side: Trade side (optional)
        trade_id: Exchange trade identifier (optional)
    """

    timestamp: datetime
    symbol: StrictStr = Field(..., min_length=1, description="Trading symbol")
    price: Decimal = Field(..., description="Trade price")
    volume: Decimal = Field(default=Decimal("0"), description="Trade volume")
    side: Optional[OrderSide] = Field(default=None, description="Trade side")
    trade_id: Optional[str] = Field(default=None, description="Exchange trade ID")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: Union[datetime, float, int]) -> datetime:
        """Convert to UTC-aware datetime."""
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError("timestamp must be datetime or epoch seconds")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator("price", "volume", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Union[Decimal, float, int, str]) -> Decimal:
        """Convert numeric inputs to Decimal."""
        try:
            return _to_decimal(value)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Ensure symbol is non-empty."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("symbol must be non-empty")
        return stripped.upper()

    @field_validator("price")
    @classmethod
    def _validate_positive_price(cls, value: Decimal) -> Decimal:
        """Ensure price is positive."""
        if value <= 0:
            raise ValueError("price must be positive (> 0)")
        return value

    @field_validator("volume")
    @classmethod
    def _validate_non_negative_volume(cls, value: Decimal) -> Decimal:
        """Ensure volume is non-negative."""
        if value < 0:
            raise ValueError("volume must be non-negative (>= 0)")
        return value

    @model_validator(mode="after")
    def _validate_utc_and_finite(self) -> "Tick":
        """Validate UTC timezone and finite values."""
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")

        max_magnitude = Decimal("1e15")
        for field_name in ("price", "volume"):
            value: Decimal = getattr(self, field_name)
            if not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
            if abs(value) > max_magnitude:
                raise ValueError(f"{field_name} exceeds maximum magnitude")
        return self

    @property
    def ts(self) -> float:
        """Return timestamp as epoch seconds."""
        return self.timestamp.timestamp()


class FeatureVector(_FrozenModel):
    """Structured feature vector for strategy consumption.

    This model provides a standardized interface for passing computed
    features (indicators, signals, etc.) to strategies.

    Attributes:
        timestamp: Feature computation time
        symbol: Associated symbol
        features: Dictionary of feature name -> value mappings
        metadata: Optional additional context
    """

    timestamp: datetime
    symbol: StrictStr = Field(..., min_length=1, description="Associated symbol")
    features: Dict[str, float] = Field(
        default_factory=dict, description="Feature values"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: Union[datetime, float, int]) -> datetime:
        """Convert to UTC-aware datetime."""
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError("timestamp must be datetime or epoch seconds")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Ensure symbol is non-empty."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("symbol must be non-empty")
        return stripped.upper()

    @model_validator(mode="after")
    def _validate_utc(self) -> "FeatureVector":
        """Ensure timestamp is UTC."""
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return self

    def get(
        self, feature_name: str, default: Optional[float] = None
    ) -> Optional[float]:
        """Get a feature value by name."""
        return self.features.get(feature_name, default)

    @property
    def ts(self) -> float:
        """Return timestamp as epoch seconds."""
        return self.timestamp.timestamp()


class MarketSnapshot(_FrozenModel):
    """Point-in-time market state for a symbol.

    Combines price data, order book summary, and other market metrics
    into a single snapshot.

    Attributes:
        timestamp: Snapshot time
        symbol: Trading symbol
        last_price: Most recent trade price
        bid: Best bid price (optional)
        ask: Best ask price (optional)
        bid_volume: Volume at best bid (optional)
        ask_volume: Volume at best ask (optional)
        last_bar: Most recent completed bar (optional)
        features: Associated feature vector (optional)
    """

    model_config = ConfigDict(
        frozen=True,
        strict=False,  # Allow flexible type coercion for nested models
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=False,
    )

    timestamp: datetime
    symbol: StrictStr = Field(..., min_length=1, description="Trading symbol")
    last_price: Decimal = Field(..., description="Most recent trade price")
    bid: Optional[Decimal] = Field(default=None, description="Best bid price")
    ask: Optional[Decimal] = Field(default=None, description="Best ask price")
    bid_volume: Optional[Decimal] = Field(
        default=None, description="Volume at best bid"
    )
    ask_volume: Optional[Decimal] = Field(
        default=None, description="Volume at best ask"
    )
    last_bar: Optional[Any] = Field(default=None, description="Most recent bar")
    features: Optional[Any] = Field(default=None, description="Feature vector")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: Union[datetime, float, int]) -> datetime:
        """Convert to UTC-aware datetime."""
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError("timestamp must be datetime or epoch seconds")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator(
        "last_price", "bid", "ask", "bid_volume", "ask_volume", mode="before"
    )
    @classmethod
    def _coerce_decimal(
        cls, value: Optional[Union[Decimal, float, int, str]]
    ) -> Optional[Decimal]:
        """Convert numeric inputs to Decimal."""
        if value is None:
            return None
        try:
            return _to_decimal(value)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Ensure symbol is non-empty."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("symbol must be non-empty")
        return stripped.upper()

    @field_validator("last_price")
    @classmethod
    def _validate_positive_price(cls, value: Decimal) -> Decimal:
        """Ensure price is positive."""
        if value <= 0:
            raise ValueError("last_price must be positive (> 0)")
        return value

    @model_validator(mode="after")
    def _validate_book_consistency(self) -> "MarketSnapshot":
        """Validate order book data consistency."""
        if self.bid is not None and self.ask is not None:
            if self.bid > self.ask:
                raise ValueError("bid cannot be greater than ask")

        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive")
        if self.bid_volume is not None and self.bid_volume < 0:
            raise ValueError("bid_volume must be non-negative")
        if self.ask_volume is not None and self.ask_volume < 0:
            raise ValueError("ask_volume must be non-negative")
        return self

    @model_validator(mode="after")
    def _validate_utc(self) -> "MarketSnapshot":
        """Ensure timestamp is UTC."""
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return self

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread if available."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid price if bid/ask available."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    @property
    def ts(self) -> float:
        """Return timestamp as epoch seconds."""
        return self.timestamp.timestamp()
