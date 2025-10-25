"""Microservice responsible for market data ingestion and feature building."""

from __future__ import annotations

from typing import AsyncIterator

import pandas as pd

from application.microservices.base import Microservice, ServiceState
from application.microservices.contracts import MarketDataSource
from application.system import TradePulseSystem
from core.data.models import InstrumentType, PriceTick


class MarketDataService(Microservice):
    """Encapsulate all market data related operations behind a service boundary."""

    def __init__(self, system: TradePulseSystem) -> None:
        super().__init__(name="market-data")
        self._system = system
        self._last_source: MarketDataSource | None = None

    def start(self) -> None:
        super().start()

    def ingest(self, source: MarketDataSource) -> pd.DataFrame:
        """Load data from *source* and return a normalised OHLCV frame."""

        self._ensure_active()
        try:
            frame = self._system.ingest_csv(
                source.path,
                symbol=source.symbol,
                venue=source.venue,
                instrument_type=source.instrument_type,
                market=source.market,
            )
        except Exception as exc:
            self._mark_error(exc)
            raise
        else:
            self._last_source = source
            self._mark_healthy()
            return frame

    def build_features(self, market_frame: pd.DataFrame) -> pd.DataFrame:
        """Compute the feature frame associated with *market_frame*."""

        self._ensure_active()
        try:
            features = self._system.build_feature_frame(market_frame)
        except Exception as exc:
            self._mark_error(exc)
            raise
        else:
            self._mark_healthy()
            return features

    def stream(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        interval_ms: int = 1000,
        max_ticks: int | None = None,
    ) -> AsyncIterator[PriceTick]:
        """Return an async iterator yielding ticks from a live connector."""

        self._ensure_active()
        return self._system.stream_market_data(
            source,
            symbol,
            instrument_type=instrument_type,
            interval_ms=interval_ms,
            max_ticks=max_ticks,
        )

    async def fetch_snapshot(
        self,
        source: str,
        *,
        symbol: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        **kwargs,
    ) -> list[PriceTick]:
        """Fetch a one-off market snapshot from a configured connector."""

        self._ensure_active()
        try:
            snapshot = await self._system.fetch_market_snapshot(
                source,
                symbol=symbol,
                instrument_type=instrument_type,
                **kwargs,
            )
        except Exception as exc:
            self._mark_error(exc)
            raise
        else:
            self._mark_healthy()
            return snapshot

    def _health_metadata(self) -> dict[str, object] | None:
        if self.state is ServiceState.STOPPED:
            return None
        metadata: dict[str, object] = {}
        if self._last_source is not None:
            metadata["last_symbol"] = self._last_source.symbol
            metadata["last_venue"] = self._last_source.venue
        if self._system.last_ingestion_duration_seconds is not None:
            metadata["last_duration_seconds"] = (
                self._system.last_ingestion_duration_seconds
            )
        if self._system.last_ingestion_error is not None:
            metadata["last_error"] = self._system.last_ingestion_error
        return metadata or None
