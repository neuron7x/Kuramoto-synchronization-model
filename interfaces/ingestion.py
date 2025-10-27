"""Shared ingestion interfaces for synchronous and asynchronous pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable, Iterable, Optional

from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker


class DataIngestionService(ABC):
    """Contract for synchronous data ingestion components."""

    @abstractmethod
    def historical_csv(
        self,
        path: str,
        on_tick: Callable[[Ticker], None],
        *,
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
        symbol: str = "UNKNOWN",
        venue: str = "CSV",
        instrument_type: InstrumentType = InstrumentType.SPOT,
        market: Optional[str] = None,
    ) -> None:
        """Load historical data from a CSV file and emit ticks via callback."""

    @abstractmethod
    def binance_ws(
        self,
        symbol: str,
        on_tick: Callable[[Ticker], None],
        *,
        interval: str = "1m",
    ) -> object:
        """Start a Binance websocket subscription."""


class AsyncDataIngestionService(ABC):
    """Contract for asynchronous data ingestion components."""

    @abstractmethod
    async def read_csv(
        self,
        path: str,
        *,
        symbol: str = "UNKNOWN",
        venue: str = "CSV",
        instrument_type: InstrumentType = InstrumentType.SPOT,
        market: Optional[str] = None,
        chunk_size: int = 1000,
        delay_ms: int = 0,
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
    ) -> AsyncIterator[Ticker]:
        """Asynchronously stream ticks from a CSV file."""

    @abstractmethod
    async def stream_ticks(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        interval_ms: int = 1000,
        max_ticks: Optional[int] = None,
    ) -> AsyncIterator[Ticker]:
        """Asynchronously stream ticks from a live source."""

    @abstractmethod
    async def batch_process(
        self,
        ticks: AsyncIterator[Ticker],
        callback: Callable[[list[Ticker]], None],
        batch_size: int = 100,
    ) -> int:
        """Process ticks in batches and return the number of processed items."""
