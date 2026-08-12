# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Parquet ingestion adapter with async + fault tolerance support."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Optional

import pandas as pd

from core.data.adapters.base import IngestionAdapter
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.timeutils import normalize_timestamp
from core.utils.dataframe_io import MissingParquetDependencyError, read_dataframe
from core.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["ParquetIngestionAdapter"]


class ParquetIngestionAdapter(IngestionAdapter):
    """Load tick level data from parquet datasets."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    async def _read_parquet(
        self, path: str | Path, columns: Optional[Iterable[str]] = None
    ) -> pd.DataFrame:
        def _load() -> pd.DataFrame:
            frame = read_dataframe(Path(path), allow_json_fallback=False)
            if columns is not None:
                return frame.loc[:, list(columns)]
            return frame

        return await asyncio.to_thread(_load)

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
        columns: Optional[Iterable[str]] = None,
    ) -> list[Ticker]:
        """Return ticks from the parquet dataset as ``Ticker`` objects."""

        try:
            df = await self._run_with_policy(lambda: self._read_parquet(path, columns))
        except MissingParquetDependencyError as exc:
            raise RuntimeError(
                "Parquet ingestion requires either pyarrow or polars. Install the 'geosync[feature_store]' extra."
            ) from exc
        if timestamp_field not in df.columns or price_field not in df.columns:
            missing = {timestamp_field, price_field} - set(df.columns)
            raise ValueError(f"Parquet dataset missing required columns: {missing}")

        ticks: list[Ticker] = []
        for row in df.itertuples(index=False):
            ts_value = getattr(row, timestamp_field)
            price = getattr(row, price_field)
            volume = getattr(row, volume_field, 0) if volume_field in df.columns else 0
            tick = Ticker.create(
                symbol=symbol,
                venue=venue,
                price=price,
                volume=volume,
                instrument_type=instrument_type,
                timestamp=normalize_timestamp(ts_value),
            )
            ticks.append(tick)

        logger.debug("parquet_fetch", path=str(path), count=len(ticks))
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
        batch_delay_ms: int = 0,
    ) -> AsyncIterator[Ticker]:
        """Stream ticks sequentially from the parquet dataset."""

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
            if batch_delay_ms > 0:
                await asyncio.sleep(batch_delay_ms / 1000.0)

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        return None
