# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Domain events emitted by data ingestion pipelines."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Mapping, Protocol, Sequence

from core.data.models import InstrumentType, PriceTick

if TYPE_CHECKING:
    from .event_bus import MessageBroker


@dataclass(frozen=True, slots=True)
class TickBatchPersistedEvent:
    """Metadata describing a batch of ticks stored in the cache."""

    layer: str
    timeframe: str
    symbol: str
    venue: str
    instrument_type: InstrumentType
    market: str | None
    batch_size: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None

    def to_payload(self) -> bytes:
        payload = {
            "event_type": "data.tick_batch.persisted",
            "layer": self.layer,
            "timeframe": self.timeframe,
            "symbol": self.symbol,
            "venue": self.venue,
            "instrument_type": self.instrument_type.value,
            "market": self.market,
            "batch_size": self.batch_size,
            "first_timestamp": _isoformat(self.first_timestamp),
            "last_timestamp": _isoformat(self.last_timestamp),
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )


class TickEventPublisher(Protocol):
    """Publish events describing pipeline activity."""

    async def publish_batch(
        self, event: TickBatchPersistedEvent
    ) -> None:  # pragma: no cover - protocol definition
        """Publish ``event`` to downstream consumers."""


class NullTickEventPublisher:
    """Fallback publisher that drops all events."""

    async def publish_batch(self, event: TickBatchPersistedEvent) -> None:
        return None


class BrokeredTickEventPublisher:
    """Publish tick events using a :class:`~src.data.event_bus.MessageBroker`."""

    def __init__(
        self,
        broker: "MessageBroker",
        *,
        topic: str,
        header_factory: "HeaderFactory" | None = None,
    ) -> None:
        self._broker = broker
        self._topic = topic
        self._header_factory = header_factory or default_tick_header_factory

    async def publish_batch(self, event: TickBatchPersistedEvent) -> None:
        from .event_bus import BrokerMessage

        headers = self._header_factory(event)
        message = BrokerMessage(
            topic=self._topic, payload=event.to_payload(), headers=headers
        )
        await self._broker.publish(message)


HeaderFactory = Callable[[TickBatchPersistedEvent], Mapping[str, str]]


class CacheRouteLike(Protocol):
    layer: str
    timeframe: str
    market: str | None


def default_tick_header_factory(event: TickBatchPersistedEvent) -> Mapping[str, str]:
    """Build a compact header map for broker transports."""

    headers = {
        "event_type": "data.tick_batch.persisted",
        "symbol": event.symbol,
        "venue": event.venue,
        "timeframe": event.timeframe,
    }
    if event.market is not None:
        headers["market"] = event.market
    return headers


def build_tick_event(
    *,
    route: CacheRouteLike,
    symbol: str,
    venue: str,
    instrument_type: InstrumentType,
    ticks: Sequence[PriceTick],
) -> TickBatchPersistedEvent:
    """Create an event payload for ``ticks`` stored in ``route``."""

    if not ticks:
        raise ValueError(
            "ticks must not be empty when creating TickBatchPersistedEvent"
        )
    first_ts = min(tick.timestamp for tick in ticks)
    last_ts = max(tick.timestamp for tick in ticks)
    return TickBatchPersistedEvent(
        layer=route.layer,
        timeframe=route.timeframe,
        symbol=symbol,
        venue=venue,
        instrument_type=instrument_type,
        market=route.market,
        batch_size=len(ticks),
        first_timestamp=first_ts,
        last_timestamp=last_ts,
    )


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "CacheRouteLike",
    "BrokeredTickEventPublisher",
    "NullTickEventPublisher",
    "TickBatchPersistedEvent",
    "TickEventPublisher",
    "build_tick_event",
    "default_tick_header_factory",
]
