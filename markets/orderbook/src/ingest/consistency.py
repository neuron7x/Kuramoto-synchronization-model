# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Consistency validation utilities for order book ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from markets.orderbook.src.core.lob import Side

from .models import OrderBookDiff, OrderBookSnapshot, PriceLevel


@dataclass(slots=True)
class ConsistencyError(Exception):
    """Raised when the order book stream violates invariants."""

    message: str
    instrument: str
    sequence: int | None

    def __str__(self) -> str:  # noqa: D401 - provide rich error string
        return f"{self.instrument} seq={self.sequence}: {self.message}"


class ConsistencyValidator:
    """Performs strict validation of exchange payloads before applying."""

    def __init__(
        self, *, min_price: Decimal | None = None, min_quantity: Decimal | None = None
    ) -> None:
        self._min_price = min_price
        self._min_quantity = min_quantity

    def validate_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self._validate_levels(
            snapshot.instrument, snapshot.sequence, snapshot.bids, Side.BUY
        )
        self._validate_levels(
            snapshot.instrument, snapshot.sequence, snapshot.asks, Side.SELL
        )
        self._validate_timestamps(snapshot.ts_event, snapshot.ts_arrival)

    def validate_diff(self, diff: OrderBookDiff) -> None:
        self._validate_levels(
            diff.instrument, diff.sequence_end, diff.bids, Side.BUY, allow_zero=True
        )
        self._validate_levels(
            diff.instrument, diff.sequence_end, diff.asks, Side.SELL, allow_zero=True
        )
        self._validate_timestamps(diff.ts_event, diff.ts_arrival)

    @staticmethod
    def _validate_timestamps(ts_event: datetime, ts_arrival: datetime) -> None:
        if ts_arrival < ts_event:
            raise ConsistencyError(
                "arrival timestamp earlier than event", "<unknown>", None
            )

    def _validate_levels(
        self,
        instrument: str,
        sequence: int | None,
        levels: Sequence[PriceLevel],
        side: Side,
        *,
        allow_zero: bool = False,
    ) -> None:
        prev_price: Decimal | None = None
        for level in levels:
            price = level.price
            qty = level.quantity
            if self._min_price is not None and price < self._min_price:
                raise ConsistencyError(
                    f"price {price} below minimum {self._min_price}",
                    instrument,
                    sequence,
                )
            if self._min_quantity is not None and qty < self._min_quantity and qty != 0:
                raise ConsistencyError(
                    f"quantity {qty} below minimum {self._min_quantity}",
                    instrument,
                    sequence,
                )
            if qty < 0:
                raise ConsistencyError(f"negative quantity {qty}", instrument, sequence)
            if not allow_zero and qty == 0:
                raise ConsistencyError(
                    "zero quantity in snapshot", instrument, sequence
                )
            if prev_price is not None and not allow_zero:
                if side is Side.BUY and price >= prev_price:
                    raise ConsistencyError(
                        "bid levels not strictly descending", instrument, sequence
                    )
                if side is Side.SELL and price <= prev_price:
                    raise ConsistencyError(
                        "ask levels not strictly ascending", instrument, sequence
                    )
            prev_price = price


def ensure_sorted(levels: Iterable[PriceLevel], side: Side) -> bool:
    iterator = iter(levels)
    try:
        prev = next(iterator)
    except StopIteration:
        return True
    for current in iterator:
        if side is Side.BUY and current.price >= prev.price:
            return False
        if side is Side.SELL and current.price <= prev.price:
            return False
        prev = current
    return True
