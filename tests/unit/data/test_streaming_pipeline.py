# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pytest

from core.data.catalog import normalize_symbol
from core.data.models import InstrumentType, PriceTick
from src.data.ingestion_service import DataIngestionCacheService
from src.data.kafka_ingestion import KafkaIngestionConfig, LagHandler
from src.data.pipeline import (
    CacheRoute,
    CacheWriterTickHandler,
    StaticTickRoutingStrategy,
    StreamingIngestionPipeline,
)


@dataclass
class _RecordingCall:
    symbol: str
    venue: str
    layer: str
    timeframe: str
    market: str | None
    instrument_type: InstrumentType
    tick_count: int


class _RecordingCacheService:
    def __init__(self) -> None:
        self.calls: list[_RecordingCall] = []

    def cache_ticks(
        self,
        ticks: list[PriceTick],
        *,
        layer: str,
        symbol: str,
        venue: str,
        timeframe: str,
        market: str | None,
        instrument_type: InstrumentType,
    ) -> pd.DataFrame:
        self.calls.append(
            _RecordingCall(
                symbol=symbol,
                venue=venue,
                layer=layer,
                timeframe=timeframe,
                market=market,
                instrument_type=instrument_type,
                tick_count=len(ticks),
            )
        )
        return pd.DataFrame()


class _FilterStrategy(StaticTickRoutingStrategy):
    def __init__(
        self,
        *,
        include_symbol: str,
        route: CacheRoute,
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> None:
        super().__init__(route_template=route)
        self._include_symbol = normalize_symbol(
            include_symbol, instrument_type_hint=instrument_type
        )

    def route(self, tick: PriceTick) -> CacheRoute | None:
        if tick.symbol == self._include_symbol:
            return self.route_template
        return None


class _StubKafkaService:
    def __init__(self, config: KafkaIngestionConfig, **kwargs: Any) -> None:
        self.config = config
        self.kwargs = kwargs
        self.tick_handler = kwargs.get("tick_handler")
        self.lag_handler = kwargs.get("lag_handler")
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


class _LagOptionalService:
    def __init__(self, config: KafkaIngestionConfig) -> None:
        self.config = config
        self.tick_handler: CacheWriterTickHandler | None = None
        self.lag_handler: LagHandler | None = None


def _tick(symbol: str, *, price: float, when: datetime) -> PriceTick:
    return PriceTick.create(
        symbol=symbol,
        venue="coinbase",
        price=price,
        timestamp=when,
        volume=0.1,
        instrument_type=InstrumentType.SPOT,
    )


@pytest.mark.asyncio
async def test_cache_writer_groups_ticks_per_route() -> None:
    cache = _RecordingCacheService()
    route = CacheRoute(layer="raw", timeframe="1s", market="crypto")
    handler = CacheWriterTickHandler(
        cache_service=cache,
        routing_strategy=StaticTickRoutingStrategy(route_template=route),
    )
    now = datetime.now(timezone.utc)
    ticks = [
        _tick("BTCUSD", price=100.0, when=now),
        _tick("BTCUSD", price=100.5, when=now + timedelta(seconds=1)),
        _tick("ETHUSD", price=50.0, when=now + timedelta(seconds=2)),
    ]

    await handler(ticks)

    assert len(cache.calls) == 2
    first, second = cache.calls
    assert first.symbol == ticks[0].symbol
    assert first.tick_count == 2
    assert first.layer == "raw"
    assert first.timeframe == "1s"
    assert first.market == "crypto"
    assert second.symbol == ticks[2].symbol
    assert second.tick_count == 1


@pytest.mark.asyncio
async def test_cache_writer_ignores_unrouted_ticks() -> None:
    cache = _RecordingCacheService()
    route = CacheRoute(layer="raw", timeframe="1s")
    handler = CacheWriterTickHandler(
        cache_service=cache,
        routing_strategy=_FilterStrategy(include_symbol="BTCUSD", route=route),
    )
    now = datetime.now(timezone.utc)
    ticks = [
        _tick("BTCUSD", price=100.0, when=now),
        _tick("ETHUSD", price=50.0, when=now + timedelta(seconds=1)),
    ]

    await handler(ticks)

    assert len(cache.calls) == 1
    recorded = cache.calls[0]
    assert recorded.symbol == ticks[0].symbol


@pytest.mark.asyncio
async def test_cache_writer_no_ticks_avoids_cache_calls() -> None:
    cache = _RecordingCacheService()
    handler = CacheWriterTickHandler(
        cache_service=cache,
        routing_strategy=StaticTickRoutingStrategy(
            route_template=CacheRoute(layer="raw", timeframe="1s")
        ),
    )

    await handler([])

    assert cache.calls == []


@pytest.mark.asyncio
async def test_cache_writer_large_batch_is_deterministic() -> None:
    cache = _RecordingCacheService()
    handler = CacheWriterTickHandler(
        cache_service=cache,
        routing_strategy=StaticTickRoutingStrategy(
            route_template=CacheRoute(layer="raw", timeframe="1s", market="crypto")
        ),
    )
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [
        _tick("BTCUSD", price=100.0 + idx, when=now + timedelta(milliseconds=idx))
        for idx in range(500)
    ] + [
        _tick("ETHUSD", price=50.0 + idx, when=now + timedelta(milliseconds=idx))
        for idx in range(750)
    ]

    await handler(ticks)
    await handler(ticks)

    assert len(cache.calls) == 4
    first_pass = cache.calls[:2]
    second_pass = cache.calls[2:]
    assert [call.tick_count for call in first_pass] == [500, 750]
    assert [call.tick_count for call in second_pass] == [500, 750]
    assert first_pass[0].market == "crypto" and second_pass[0].market == "crypto"


@pytest.mark.asyncio
async def test_pipeline_exposes_composed_services() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    route = CacheRoute(layer="raw", timeframe="1s")
    created: list[_StubKafkaService] = []

    def factory(
        cfg: KafkaIngestionConfig,
        *,
        tick_handler: CacheWriterTickHandler,
        **kwargs: Any,
    ) -> _StubKafkaService:
        service = _StubKafkaService(cfg, tick_handler=tick_handler, **kwargs)
        created.append(service)
        return service

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        routing_strategy=StaticTickRoutingStrategy(route_template=route),
        kafka_service_factory=factory,
    )

    assert created and pipeline.kafka_service is created[0]
    assert pipeline.kafka_service.tick_handler is pipeline.tick_handler

    await pipeline.start()
    await pipeline.stop()

    assert pipeline.kafka_service.started == 1
    assert pipeline.kafka_service.stopped == 1


@pytest.mark.asyncio
async def test_pipeline_aggregator_operates_on_shared_cache() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    cache_service = DataIngestionCacheService()
    route = CacheRoute(layer="raw", timeframe="1s")

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        cache_service=cache_service,
        routing_strategy=StaticTickRoutingStrategy(route_template=route),
        kafka_service_factory=lambda cfg, **kwargs: _StubKafkaService(cfg, **kwargs),
    )

    now = datetime.now(timezone.utc)
    ticks = [
        _tick("BTCUSD", price=100 + idx, when=now + timedelta(seconds=idx))
        for idx in range(3)
    ]

    await pipeline.tick_handler(ticks)

    aggregator = pipeline.create_aggregator(route)
    result = aggregator.synchronise(symbol="BTCUSD", venue="coinbase")

    assert result.frame.shape[0] == 3
    assert result.key.timeframe == "1s"


@pytest.mark.asyncio
async def test_pipeline_accepts_minimal_kafka_factory_signature() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    route = CacheRoute(layer="raw", timeframe="1s")

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        routing_strategy=StaticTickRoutingStrategy(route_template=route),
        kafka_service_factory=lambda cfg: _StubKafkaService(cfg),
    )

    assert isinstance(pipeline.kafka_service, _StubKafkaService)
    assert pipeline.kafka_service.tick_handler is pipeline.tick_handler
    assert pipeline.kafka_service.lag_handler is None

    await pipeline.start()
    await pipeline.stop()

    assert pipeline.kafka_service.started == 1
    assert pipeline.kafka_service.stopped == 1


def test_pipeline_rejects_tick_handler_in_kafka_kwargs() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )

    with pytest.raises(ValueError, match="must not be provided"):
        StreamingIngestionPipeline(
            kafka_config=config,
            kafka_kwargs={"tick_handler": object()},
        )


def test_pipeline_rejects_lag_handler_in_kafka_kwargs() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )

    with pytest.raises(ValueError, match="must not be provided"):
        StreamingIngestionPipeline(
            kafka_config=config,
            kafka_kwargs={"lag_handler": object()},
        )


def test_pipeline_respects_explicit_lag_handler() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    lag_handler = object()
    created: list[_StubKafkaService] = []

    def factory(
        cfg: KafkaIngestionConfig,
        *,
        tick_handler: CacheWriterTickHandler,
        lag_handler: object | None,
        **kwargs: Any,
    ) -> _StubKafkaService:
        service = _StubKafkaService(
            cfg,
            tick_handler=tick_handler,
            lag_handler=lag_handler,
            **kwargs,
        )
        created.append(service)
        return service

    StreamingIngestionPipeline(
        kafka_config=config,
        lag_handler=lag_handler,
        kafka_service_factory=factory,
    )

    assert created and created[0].lag_handler is lag_handler


def test_pipeline_overrides_none_lag_handler_attribute() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    lag_handler = object()

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        lag_handler=lag_handler,
        kafka_service_factory=lambda cfg: _LagOptionalService(cfg),
    )

    assert isinstance(pipeline.kafka_service, _LagOptionalService)
    assert pipeline.kafka_service.tick_handler is pipeline.tick_handler
    assert pipeline.kafka_service.lag_handler is lag_handler


def test_pipeline_omits_lag_handler_when_factory_does_not_accept_it() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    lag_handler = object()
    captured_tick_handler: CacheWriterTickHandler | None = None

    def factory(
        cfg: KafkaIngestionConfig, *, tick_handler: CacheWriterTickHandler
    ) -> _StubKafkaService:
        nonlocal captured_tick_handler
        captured_tick_handler = tick_handler
        return _StubKafkaService(cfg)

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        lag_handler=lag_handler,
        kafka_service_factory=factory,
    )

    assert captured_tick_handler is pipeline.tick_handler


def test_pipeline_omits_tick_handler_when_factory_only_accepts_lag() -> None:
    config = KafkaIngestionConfig(
        topic="ticks",
        bootstrap_servers="kafka:9092",
        group_id="geosync-test",
    )
    lag_handler = object()
    captured_lag_handler: object | None = None

    def factory(
        cfg: KafkaIngestionConfig, *, lag_handler: object | None
    ) -> _StubKafkaService:
        nonlocal captured_lag_handler
        captured_lag_handler = lag_handler
        return _StubKafkaService(cfg)

    StreamingIngestionPipeline(
        kafka_config=config,
        lag_handler=lag_handler,
        kafka_service_factory=factory,
    )

    assert captured_lag_handler is lag_handler
