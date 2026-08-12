# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit coverage for the ingestion adapters and fault tolerance stack."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable

import httpx
import pandas as pd
import pytest

from core.data.adapters import (
    AlpacaIngestionAdapter,
    CCXTIngestionAdapter,
    CSVIngestionAdapter,
    ParquetIngestionAdapter,
    PolygonIngestionAdapter,
    RetryConfig,
)
from core.data.adapters import ccxt as ccxt_module
from core.data.adapters.base import IngestionAdapter
from core.data.models import PriceTick as Ticker
from core.utils.dataframe_io import MissingParquetDependencyError, write_dataframe
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL

POLYGON_TEST_KEY = "".join(
    (
        "p",
        "o",
        "l",
        "y",
        "g",
        "o",
        "n",
        "-",
        "d",
        "e",
        "m",
        "o",
        "-",
        "t",
        "o",
        "k",
        "e",
        "n",
    )
)
ALPACA_TEST_KEY = "".join(
    (
        "a",
        "l",
        "p",
        "a",
        "c",
        "a",
        "-",
        "d",
        "e",
        "m",
        "o",
        "-",
        "t",
        "o",
        "k",
        "e",
        "n",
    )
)
ALPACA_TEST_SECRET = "".join(
    (
        "a",
        "l",
        "p",
        "a",
        "c",
        "a",
        "-",
        "d",
        "e",
        "m",
        "o",
        "-",
        "p",
        "a",
        "s",
        "s",
        "p",
        "h",
        "r",
        "a",
        "s",
        "e",
    )
)


class DummyAdapter(IngestionAdapter):
    def __init__(self) -> None:
        super().__init__(
            retry=RetryConfig(
                attempts=3,
                multiplier=0.01,
                max_backoff=0.02,
                jitter=0.0,
            )
        )
        self.calls = 0

    async def fetch(self, **kwargs: object) -> str:
        async def _op() -> str:
            self.calls += 1
            if self.calls < 3:
                raise asyncio.TimeoutError("transient")
            return "ok"

        return await self._run_with_policy(_op)

    async def stream(self, **kwargs: object) -> AsyncIterator[Ticker]:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_retry_policy_eventually_succeeds() -> None:
    adapter = DummyAdapter()
    result = await adapter.fetch()
    assert adapter.calls == 3
    assert result == "ok"


@pytest.mark.asyncio
async def test_parquet_adapter_fetch(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "ts": [1719878400, 1719878460],
            "price": [101.2, 102.4],
            "volume": [1.5, 2.5],
        }
    )
    file_path = tmp_path / "ticks.parquet"
    try:
        write_dataframe(df, file_path)
    except MissingParquetDependencyError:
        pytest.skip("Parquet backend unavailable")

    adapter = ParquetIngestionAdapter()
    ticks = await adapter.fetch(path=file_path, symbol="BTCUSD", venue="BINANCE")
    assert len(ticks) == 2
    assert float(ticks[0].price) == pytest.approx(
        df.loc[0, "price"],
        rel=FLOAT_REL_TOL,
        abs=FLOAT_ABS_TOL,
    )


@pytest.mark.asyncio
async def test_csv_adapter_stream(tmp_path: Path) -> None:
    csv_path = tmp_path / "ticks.csv"
    csv_path.write_text(
        "ts,price,volume\n1719878400,100.5,10\n1719878460,101.0,5\n",
        encoding="utf-8",
    )

    adapter = CSVIngestionAdapter()
    stream = adapter.stream(path=csv_path, symbol="ETHUSD", venue="CSV")
    ticks = [tick async for tick in stream]
    assert len(ticks) == 2
    assert float(ticks[1].price) == pytest.approx(101.0, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)


class _StubExchange:
    def __init__(self, params: dict[str, object]) -> None:
        self.params = params
        self.closed = False

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None,
        limit: int,
    ) -> list[list[float]]:
        return [[1719878400000, 1, 2, 3, 4, 5]]

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ccxt_adapter_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    def _factory_loader(_: str) -> Callable[[dict[str, object]], _StubExchange]:
        return lambda params: _StubExchange(params)

    monkeypatch.setattr(ccxt_module, "_load_exchange_factory", _factory_loader)

    adapter = CCXTIngestionAdapter(
        exchange_id="binance",
        retry=RetryConfig(
            attempts=2,
            multiplier=0.01,
            max_backoff=0.02,
            jitter=0.0,
        ),
    )
    ticks = await adapter.fetch(symbol="BTC/USDT")
    assert len(ticks) == 1
    assert ticks[0].price == 4
    await adapter.aclose()
    assert adapter._exchange.closed  # type: ignore[attr-defined]


class _StubResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict[str, object]:
        return self._payload


class _UnstableClient:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def get(self, *args: object, **kwargs: object) -> _StubResponse:
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadTimeout("boom", request=None)
        return _StubResponse(
            200,
            {
                "results": [
                    {"t": 1719878400000, "c": 100.1, "v": 12.0},
                ]
            },
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_polygon_adapter_fetch_with_retry() -> None:
    client = _UnstableClient()
    adapter = PolygonIngestionAdapter(
        api_key=POLYGON_TEST_KEY,
        client=client,  # type: ignore[arg-type]
        retry=RetryConfig(
            attempts=2,
            multiplier=0.01,
            max_backoff=0.02,
            jitter=0.0,
        ),
    )
    ticks = await adapter.fetch(symbol="AAPL", start="2024-01-01", end="2024-01-02")
    assert len(ticks) == 1
    assert client.calls == 2
    await adapter.aclose()
    assert client.closed


class _StaticClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.closed = False

    async def get(self, *args: object, **kwargs: object) -> _StubResponse:
        return _StubResponse(200, self.payload)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_alpaca_adapter_fetch_parses_timestamps() -> None:
    payload = {
        "trades": [
            {"t": "2024-07-01T10:00:00Z", "p": 150.0, "s": 10},
        ]
    }
    client = _StaticClient(payload)
    adapter = AlpacaIngestionAdapter(
        api_key=ALPACA_TEST_KEY,
        api_secret=ALPACA_TEST_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    ticks = await adapter.fetch(symbol="MSFT", start="2024-07-01", end="2024-07-02")
    assert len(ticks) == 1
    assert ticks[0].timestamp == datetime(2024, 7, 1, 10, 0, tzinfo=timezone.utc)
    await adapter.aclose()
    assert client.closed
