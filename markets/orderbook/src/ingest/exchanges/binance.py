# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Parsers for Binance spot depth feeds."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from ..models import OrderBookDiff, OrderBookSnapshot, PriceLevel


def _levels(entries: Iterable[Sequence[str | float]]) -> tuple[PriceLevel, ...]:
    return tuple(PriceLevel.from_raw(price, quantity) for price, quantity in entries)


def parse_snapshot(
    payload: Mapping[str, object],
    *,
    instrument: str,
    ts_arrival: datetime,
    source: str = "binance",
) -> OrderBookSnapshot:
    # Type narrowing for lastUpdateId
    last_update_id_raw = payload["lastUpdateId"]
    if isinstance(last_update_id_raw, int):
        last_update_id = last_update_id_raw
    else:
        # Convert string or float to int
        last_update_id = int(str(last_update_id_raw))

    # Type narrowing for bids/asks arrays
    bids_raw = payload.get("bids", [])
    asks_raw = payload.get("asks", [])

    # Validate structure before passing to _levels
    if not isinstance(bids_raw, (list, tuple)):
        raise ValueError(f"Expected bids to be a list, got {type(bids_raw)}")
    if not isinstance(asks_raw, (list, tuple)):
        raise ValueError(f"Expected asks to be a list, got {type(asks_raw)}")

    # Runtime validation above ensures correct structure for _levels
    bids = _levels(bids_raw)
    asks = _levels(asks_raw)

    # Type narrowing for event timestamp
    raw_event = payload.get("E")
    if raw_event is None:
        ts_event = ts_arrival
    else:
        # Convert to float, handling multiple input types
        if isinstance(raw_event, (int, float)):
            event_value = float(raw_event)
        else:
            event_value = float(str(raw_event))

        if event_value > 1e12:  # millisecond precision
            event_value /= 1_000
        ts_event = datetime.fromtimestamp(event_value, tz=timezone.utc)

    if ts_arrival.tzinfo is None:
        raise ValueError("ts_arrival must be timezone aware")
    return OrderBookSnapshot(
        instrument=instrument,
        sequence=last_update_id,
        bids=bids,
        asks=asks,
        ts_event=ts_event,
        ts_arrival=ts_arrival,
        source=source,
    )


def parse_diff(
    payload: Mapping[str, object],
    *,
    ts_arrival: datetime,
    source: str = "binance",
) -> OrderBookDiff:
    instrument = str(payload["s"])
    first_update = int(payload["U"])
    final_update = int(payload["u"])
    event_time = datetime.fromtimestamp(int(payload["E"]) / 1_000, tz=timezone.utc)
    bids = _levels(payload.get("b", []))
    asks = _levels(payload.get("a", []))
    if ts_arrival.tzinfo is None:
        raise ValueError("ts_arrival must be timezone aware")
    return OrderBookDiff(
        instrument=instrument,
        sequence_start=first_update,
        sequence_end=final_update,
        bids=bids,
        asks=asks,
        ts_event=event_time,
        ts_arrival=ts_arrival,
        source=source,
    )
