# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CSV ingestion adapter built on the shared ingestion abstractions."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from core.data.adapters.base import IngestionAdapter
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.timeutils import normalize_timestamp
from core.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["CSVIngestionAdapter"]


class CSVIngestionAdapter(IngestionAdapter):
    """Load historical CSV data and expose it as async primitives."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    async def _read_csv(self, path: str | Path) -> list[dict[str, Any]]:
        def _read() -> list[dict[str, Any]]:
            with open(path, "r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError("CSV file must include headers")
                return list(reader)

        return await asyncio.to_thread(_read)

    async def fetch(
        self,
        *,
        path: str | Path,
        symbol: str,
        venue: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
        required_fields: Iterable[str] = ("ts", "price"),
    ) -> list[Ticker]:
        """Return ticks read from the CSV file."""

        rows = await self._run_with_policy(lambda: self._read_csv(path))
        if not rows:
            return []

        missing = set(required_fields) - set(rows[0].keys())
        if missing:
            raise ValueError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )

        ticks: list[Ticker] = []
        for row in rows:
            tick = Ticker.create(
                symbol=symbol,
                venue=venue,
                price=row[price_field],
                volume=row.get(volume_field, 0),
                instrument_type=instrument_type,
                timestamp=normalize_timestamp(float(row[timestamp_field])),
            )
            ticks.append(tick)

        logger.debug("csv_fetch", path=str(path), count=len(ticks))
        return ticks

    async def stream(
        self,
        *,
        path: str | Path,
        symbol: str,
        venue: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
        delay_ms: int = 0,
    ) -> AsyncIterator[Ticker]:
        """Stream ticks sequentially from the CSV file."""

        ticks = await self.fetch(
            path=path,
            symbol=symbol,
            venue=venue,
            instrument_type=instrument_type,
            timestamp_field=timestamp_field,
            price_field=price_field,
            volume_field=volume_field,
        )
        for tick in ticks:
            yield tick
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        return None
