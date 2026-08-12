# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
from collections import deque
from pathlib import Path
from typing import AsyncIterator, Deque, Iterable

import pytest

from core.data.async_ingestion import AsyncDataIngestor, Ticker, merge_streams
from core.data.models import InstrumentType


@pytest.mark.asyncio
async def test_async_csv_ingestion_handles_malformed_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    csv_path = tmp_path / "ticks.csv"
    rows: Iterable[list[str]] = [
        ["ts", "price", "volume"],
        ["1700000000", "100.0", "1.0"],
        ["not-a-number", "101.0", ""],
        ["1700000001", "102.0", "2.0"],
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    ingestor = AsyncDataIngestor(allowed_roots=[tmp_path])
    caplog.set_level("WARNING")

    ticks: list[Ticker] = []
    async for tick in ingestor.read_csv(
        str(csv_path),
        symbol="BTCUSD",
        venue="fixture",
        instrument_type=InstrumentType.SPOT,
        chunk_size=2,
        delay_ms=1,
    ):
        ticks.append(tick)

    assert [str(tick.price) for tick in ticks] == ["100.0", "102.0"]
    assert any("Skipping malformed row" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_async_csv_ingestion_logs_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("", encoding="utf-8")

    ingestor = AsyncDataIngestor(allowed_roots=[tmp_path])
    caplog.set_level("ERROR")

    with pytest.raises(ValueError):
        async for _ in ingestor.read_csv(str(bad_csv), symbol="ETHUSD"):
            pass

    assert any("CSV ingestion failed" in record.message for record in caplog.records)


async def _finite_stream(symbol: str, values: Iterable[float]) -> AsyncIterator[Ticker]:
    for idx, price in enumerate(values):
        yield Ticker.create(
            symbol=symbol,
            venue="STREAM",
            price=price,
            timestamp=1700000000 + idx,
            volume=1.0,
            instrument_type=InstrumentType.SPOT,
        )


async def _error_stream(symbol: str, values: Deque[float]) -> AsyncIterator[Ticker]:
    while values:
        yield Ticker.create(
            symbol=symbol,
            venue="STREAM",
            price=values.popleft(),
            timestamp=1700000100,
            volume=1.0,
            instrument_type=InstrumentType.SPOT,
        )
    raise RuntimeError("network glitch")


@pytest.mark.asyncio
async def test_merge_streams_continues_after_stream_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")

    primary = _finite_stream("BTCUSD", [100.0, 101.0, 102.0])
    flaky = _error_stream("ETHUSD", deque([1500.0]))

    merged = merge_streams(primary, flaky)
    received: list[Ticker] = []

    async for tick in merged:
        received.append(tick)
        if len(received) >= 4:
            break

    prices = [str(tick.price) for tick in received]
    assert prices.count("1500.0") == 1
    assert any("Async stream terminated with error" in record.message for record in caplog.records)
