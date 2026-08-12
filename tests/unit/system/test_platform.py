# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pytest

from application.system import (
    ExchangeAdapterConfig,
    GeoSyncSystem,
    GeoSyncSystemConfig,
)
from application.system_orchestrator import MarketDataSource
from core.data.models import InstrumentType, PriceTick
from execution.connectors import SimulatedExchangeConnector
from src.audit.audit_logger import AuditLogger
from src.data.ingestion_service import DataIngestionCacheService
from src.data.kafka_ingestion import KafkaIngestionConfig
from src.data.pipeline import CacheRoute
from src.system import (
    GeoSyncPlatform,
    StreamingPipelineSettings,
    build_geosync_platform,
)


class _StubStreamingPipeline:
    def __init__(self, cache_service: DataIngestionCacheService) -> None:
        self.cache_service = cache_service
        self.created: list[tuple[CacheRoute, str | pd.Timedelta | object | None]] = []
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    def create_aggregator(self, route: CacheRoute, *, frequency: str | pd.Timedelta | None = None):
        self.created.append((route, frequency))
        from src.data.streaming_aggregator import TickStreamAggregator

        return TickStreamAggregator(
            cache_service=self.cache_service,
            layer=route.layer,
            timeframe=route.timeframe,
            market=route.market,
            frequency=frequency or route.timeframe,
        )


class _StubKafkaService:
    def __init__(
        self,
        config: KafkaIngestionConfig,
        *,
        tick_handler,
        lag_handler=None,
        **kwargs,
    ) -> None:
        self.config = config
        self.tick_handler = tick_handler
        self.lag_handler = lag_handler
        self.kwargs = kwargs
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def _venues() -> tuple[ExchangeAdapterConfig, ...]:
    connector = SimulatedExchangeConnector()
    return (ExchangeAdapterConfig(name="sim", connector=connector),)


def _build_platform(
    *,
    audit_secret: str = "integration-platform-secret",
    cache_service: DataIngestionCacheService | None = None,
    streaming_pipeline: _StubStreamingPipeline | None = None,
    allowed_data_roots: Iterable[str | Path] | None = None,
) -> GeoSyncPlatform:
    kwargs: dict[str, object] = {}
    if cache_service is not None:
        kwargs["cache_service"] = cache_service
    if streaming_pipeline is not None:
        kwargs["streaming_pipeline"] = streaming_pipeline
    if allowed_data_roots is not None:
        kwargs["allowed_data_roots"] = allowed_data_roots
    return build_geosync_platform(
        venues=_venues(),
        audit_secret=audit_secret,
        **kwargs,
    )


def test_build_geosync_platform_requires_audit_credentials() -> None:
    with pytest.raises(ValueError):
        build_geosync_platform(venues=_venues())


def test_build_geosync_platform_rejects_conflicting_audit_dependencies() -> None:
    with pytest.raises(ValueError):
        build_geosync_platform(
            venues=_venues(),
            audit_logger=AuditLogger(secret="explicit"),
            audit_secret="redundant",
        )


def test_build_geosync_platform_allows_audit_secret_resolver() -> None:
    secret_calls: list[str] = []

    def resolver() -> str:
        secret_calls.append("resolver")
        return "resolved-secret"

    platform = build_geosync_platform(
        venues=_venues(),
        audit_secret_resolver=resolver,
    )

    record = platform.log_audit_event(
        event_type="integration.test",
        actor="resolver",  # reuse actor field to avoid duplicates
        ip_address="198.51.100.11",
    )

    assert secret_calls == ["resolver"]
    assert platform.audit_logger.verify(record) is True


def test_platform_wires_components_and_audit_logging() -> None:
    platform = _build_platform()

    record = platform.log_audit_event(
        event_type="integration.test",
        actor="tester",
        ip_address="198.51.100.10",
        details={"scope": "unit"},
    )

    assert platform.audit_logger.verify(record) is True
    assert platform.risk_manager.risk_manager is platform.system.risk_manager


def test_platform_run_strategy_end_to_end() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    sample_csv = repo_root / "data" / "sample.csv"

    platform = _build_platform(allowed_data_roots=[sample_csv.parent])

    source = MarketDataSource(path=sample_csv, symbol="BTCUSDT", venue="CSV")

    def strategy(prices: np.ndarray) -> np.ndarray:
        return np.where(prices >= prices.mean(), 1.0, -1.0)

    run = platform.run_strategy(source, strategy=strategy)

    assert not run.market_frame.empty
    assert not run.feature_frame.empty
    assert run.signals


def test_platform_ingest_csv_updates_cache_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    sample_csv = repo_root / "data" / "sample.csv"
    cache_service = DataIngestionCacheService()

    platform = _build_platform(
        cache_service=cache_service,
        allowed_data_roots=[sample_csv.parent],
    )

    frame = platform.ingest_csv(
        str(sample_csv),
        symbol="BTCUSD",
        venue="CSV",
        timeframe="1s",
    )

    assert not frame.empty
    metadata = platform.metadata_for(layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1s")
    assert metadata is not None
    assert metadata.rows == frame.shape[0]


def test_platform_create_aggregator_without_pipeline_uses_shared_cache() -> None:
    cache_service = DataIngestionCacheService()
    platform = _build_platform(cache_service=cache_service)

    route = CacheRoute(layer="raw", timeframe="1min")
    aggregator = platform.create_aggregator(route)

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    tick = PriceTick.create(
        symbol="BTCUSD",
        venue="CSV",
        price=100.0,
        timestamp=base,
        volume=1.0,
        instrument_type=InstrumentType.SPOT,
    )

    result = aggregator.synchronise(
        symbol="BTCUSD",
        venue="CSV",
        instrument_type=InstrumentType.SPOT,
        historical=[tick],
    )

    metadata = platform.metadata_for(layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1min")
    assert metadata is not None
    assert metadata.rows == 1
    assert result.frame.shape[0] == 1


def test_platform_create_aggregator_with_pipeline_delegates() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(cache_service)
    platform = _build_platform(
        cache_service=cache_service,
        streaming_pipeline=pipeline,
    )

    route = CacheRoute(layer="raw", timeframe="1s")
    aggregator = platform.create_aggregator(route, frequency="1s")

    assert pipeline.created == [(route, "1s")]

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [
        PriceTick.create(
            symbol="BTCUSD",
            venue="CSV",
            price=100.0 + idx,
            timestamp=base + timedelta(seconds=idx),
            volume=1.0,
            instrument_type=InstrumentType.SPOT,
        )
        for idx in range(2)
    ]

    aggregator.synchronise(
        symbol="BTCUSD",
        venue="CSV",
        instrument_type=InstrumentType.SPOT,
        historical=ticks,
    )

    metadata = platform.metadata_for(layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1s")
    assert metadata is not None
    assert metadata.rows == 2


@pytest.mark.asyncio
async def test_platform_start_stop_streaming_delegates() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(cache_service)
    platform = _build_platform(
        cache_service=cache_service,
        streaming_pipeline=pipeline,
    )

    await platform.start_streaming()
    await platform.stop_streaming()

    assert pipeline.started == 1
    assert pipeline.stopped == 1


@pytest.mark.asyncio
async def test_platform_streaming_session_manages_lifecycle() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(cache_service)
    platform = _build_platform(
        cache_service=cache_service,
        streaming_pipeline=pipeline,
    )

    async with platform.streaming_session() as session:
        assert session is platform
        assert pipeline.started == 1
        assert pipeline.stopped == 0

    assert pipeline.started == 1
    assert pipeline.stopped == 1


@pytest.mark.asyncio
async def test_platform_streaming_session_without_pipeline_is_noop() -> None:
    platform = _build_platform()

    async with platform.streaming_session() as session:
        assert session is platform
        assert platform.streaming_pipeline is None


@pytest.mark.asyncio
async def test_platform_async_context_manager_alias() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(cache_service)
    platform = _build_platform(
        cache_service=cache_service,
        streaming_pipeline=pipeline,
    )

    async with platform as session:
        assert session is platform
        assert pipeline.started == 1
        assert pipeline.stopped == 0

    assert pipeline.started == 1
    assert pipeline.stopped == 1


def test_platform_kill_switch_round_trip() -> None:
    platform = _build_platform()

    engaged = platform.engage_kill_switch("integration-test")
    assert engaged.engaged is True
    assert engaged.reason == "integration-test"

    reset = platform.reset_kill_switch()
    assert reset.engaged is False

    current = platform.kill_switch_state()
    assert isinstance(current.reason, str)


def test_build_geosync_platform_rejects_system_and_config() -> None:
    config = GeoSyncSystemConfig(venues=_venues())
    system = GeoSyncSystem(config)

    with pytest.raises(ValueError):
        build_geosync_platform(
            system=system,
            system_config=config,
            audit_secret="integration-platform-secret",
        )


def test_build_geosync_platform_accepts_existing_system() -> None:
    config = GeoSyncSystemConfig(venues=_venues())
    system = GeoSyncSystem(config)

    platform = build_geosync_platform(
        system=system,
        audit_secret="integration-platform-secret",
    )

    assert platform.system is system


def test_build_geosync_platform_uses_explicit_system_config(tmp_path: Path) -> None:
    allowed_root = tmp_path
    config = GeoSyncSystemConfig(
        venues=_venues(),
        allowed_data_roots=[allowed_root],
        max_csv_bytes=1234,
    )

    platform = build_geosync_platform(
        system_config=config,
        audit_secret="integration-platform-secret",
    )

    assert platform.system.connector_names == ("sim",)
    path_guard = platform.system.data_ingestor._path_guard  # noqa: SLF001 - test introspection
    assert path_guard.allowed_roots == (allowed_root.resolve(),)
    assert path_guard.max_bytes == 1234


def test_build_geosync_platform_rejects_conflicting_streaming_dependencies() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(cache_service)
    settings = StreamingPipelineSettings(
        kafka_config=KafkaIngestionConfig(
            topic="ticks",
            bootstrap_servers="localhost:9092",
            group_id="test",
        )
    )

    with pytest.raises(ValueError):
        build_geosync_platform(
            venues=_venues(),
            audit_secret="integration-platform-secret",
            cache_service=cache_service,
            streaming_pipeline=pipeline,
            streaming_settings=settings,
        )


def test_build_geosync_platform_rejects_mismatched_streaming_cache() -> None:
    cache_service = DataIngestionCacheService()
    pipeline = _StubStreamingPipeline(DataIngestionCacheService())

    with pytest.raises(ValueError):
        build_geosync_platform(
            venues=_venues(),
            audit_secret="integration-platform-secret",
            cache_service=cache_service,
            streaming_pipeline=pipeline,
        )


@pytest.mark.asyncio
async def test_build_geosync_platform_streaming_settings_create_pipeline() -> None:
    cache_service = DataIngestionCacheService()
    factory_calls: list[_StubKafkaService] = []

    def factory(
        config: KafkaIngestionConfig,
        *,
        tick_handler,
        lag_handler=None,
        **kwargs,
    ) -> _StubKafkaService:
        service = _StubKafkaService(
            config,
            tick_handler=tick_handler,
            lag_handler=lag_handler,
            **kwargs,
        )
        factory_calls.append(service)
        return service

    settings = StreamingPipelineSettings(
        kafka_config=KafkaIngestionConfig(
            topic="ticks",
            bootstrap_servers="localhost:9092",
            group_id="test",
        ),
        kafka_service_factory=factory,
        kafka_kwargs={"retries": 3},
    )

    platform = build_geosync_platform(
        venues=_venues(),
        audit_secret="integration-platform-secret",
        cache_service=cache_service,
        streaming_settings=settings,
    )

    assert platform.streaming_pipeline is not None
    assert factory_calls
    service = factory_calls[0]
    assert platform.streaming_pipeline.kafka_service is service
    assert service.tick_handler is platform.streaming_pipeline.tick_handler
    assert service.kwargs == {"retries": 3}

    aggregator = platform.create_aggregator(CacheRoute(layer="raw", timeframe="1s"))
    assert aggregator._cache_service is cache_service  # noqa: SLF001 - test introspection

    await platform.start_streaming()
    await platform.stop_streaming()

    assert service.started == 1
    assert service.stopped == 1
