"""Composable TradePulse platform primitives."""

from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BaseOffset

from analytics.signals.pipeline import FeaturePipelineConfig
from application.system import (
    ExchangeAdapterConfig,
    LiveLoopSettings,
    TradePulseSystem,
    TradePulseSystemConfig,
)
from application.system_orchestrator import (
    MarketDataSource,
    StrategyRun,
    TradePulseOrchestrator,
    build_tradepulse_system,
)
from core.data.models import InstrumentType
from execution.risk import RiskLimits
from src.audit.audit_logger import AuditLogger, AuditRecord
from src.data.ingestion_service import CacheEntrySnapshot, DataIngestionCacheService
from src.data.kafka_ingestion import (
    KafkaIngestionConfig,
    KafkaIngestionService,
    LagHandler,
)
from src.data.pipeline import (
    CacheRoute,
    StreamingIngestionPipeline,
    TickRoutingStrategy,
)
from src.data.streaming_aggregator import TickStreamAggregator
from src.risk.risk_manager import KillSwitchState, RiskManagerFacade


@dataclass(slots=True)
class StreamingPipelineSettings:
    """Configuration describing how to instantiate a streaming ingestion pipeline."""

    kafka_config: KafkaIngestionConfig
    routing_strategy: TickRoutingStrategy | None = None
    lag_handler: LagHandler | None = None
    kafka_service_factory: (
        Callable[[KafkaIngestionConfig], KafkaIngestionService]
        | Callable[..., KafkaIngestionService]
        | None
    ) = None
    kafka_kwargs: Mapping[str, Any] | None = None


@dataclass(slots=True)
class TradePulsePlatform:
    """Aggregate TradePulse services into a cohesive runtime."""

    system: TradePulseSystem
    orchestrator: TradePulseOrchestrator
    cache_service: DataIngestionCacheService
    risk_manager: RiskManagerFacade
    audit_logger: AuditLogger
    streaming_pipeline: StreamingIngestionPipeline | None = None

    @property
    def has_streaming(self) -> bool:
        """Return ``True`` when a streaming pipeline has been configured."""

        return self.streaming_pipeline is not None

    async def start_streaming(self) -> None:
        """Start the configured streaming ingestion pipeline if present."""

        if not self.has_streaming:
            return
        await self.streaming_pipeline.start()

    async def stop_streaming(self) -> None:
        """Stop the configured streaming ingestion pipeline if present."""

        if not self.has_streaming:
            return
        await self.streaming_pipeline.stop()

    @asynccontextmanager
    async def streaming_session(self) -> AsyncIterator["TradePulsePlatform"]:
        """Manage the streaming lifecycle within an async context manager.

        When a streaming pipeline is configured, the context manager starts it
        on entry and stops it on exit, mirroring :meth:`start_streaming` and
        :meth:`stop_streaming`. The platform instance itself is yielded so that
        callers can access orchestrator functionality while streaming is
        active.
        """

        if not self.has_streaming:
            yield self
            return

        try:
            await self.start_streaming()
        except Exception:
            with suppress(Exception):
                await self.stop_streaming()
            raise

        try:
            yield self
        finally:
            await self.stop_streaming()

    async def __aenter__(self) -> "TradePulsePlatform":
        """Enable ``async with`` usage that automatically starts streaming."""

        await self.start_streaming()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Stop streaming when exiting an ``async with`` block."""

        await self.stop_streaming()

    def create_aggregator(
        self,
        route: CacheRoute,
        *,
        frequency: str | pd.Timedelta | BaseOffset | None = None,
    ) -> TickStreamAggregator:
        """Create a tick aggregator backed by the shared cache service."""

        if self.streaming_pipeline is not None:
            return self.streaming_pipeline.create_aggregator(route, frequency=frequency)
        return TickStreamAggregator(
            cache_service=self.cache_service,
            layer=route.layer,
            timeframe=route.timeframe,
            market=route.market,
            frequency=frequency or route.timeframe,
        )

    def run_strategy(
        self,
        source: MarketDataSource,
        strategy: Callable[[np.ndarray], np.ndarray],
    ) -> StrategyRun:
        """Execute the canonical ingestion → features → strategy pipeline."""

        return self.orchestrator.run_strategy(source, strategy=strategy)

    def ingest_csv(
        self,
        path: str,
        *,
        symbol: str,
        venue: str,
        timeframe: str,
        instrument_type: InstrumentType | None = None,
        market: str | None = None,
        layer: str = "raw",
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
    ) -> pd.DataFrame:
        """Ingest a CSV file via the shared cache service."""

        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "venue": venue,
            "timeframe": timeframe,
            "market": market,
            "layer": layer,
            "required_fields": required_fields,
            "timestamp_field": timestamp_field,
            "price_field": price_field,
            "volume_field": volume_field,
        }
        if instrument_type is not None:
            kwargs["instrument_type"] = instrument_type
        return self.cache_service.ingest_csv(path, **kwargs)

    def cache_snapshot(self) -> list[CacheEntrySnapshot]:
        """Return metadata about cached datasets."""

        return self.cache_service.cache_snapshot()

    def metadata_for(
        self,
        *,
        layer: str,
        symbol: str,
        venue: str,
        timeframe: str,
        instrument_type: InstrumentType | None = None,
    ) -> CacheEntrySnapshot | None:
        """Return cache metadata for the specified dataset if available."""

        kwargs: dict[str, Any] = {
            "layer": layer,
            "symbol": symbol,
            "venue": venue,
            "timeframe": timeframe,
        }
        if instrument_type is not None:
            kwargs["instrument_type"] = instrument_type
        return self.cache_service.metadata_for(**kwargs)

    def engage_kill_switch(self, reason: str) -> KillSwitchState:
        """Engage the kill-switch via the risk facade."""

        return self.risk_manager.engage_kill_switch(reason)

    def reset_kill_switch(self) -> KillSwitchState:
        """Reset the kill-switch via the risk facade."""

        return self.risk_manager.reset_kill_switch()

    def kill_switch_state(self) -> KillSwitchState:
        """Return the current kill-switch snapshot."""

        return self.risk_manager.kill_switch_state()

    def log_audit_event(
        self,
        *,
        event_type: str,
        actor: str,
        ip_address: str,
        details: Mapping[str, object] | None = None,
    ) -> AuditRecord:
        """Emit a signed audit record using the configured logger."""

        return self.audit_logger.log_event(
            event_type=event_type,
            actor=actor,
            ip_address=ip_address,
            details=details,
        )


def build_tradepulse_platform(
    *,
    system: TradePulseSystem | None = None,
    system_config: TradePulseSystemConfig | None = None,
    venues: Sequence[ExchangeAdapterConfig] | None = None,
    feature_pipeline: FeaturePipelineConfig | None = None,
    risk_limits: RiskLimits | None = None,
    live_settings: LiveLoopSettings | None = None,
    allowed_data_roots: Iterable[str | Path] | None = None,
    max_csv_bytes: int | None = None,
    cache_service: DataIngestionCacheService | None = None,
    streaming_pipeline: StreamingIngestionPipeline | None = None,
    streaming_settings: StreamingPipelineSettings | None = None,
    audit_logger: AuditLogger | None = None,
    audit_secret: str | None = None,
    audit_secret_resolver: Callable[[], str] | None = None,
) -> TradePulsePlatform:
    """Instantiate a :class:`TradePulsePlatform` with sensible defaults."""

    resolved_system = _resolve_tradepulse_system(
        system=system,
        system_config=system_config,
        venues=venues,
        feature_pipeline=feature_pipeline,
        risk_limits=risk_limits,
        live_settings=live_settings,
        allowed_data_roots=allowed_data_roots,
        max_csv_bytes=max_csv_bytes,
    )
    orchestrator = TradePulseOrchestrator(resolved_system)

    resolved_streaming_pipeline, resolved_cache_service = _resolve_streaming_components(
        system=resolved_system,
        cache_service=cache_service,
        streaming_pipeline=streaming_pipeline,
        streaming_settings=streaming_settings,
    )

    resolved_audit_logger = _resolve_audit_logger(
        audit_logger=audit_logger,
        audit_secret=audit_secret,
        audit_secret_resolver=audit_secret_resolver,
    )

    risk_facade = RiskManagerFacade(resolved_system.risk_manager)

    return TradePulsePlatform(
        system=resolved_system,
        orchestrator=orchestrator,
        cache_service=resolved_cache_service,
        risk_manager=risk_facade,
        audit_logger=resolved_audit_logger,
        streaming_pipeline=resolved_streaming_pipeline,
    )


def _resolve_tradepulse_system(
    *,
    system: TradePulseSystem | None,
    system_config: TradePulseSystemConfig | None,
    venues: Sequence[ExchangeAdapterConfig] | None,
    feature_pipeline: FeaturePipelineConfig | None,
    risk_limits: RiskLimits | None,
    live_settings: LiveLoopSettings | None,
    allowed_data_roots: Iterable[str | Path] | None,
    max_csv_bytes: int | None,
) -> TradePulseSystem:
    """Return a fully initialised :class:`TradePulseSystem`."""

    if system is not None and system_config is not None:
        raise ValueError("Provide either system or system_config, not both")
    if system is not None:
        return system
    if system_config is not None:
        return TradePulseSystem(system_config)
    return build_tradepulse_system(
        venues=venues,
        feature_pipeline=feature_pipeline,
        risk_limits=risk_limits,
        live_settings=live_settings,
        allowed_data_roots=allowed_data_roots,
        max_csv_bytes=max_csv_bytes,
    )


def _resolve_streaming_components(
    *,
    system: TradePulseSystem,
    cache_service: DataIngestionCacheService | None,
    streaming_pipeline: StreamingIngestionPipeline | None,
    streaming_settings: StreamingPipelineSettings | None,
) -> tuple[StreamingIngestionPipeline | None, DataIngestionCacheService]:
    """Return coherent streaming and caching components."""

    if streaming_pipeline is not None and streaming_settings is not None:
        raise ValueError(
            "Provide either streaming_pipeline or streaming_settings, not both"
        )

    if streaming_pipeline is not None:
        pipeline_cache = streaming_pipeline.cache_service
        if cache_service is not None and cache_service is not pipeline_cache:
            raise ValueError(
                "cache_service must match the streaming pipeline cache_service"
            )
        return streaming_pipeline, pipeline_cache

    resolved_cache_service = cache_service or DataIngestionCacheService(
        data_ingestor=system.data_ingestor,
    )

    if streaming_settings is None:
        return None, resolved_cache_service

    resolved_pipeline = StreamingIngestionPipeline(
        kafka_config=streaming_settings.kafka_config,
        cache_service=resolved_cache_service,
        routing_strategy=streaming_settings.routing_strategy,
        lag_handler=streaming_settings.lag_handler,
        kafka_service_factory=streaming_settings.kafka_service_factory,
        kafka_kwargs=streaming_settings.kafka_kwargs,
    )
    return resolved_pipeline, resolved_cache_service


def _resolve_audit_logger(
    *,
    audit_logger: AuditLogger | None,
    audit_secret: str | None,
    audit_secret_resolver: Callable[[], str] | None,
) -> AuditLogger:
    """Return an :class:`AuditLogger` honouring explicit dependencies."""

    if audit_logger is not None:
        if audit_secret is not None or audit_secret_resolver is not None:
            raise ValueError(
                "Do not provide audit credentials when supplying an audit_logger"
            )
        return audit_logger

    if audit_secret is None and audit_secret_resolver is None:
        raise ValueError(
            "Provide an audit_logger or audit credentials via audit_secret or audit_secret_resolver"
        )

    if audit_secret is not None and audit_secret_resolver is not None:
        raise ValueError(
            "audit_secret and audit_secret_resolver are mutually exclusive"
        )

    if audit_secret is not None:
        return AuditLogger(secret=audit_secret)

    assert audit_secret_resolver is not None
    return AuditLogger(secret_resolver=audit_secret_resolver)


__all__ = [
    "StreamingPipelineSettings",
    "TradePulsePlatform",
    "build_tradepulse_platform",
]
