"""Compositional helpers to assemble streaming ingestion pipelines."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Mapping, Protocol, Sequence

import pandas as pd
from pandas.tseries.offsets import BaseOffset

from core.data.models import InstrumentType, PriceTick

from .ingestion_service import DataIngestionCacheService
from .kafka_ingestion import KafkaIngestionConfig, KafkaIngestionService, LagHandler

if TYPE_CHECKING:
    from .streaming_aggregator import TickStreamAggregator


class TickRoutingStrategy(Protocol):
    """Decide how incoming ticks should be routed to cache layers."""

    def route(self, tick: PriceTick) -> "CacheRoute | None":  # pragma: no cover - protocol
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
    ) -> None:
        self._cache_service = cache_service
        self._routing_strategy = routing_strategy

    async def __call__(self, ticks: Sequence[PriceTick]) -> None:
        """Group ticks by cache route and persist them."""

        if not ticks:
            return

        buckets: Dict[
            tuple[CacheRoute, str, str, InstrumentType], list[PriceTick]
        ] = defaultdict(list)
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


class StreamingIngestionPipeline:
    """Wire Kafka ingestion with cache writers and aggregators."""

    def __init__(
        self,
        *,
        kafka_config: KafkaIngestionConfig,
        cache_service: DataIngestionCacheService | None = None,
        routing_strategy: TickRoutingStrategy | None = None,
        lag_handler: LagHandler | None = None,
        kafka_service_factory: Callable[
            [KafkaIngestionConfig], KafkaIngestionService
        ]
        | Callable[..., KafkaIngestionService]
        | None = None,
        kafka_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        self._cache_service = cache_service or DataIngestionCacheService()
        default_route = CacheRoute(layer="raw", timeframe="1min")
        self._routing_strategy = routing_strategy or StaticTickRoutingStrategy(
            route_template=default_route
        )
        self._tick_handler = CacheWriterTickHandler(
            cache_service=self._cache_service,
            routing_strategy=self._routing_strategy,
        )
        self._lag_handler = lag_handler
        factory = kafka_service_factory or self._build_kafka_service
        kwargs: Dict[str, Any] = dict(kafka_kwargs or {})
        if "tick_handler" in kwargs or "lag_handler" in kwargs:
            raise ValueError(
                "tick_handler and lag_handler must not be provided in kafka_kwargs"
            )
        self._kafka_service = factory(
            kafka_config,
            tick_handler=self._tick_handler,
            lag_handler=self._lag_handler,
            **kwargs,
        )

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

    async def start(self) -> None:
        await self._kafka_service.start()

    async def stop(self) -> None:
        await self._kafka_service.stop()

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
