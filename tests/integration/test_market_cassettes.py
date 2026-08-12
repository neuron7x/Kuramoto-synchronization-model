# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json
from pathlib import Path

import httpx
import pytest

from core.data.adapters.polygon import PolygonIngestionAdapter
from core.data.catalog import normalize_symbol
from core.data.connectors.market import BaseMarketDataConnector


@pytest.mark.asyncio
async def test_polygon_adapter_replays_recorded_cassette(tmp_path):
    cassette_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / "cassettes" / "polygon_agg.json"
    )
    payload = json.loads(cassette_path.read_text())
    requests: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.startswith("/v2/aggs/ticker/X:BTCUSD")
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(_handler)

    async with httpx.AsyncClient(base_url="https://mock.polygon", transport=transport) as client:
        adapter = PolygonIngestionAdapter(
            api_key="cassette", base_url="https://mock.polygon", client=client
        )
        connector = BaseMarketDataConnector(adapter)
        events = await connector.fetch_snapshot(
            symbol="X:BTCUSD", start="2024-01-01", end="2024-01-02"
        )
        expected_symbol = normalize_symbol("X:BTCUSD")
        assert len(events) == len(payload["results"])
        for event in events:
            assert event.symbol == expected_symbol
            assert event.bid_price == pytest.approx(event.ask_price)
            assert event.last_price == pytest.approx(event.bid_price)
            assert event.volume is not None and event.volume > 0
        assert connector.dead_letter_queue.peek() == []
        await connector.aclose()

    assert len(requests) == 1
    params = requests[0].url.params
    assert params.get("adjusted") == "true"
    assert params.get("sort") == "asc"
