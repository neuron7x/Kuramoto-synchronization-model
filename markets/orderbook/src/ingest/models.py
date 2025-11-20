# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data structures for level 2 order book ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Iterable, Sequence

_DECIMAL_QUANT = Decimal("1e-12")


def _to_decimal(value: str | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        dec = value
    else:
        dec = Decimal(str(value))
    # Normalise aggressively to keep memory footprint predictable while being
    # precise enough for sub-pip instruments. ROUND_HALF_EVEN avoids drift.
    return dec.quantize(_DECIMAL_QUANT, rounding=ROUND_HALF_EVEN).normalize()


@dataclass(slots=True, frozen=True)
class PriceLevel:
    """Price/quantity tuple represented with fixed decimal precision."""

    price: Decimal
    quantity: Decimal

    @classmethod
    def from_raw(
        cls, price: str | float | Decimal, quantity: str | float | Decimal
    ) -> "PriceLevel":
        return cls(price=_to_decimal(price), quantity=_to_decimal(quantity))


@dataclass(slots=True, frozen=True)
class OrderBookDiff:
    """Incremental diff message coming from an exchange."""

    instrument: str
    sequence_start: int
    sequence_end: int
    bids: Sequence[PriceLevel]
    asks: Sequence[PriceLevel]
    ts_event: datetime
    ts_arrival: datetime
    source: str

    def __post_init__(self) -> None:
        if self.sequence_end < self.sequence_start:
            msg = "sequence_end must be >= sequence_start"
            raise ValueError(msg)
        if (
            self.ts_event.tzinfo is None
            or self.ts_event.tzinfo.utcoffset(self.ts_event) is None
        ):
            raise ValueError("ts_event must be timezone-aware")
        if (
            self.ts_arrival.tzinfo is None
            or self.ts_arrival.tzinfo.utcoffset(self.ts_arrival) is None
        ):
            raise ValueError("ts_arrival must be timezone-aware")
        if self.ts_arrival < self.ts_event:
            raise ValueError("arrival timestamp cannot be earlier than event timestamp")


@dataclass(slots=True, frozen=True)
class OrderBookSnapshot:
    """Full order book image used for recovery and baselining."""

    instrument: str
    sequence: int
    bids: Sequence[PriceLevel]
    asks: Sequence[PriceLevel]
    ts_event: datetime
    ts_arrival: datetime
    source: str

    def __post_init__(self) -> None:
        if (
            self.ts_event.tzinfo is None
            or self.ts_event.tzinfo.utcoffset(self.ts_event) is None
        ):
            raise ValueError("ts_event must be timezone-aware")
        if (
            self.ts_arrival.tzinfo is None
            or self.ts_arrival.tzinfo.utcoffset(self.ts_arrival) is None
        ):
            raise ValueError("ts_arrival must be timezone-aware")
        if self.ts_arrival < self.ts_event:
            raise ValueError("arrival timestamp cannot be earlier than event timestamp")


@dataclass(slots=True, frozen=True)
class AppliedDiff:
    """Result returned when a diff was applied successfully."""

    instrument: str
    sequence: int
    ts_event: datetime
    ts_arrival: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_price_levels(levels: Iterable[PriceLevel]) -> tuple[PriceLevel, ...]:
    return tuple(levels)
