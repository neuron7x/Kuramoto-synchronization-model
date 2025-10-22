from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pytest

from application.system import ExchangeAdapterConfig
from application.system_orchestrator import MarketDataSource
from core.data.models import InstrumentType, PriceTick
from execution.connectors import SimulatedExchangeConnector

from src.audit.audit_logger import AuditLogger
from src.data.ingestion_service import DataIngestionCacheService
from src.data.pipeline import CacheRoute
from src.system import TradePulsePlatform, build_tradepulse_platform


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

    def create_aggregator(
        self, route: CacheRoute, *, frequency: str | pd.Timedelta | None = None
    ):
        self.created.append((route, frequency))
        from src.data.streaming_aggregator import TickStreamAggregator

        return TickStreamAggregator(
            cache_service=self.cache_service,
            layer=route.layer,
            timeframe=route.timeframe,
            market=route.market,
            frequency=frequency or route.timeframe,
        )


def _venues() -> tuple[ExchangeAdapterConfig, ...]:
    connector = SimulatedExchangeConnector()
    return (ExchangeAdapterConfig(name="sim", connector=connector),)


def _build_platform(
    *,
    audit_secret: str = "integration-platform-secret",
    cache_service: DataIngestionCacheService | None = None,
    streaming_pipeline: _StubStreamingPipeline | None = None,
    allowed_data_roots: Iterable[str | Path] | None = None,
) -> TradePulsePlatform:
    kwargs: dict[str, object] = {}
    if cache_service is not None:
        kwargs["cache_service"] = cache_service
    if streaming_pipeline is not None:
        kwargs["streaming_pipeline"] = streaming_pipeline
    if allowed_data_roots is not None:
        kwargs["allowed_data_roots"] = allowed_data_roots
    return build_tradepulse_platform(
        venues=_venues(),
        audit_secret=audit_secret,
        **kwargs,
    )


def test_build_tradepulse_platform_requires_audit_credentials() -> None:
    with pytest.raises(ValueError):
        build_tradepulse_platform(venues=_venues())


def test_build_tradepulse_platform_rejects_conflicting_audit_dependencies() -> None:
    with pytest.raises(ValueError):
        build_tradepulse_platform(
            venues=_venues(),
            audit_logger=AuditLogger(secret="explicit"),
            audit_secret="redundant",
        )


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
    metadata = platform.metadata_for(
        layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1s"
    )
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

    metadata = platform.metadata_for(
        layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1min"
    )
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

    metadata = platform.metadata_for(
        layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1s"
    )
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
