# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Parsers for OKX books-l2-tbt feeds."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from ..models import OrderBookDiff, OrderBookSnapshot, PriceLevel


def _levels(entries: Iterable[Sequence[str | float]]) -> tuple[PriceLevel, ...]:
    return tuple(
        PriceLevel.from_raw(price, quantity) for price, quantity, *_ in entries
    )


def parse(
    payload: Mapping[str, object],
    *,
    ts_arrival: datetime,
    source: str = "okx",
) -> OrderBookSnapshot | OrderBookDiff:
    if ts_arrival.tzinfo is None:
        raise ValueError("ts_arrival must be timezone aware")
    data = (payload.get("data") or [None])[0]
    if data is None:
        raise ValueError("payload missing data")
    instrument = str(data.get("instId") or payload.get("arg", {}).get("instId"))
    seq = int(data["seqId"])
    prev_seq = int(data.get("prevSeqId", seq))
    ts_event = datetime.fromtimestamp(int(data["ts"]) / 1_000, tz=timezone.utc)
    bids = _levels(data.get("bids", []))
    asks = _levels(data.get("asks", []))
    action = payload.get("action") or data.get("action")

    if action == "snapshot" or prev_seq == seq:
        return OrderBookSnapshot(
            instrument=instrument,
            sequence=seq,
            bids=bids,
            asks=asks,
            ts_event=ts_event,
            ts_arrival=ts_arrival,
            source=source,
        )

    return OrderBookDiff(
        instrument=instrument,
        sequence_start=prev_seq + 1,
        sequence_end=seq,
        bids=bids,
        asks=asks,
        ts_event=ts_event,
        ts_arrival=ts_arrival,
        source=source,
    )
