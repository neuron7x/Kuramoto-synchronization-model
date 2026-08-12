# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compositional helpers for caching ticks while forming and sending TickBatchPersistedEvent notifications."""

from __future__ import annotations

import inspect
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Mapping, Protocol, Sequence

import pandas as pd
from pandas.tseries.offsets import BaseOffset

from core.data.models import InstrumentType, PriceTick

from .event_bus import MessageBroker, NullMessageBroker
from .events import (
    BrokeredTickEventPublisher,
    NullTickEventPublisher,
    TickEventPublisher,
    build_tick_event,
    default_tick_header_factory,
)
from .ingestion_service import DataIngestionCacheService
from .kafka_ingestion import KafkaIngestionConfig, KafkaIngestionService, LagHandler

if TYPE_CHECKING:
    from .events import HeaderFactory
    from .streaming_aggregator import TickStreamAggregator


class TickRoutingStrategy(Protocol):
    """Decide how incoming ticks should be routed to cache layers."""

    def route(
        self, tick: PriceTick
    ) -> "CacheRoute | None":  # pragma: no cover - protocol
        """Return the cache route for ``tick`` or ``None`` to drop it."""


@dataclass(frozen=True, slots=True)
class CacheRoute:
    """Cache metadata describing where a batch of ticks should be stored."""

    layer: str
    timeframe: str
    market: str | None = None


@dataclass(slots=True)
class StaticTickRoutingStrategy:
    """Route every tick to the same cache layer and timeframe."""

    route_template: CacheRoute

    def route(self, tick: PriceTick) -> CacheRoute | None:  # pragma: no cover - trivial
        return self.route_template


class CacheWriterTickHandler:
    """Persist decoded tick batches into the ingestion cache."""

    def __init__(
        self,
        *,
        cache_service: DataIngestionCacheService,
        routing_strategy: TickRoutingStrategy,
        event_publisher: TickEventPublisher | None = None,
    ) -> None:
        self._cache_service = cache_service
        self._routing_strategy = routing_strategy
        self._event_publisher = event_publisher or NullTickEventPublisher()

    async def __call__(self, ticks: Sequence[PriceTick]) -> None:
        """Group ticks by cache route and persist them."""

        if not ticks:
            return

        buckets: Dict[tuple[CacheRoute, str, str, InstrumentType], list[PriceTick]] = (
            defaultdict(list)
        )
        for tick in ticks:
            route = self._routing_strategy.route(tick)
            if route is None:
                continue
            key = (route, tick.symbol, tick.venue, tick.instrument_type)
            buckets[key].append(tick)

        for (route, symbol, venue, instrument_type), bucket in buckets.items():
            if not bucket:
                continue
            self._cache_service.cache_ticks(
                bucket,
                layer=route.layer,
                symbol=symbol,
                venue=venue,
                timeframe=route.timeframe,
                market=route.market,
                instrument_type=instrument_type,
            )
            event = build_tick_event(
                route=route,
                symbol=symbol,
                venue=venue,
                instrument_type=instrument_type,
                ticks=bucket,
            )
            await self._event_publisher.publish_batch(event)

    @property
    def event_publisher(self) -> TickEventPublisher:
        return self._event_publisher


class StreamingIngestionPipeline:
    """Wire Kafka ingestion with cache writers and aggregators."""

    def __init__(
        self,
        *,
        kafka_config: KafkaIngestionConfig,
        cache_service: DataIngestionCacheService | None = None,
        routing_strategy: TickRoutingStrategy | None = None,
        lag_handler: LagHandler | None = None,
        message_broker: MessageBroker | None = None,
        tick_event_publisher: TickEventPublisher | None = None,
        tick_event_topic: str = "geosync.data.tick_batch.persisted",
        tick_header_factory: "HeaderFactory" | None = None,
        kafka_service_factory: (
            Callable[[KafkaIngestionConfig], KafkaIngestionService]
            | Callable[..., KafkaIngestionService]
            | None
        ) = None,
        kafka_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        self._cache_service = cache_service or DataIngestionCacheService()
        default_route = CacheRoute(layer="raw", timeframe="1min")
        self._routing_strategy = routing_strategy or StaticTickRoutingStrategy(
            route_template=default_route
        )
        broker = message_broker or NullMessageBroker()
        if tick_event_publisher is not None:
            self._event_publisher = tick_event_publisher
        elif message_broker is not None:
            self._event_publisher = BrokeredTickEventPublisher(
                broker,
                topic=tick_event_topic,
                header_factory=tick_header_factory or default_tick_header_factory,
            )
        else:
            self._event_publisher = NullTickEventPublisher()
        self._message_broker = broker
        self._tick_handler = CacheWriterTickHandler(
            cache_service=self._cache_service,
            routing_strategy=self._routing_strategy,
            event_publisher=self._event_publisher,
        )
        self._lag_handler = lag_handler
        factory = kafka_service_factory or self._build_kafka_service
        kwargs: Dict[str, Any] = dict(kafka_kwargs or {})
        if "tick_handler" in kwargs or "lag_handler" in kwargs:
            raise ValueError(
                "tick_handler and lag_handler must not be provided in kafka_kwargs"
            )
        supports = self._inspect_factory_support(factory)
        if supports is None:
            try:
                self._kafka_service = factory(
                    kafka_config,
                    tick_handler=self._tick_handler,
                    lag_handler=self._lag_handler,
                    **kwargs,
                )
            except TypeError as exc:
                if self._is_unexpected_handler_type_error(exc):
                    try:
                        self._kafka_service = factory(kafka_config, **kwargs)
                    except TypeError:
                        raise exc
                else:
                    raise
        else:
            supports_tick_handler, supports_lag_handler = supports
            call_kwargs = dict(kwargs)
            if supports_tick_handler:
                call_kwargs["tick_handler"] = self._tick_handler
            if supports_lag_handler:
                call_kwargs["lag_handler"] = self._lag_handler
            self._kafka_service = factory(kafka_config, **call_kwargs)

        self._ensure_kafka_service_handlers()

    @staticmethod
    def _inspect_factory_support(
        factory: Callable[..., KafkaIngestionService],
    ) -> tuple[bool, bool] | None:
        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            return None

        has_var_keyword = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if has_var_keyword:
            return True, True

        supports_tick_handler = "tick_handler" in signature.parameters
        supports_lag_handler = "lag_handler" in signature.parameters
        return supports_tick_handler, supports_lag_handler

    @staticmethod
    def _is_unexpected_handler_type_error(exc: TypeError) -> bool:
        message = str(exc)
        unexpected_kw_fragments = (
            "unexpected keyword argument",
            "got an unexpected keyword argument",
        )
        if not any(fragment in message for fragment in unexpected_kw_fragments):
            return False
        return "tick_handler" in message or "lag_handler" in message

    def _ensure_kafka_service_handlers(self) -> None:
        service = self._kafka_service
        if not hasattr(service, "tick_handler"):
            setattr(service, "tick_handler", self._tick_handler)
        else:
            current_tick_handler = getattr(service, "tick_handler")
            if current_tick_handler is None:
                setattr(service, "tick_handler", self._tick_handler)

        if self._lag_handler is None:
            return

        if not hasattr(service, "lag_handler"):
            setattr(service, "lag_handler", self._lag_handler)
            return

        current_lag_handler = getattr(service, "lag_handler")
        if current_lag_handler is None:
            setattr(service, "lag_handler", self._lag_handler)

    @staticmethod
    def _build_kafka_service(
        config: KafkaIngestionConfig,
        *,
        tick_handler: CacheWriterTickHandler,
        lag_handler: LagHandler | None,
        **kwargs: Any,
    ) -> KafkaIngestionService:
        return KafkaIngestionService(
            config,
            tick_handler=tick_handler,
            lag_handler=lag_handler,
            **kwargs,
        )

    @property
    def cache_service(self) -> DataIngestionCacheService:
        return self._cache_service

    @property
    def kafka_service(self) -> KafkaIngestionService:
        return self._kafka_service

    @property
    def routing_strategy(self) -> TickRoutingStrategy:
        return self._routing_strategy

    @property
    def tick_handler(self) -> CacheWriterTickHandler:
        return self._tick_handler

    @property
    def message_broker(self) -> MessageBroker:
        return self._message_broker

    @property
    def event_publisher(self) -> TickEventPublisher:
        return self._event_publisher

    async def start(self) -> None:
        await self._message_broker.start()
        try:
            await self._kafka_service.start()
        except Exception:
            await self._message_broker.stop()
            raise

    async def stop(self) -> None:
        try:
            await self._kafka_service.stop()
        finally:
            await self._message_broker.stop()

    def create_aggregator(
        self,
        route: CacheRoute,
        *,
        frequency: str | pd.Timedelta | BaseOffset | None = None,
    ) -> TickStreamAggregator:
        from .streaming_aggregator import TickStreamAggregator

        return TickStreamAggregator(
            cache_service=self._cache_service,
            layer=route.layer,
            timeframe=route.timeframe,
            market=route.market,
            frequency=frequency or route.timeframe,
        )


__all__ = [
    "CacheRoute",
    "CacheWriterTickHandler",
    "StaticTickRoutingStrategy",
    "StreamingIngestionPipeline",
    "TickRoutingStrategy",
]
