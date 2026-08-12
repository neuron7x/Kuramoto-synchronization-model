# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""State management for level 2 order book ingestion."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import RLock
from typing import Dict, Iterable, List, Tuple

from markets.orderbook.src.core.lob import Side

from .models import AppliedDiff, OrderBookDiff, OrderBookSnapshot, PriceLevel


class OrderBookStateError(Exception):
    """Raised for invalid state transitions."""


@dataclass(slots=True)
class SnapshotRecord:
    sequence: int
    ts_event: datetime
    ts_arrival: datetime
    bids: Tuple[PriceLevel, ...]
    asks: Tuple[PriceLevel, ...]
    source: str

    def to_snapshot(self, instrument: str) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            instrument=instrument,
            sequence=self.sequence,
            bids=self.bids,
            asks=self.asks,
            ts_event=self.ts_event,
            ts_arrival=self.ts_arrival,
            source=self.source,
        )


class _PriceLevelStore:
    """Compact price level storage maintaining sorted price arrays."""

    __slots__ = ("_side", "_prices", "_quantities")

    def __init__(self, side: Side) -> None:
        self._side = side
        self._prices: List[Decimal] = []
        self._quantities: Dict[Decimal, Decimal] = {}

    def clear(self) -> None:
        self._prices.clear()
        self._quantities.clear()

    def update(self, level: PriceLevel) -> None:
        price = level.price
        qty = level.quantity
        if qty <= 0:
            if price in self._quantities:
                del self._quantities[price]
                index = bisect.bisect_left(self._prices, price)
                if index < len(self._prices) and self._prices[index] == price:
                    self._prices.pop(index)
            return

        if price in self._quantities:
            self._quantities[price] = qty
            return

        index = bisect.bisect_left(self._prices, price)
        self._prices.insert(index, price)
        self._quantities[price] = qty

    def levels(self, depth: int | None = None) -> Tuple[PriceLevel, ...]:
        prices = self._prices if self._side is Side.SELL else reversed(self._prices)
        result: List[PriceLevel] = []
        for price in prices:
            qty = self._quantities[price]
            result.append(PriceLevel(price=price, quantity=qty))
            if depth is not None and len(result) >= depth:
                break
        return tuple(result)

    def top(self) -> PriceLevel | None:
        if not self._prices:
            return None
        price = self._prices[-1] if self._side is Side.BUY else self._prices[0]
        qty = self._quantities[price]
        return PriceLevel(price=price, quantity=qty)


class InstrumentOrderBookState:
    """Thread-safe state for a single trading instrument."""

    __slots__ = (
        "_instrument",
        "_bids",
        "_asks",
        "_sequence",
        "_last_event",
        "_last_arrival",
        "_lock",
        "_snapshot_history",
        "_snapshot_times",
        "_max_snapshots",
    )

    def __init__(self, instrument: str, *, max_snapshots: int = 32) -> None:
        self._instrument = instrument
        self._bids = _PriceLevelStore(Side.BUY)
        self._asks = _PriceLevelStore(Side.SELL)
        self._sequence: int | None = None
        self._last_event: datetime | None = None
        self._last_arrival: datetime | None = None
        self._lock = RLock()
        self._snapshot_history: List[SnapshotRecord] = []
        self._snapshot_times: List[datetime] = []
        self._max_snapshots = max(1, max_snapshots)

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------
    def apply_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        with self._lock:
            self._sequence = snapshot.sequence
            self._last_event = snapshot.ts_event
            self._last_arrival = snapshot.ts_arrival
            self._bids.clear()
            self._asks.clear()
            for level in snapshot.bids:
                self._bids.update(level)
            for level in snapshot.asks:
                self._asks.update(level)
            self._store_snapshot(snapshot)

    def _store_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        record = SnapshotRecord(
            sequence=snapshot.sequence,
            ts_event=snapshot.ts_event,
            ts_arrival=snapshot.ts_arrival,
            bids=tuple(snapshot.bids),
            asks=tuple(snapshot.asks),
            source=snapshot.source,
        )
        idx = bisect.bisect_left(self._snapshot_times, record.ts_event)
        self._snapshot_times.insert(idx, record.ts_event)
        self._snapshot_history.insert(idx, record)
        if len(self._snapshot_history) > self._max_snapshots:
            self._snapshot_history.pop(0)
            self._snapshot_times.pop(0)

    def get_snapshot(self, depth: int | None = None) -> OrderBookSnapshot:
        with self._lock:
            if self._sequence is None or self._last_event is None or self._last_arrival is None:
                raise OrderBookStateError("snapshot requested before baseline available")
            return OrderBookSnapshot(
                instrument=self._instrument,
                sequence=self._sequence,
                bids=self._bids.levels(depth),
                asks=self._asks.levels(depth),
                ts_event=self._last_event,
                ts_arrival=self._last_arrival,
                source="state",
            )

    def snapshot_before(self, ts_event: datetime) -> OrderBookSnapshot | None:
        with self._lock:
            idx = bisect.bisect_right(self._snapshot_times, ts_event)
            if idx == 0:
                return None
            record = self._snapshot_history[idx - 1]
            return record.to_snapshot(self._instrument)

    # ------------------------------------------------------------------
    # Diff application
    # ------------------------------------------------------------------
    def apply_diff(self, diff: OrderBookDiff) -> AppliedDiff | None:
        with self._lock:
            if self._sequence is None:
                return None
            expected_sequence = self._sequence + 1
            if diff.sequence_end < expected_sequence:
                return None
            if diff.sequence_start > expected_sequence:
                raise OrderBookStateError(
                    f"sequence gap detected: expected {expected_sequence} got {diff.sequence_start}"
                )
            for level in diff.bids:
                self._bids.update(level)
            for level in diff.asks:
                self._asks.update(level)
            self._sequence = diff.sequence_end
            self._last_event = diff.ts_event
            self._last_arrival = diff.ts_arrival
            return AppliedDiff(
                instrument=self._instrument,
                sequence=self._sequence,
                ts_event=diff.ts_event,
                ts_arrival=diff.ts_arrival,
            )

    def best_bid(self) -> PriceLevel | None:
        return self._bids.top()

    def best_ask(self) -> PriceLevel | None:
        return self._asks.top()


class OrderBookStore:
    """Container managing multiple instrument states."""

    def __init__(self, *, max_snapshots: int = 32) -> None:
        self._states: Dict[str, InstrumentOrderBookState] = {}
        self._lock = RLock()
        self._max_snapshots = max_snapshots

    def for_instrument(self, instrument: str) -> InstrumentOrderBookState:
        with self._lock:
            state = self._states.get(instrument)
            if state is None:
                state = InstrumentOrderBookState(instrument, max_snapshots=self._max_snapshots)
                self._states[instrument] = state
            return state

    def snapshot(self, instrument: str, depth: int | None = None) -> OrderBookSnapshot:
        return self.for_instrument(instrument).get_snapshot(depth)

    def snapshot_before(self, instrument: str, ts_event: datetime) -> OrderBookSnapshot | None:
        return self.for_instrument(instrument).snapshot_before(ts_event)

    def instruments(self) -> Iterable[str]:
        with self._lock:
            return tuple(self._states.keys())
