# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for RestIngestor HTTP polling connector.

Uses httpx mock to simulate HTTP responses without network access.
"""

from __future__ import annotations

import httpx
import pytest

from mycelium_fractal_net.connectors.rest_source import RestIngestor


class TestRestIngestor:
    """Tests for RestIngestor connector."""

    def test_initialization(self) -> None:
        """Test RestIngestor initialization with defaults."""
        ingestor = RestIngestor(url="https://api.example.com/data")

        assert ingestor.url == "https://api.example.com/data"
        assert ingestor.poll_interval_seconds == 60.0
        assert ingestor.batch_size == 100
        assert ingestor.max_retries == 3
        assert ingestor.timeout == 30.0
        assert ingestor.headers == {}
        assert ingestor.params == {}

    def test_initialization_with_custom_params(self) -> None:
        """Test RestIngestor with custom configuration."""
        ingestor = RestIngestor(
            url="https://api.example.com/data",
            poll_interval_seconds=30.0,
            batch_size=50,
            max_retries=5,
            timeout=60.0,
            headers={"Authorization": "Bearer token123"},
            params={"limit": "100"},
            source_name="custom_source",
        )

        assert ingestor.poll_interval_seconds == 30.0
        assert ingestor.batch_size == 50
        assert ingestor.source_name == "custom_source"
        assert ingestor.headers["Authorization"] == "Bearer token123"

    def test_source_name_derivation(self) -> None:
        """Test automatic source name derivation from URL."""
        ingestor = RestIngestor(url="https://api.binance.com/v1/ticker")
        assert "binance" in ingestor.source_name.lower()

    @pytest.mark.asyncio
    async def test_connect_initializes_client(self) -> None:
        """Test that connect() initializes HTTP client."""
        ingestor = RestIngestor(url="https://api.example.com/data")
        assert ingestor._client is None

        await ingestor.connect()
        assert ingestor._client is not None
        assert ingestor._running is True

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self) -> None:
        """Test that close() properly cleans up resources."""
        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        await ingestor.close()
        assert ingestor._client is None
        assert ingestor._running is False

    @pytest.mark.asyncio
    async def test_fetch_requires_connect(self) -> None:
        """Test that fetch() raises if connect() not called."""
        ingestor = RestIngestor(url="https://api.example.com/data")

        with pytest.raises(RuntimeError, match="Client not initialized"):
            async for _ in ingestor.fetch():
                pass

    @pytest.mark.asyncio
    async def test_parse_array_response(self, httpx_mock: pytest.fixture) -> None:
        """Test parsing array JSON response."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json=[
                {"id": 1, "value": 100},
                {"id": 2, "value": 200},
            ],
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 2
        assert events[0].payload["id"] == 1
        assert events[1].payload["id"] == 2

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_parse_object_with_data_field(
        self, httpx_mock: pytest.fixture
    ) -> None:
        """Test parsing object response with 'data' array."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json={
                "status": "ok",
                "data": [
                    {"symbol": "BTC", "price": 50000},
                    {"symbol": "ETH", "price": 3000},
                ],
            },
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 2
        assert events[0].payload["symbol"] == "BTC"

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_parse_object_with_results_field(
        self, httpx_mock: pytest.fixture
    ) -> None:
        """Test parsing object response with 'results' array."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json={
                "count": 1,
                "results": [{"name": "test"}],
            },
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 1
        assert events[0].payload["name"] == "test"

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_parse_single_object(self, httpx_mock: pytest.fixture) -> None:
        """Test parsing single object response."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json={"single": "item", "value": 42},
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 1
        assert events[0].payload["single"] == "item"

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_batch_size_limits_events(self, httpx_mock: pytest.fixture) -> None:
        """Test that batch_size limits returned events."""
        # Create response with 10 items
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json=[{"id": i} for i in range(10)],
        )

        ingestor = RestIngestor(
            url="https://api.example.com/data",
            batch_size=3,
        )
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 3

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, httpx_mock: pytest.fixture) -> None:
        """Test retry behavior on 5xx errors."""
        # First two calls fail, third succeeds
        httpx_mock.add_response(
            url="https://api.example.com/data",
            status_code=503,
        )
        httpx_mock.add_response(
            url="https://api.example.com/data",
            status_code=503,
        )
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json=[{"id": 1}],
        )

        ingestor = RestIngestor(
            url="https://api.example.com/data",
            max_retries=3,
        )
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert len(events) == 1

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_client_error_not_retried(self, httpx_mock: pytest.fixture) -> None:
        """Test that 4xx errors are not retried."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            status_code=404,
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        with pytest.raises(httpx.HTTPStatusError):
            await ingestor._fetch_once()

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_timestamp_extraction(self, httpx_mock: pytest.fixture) -> None:
        """Test timestamp extraction from response data."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json=[
                {"id": 1, "timestamp": 1704067200.0},  # 2024-01-01 00:00:00 UTC
                {"id": 2, "time": "2024-01-02T00:00:00Z"},
            ],
        )

        ingestor = RestIngestor(url="https://api.example.com/data")
        await ingestor.connect()

        events = await ingestor._fetch_once()
        assert events[0].timestamp.year == 2024
        assert events[1].timestamp.day == 2

        await ingestor.close()

    @pytest.mark.asyncio
    async def test_stats_property(self) -> None:
        """Test that stats property returns correct counts."""
        ingestor = RestIngestor(url="https://api.example.com/data")

        stats = ingestor.stats
        assert stats["poll_count"] == 0
        assert stats["error_count"] == 0

    @pytest.mark.asyncio
    async def test_context_manager(self, httpx_mock: pytest.fixture) -> None:
        """Test async context manager usage."""
        httpx_mock.add_response(
            url="https://api.example.com/data",
            json=[{"id": 1}],
        )

        async with RestIngestor(url="https://api.example.com/data") as ingestor:
            assert ingestor._client is not None
            events = await ingestor._fetch_once()
            assert len(events) == 1

        assert ingestor._client is None

    @pytest.mark.asyncio
    async def test_query_params_included(self, httpx_mock: pytest.fixture) -> None:
        """Test that query parameters are included in request."""
        httpx_mock.add_response(
            url="https://api.example.com/data?limit=10&offset=0",
            json=[],
        )

        ingestor = RestIngestor(
            url="https://api.example.com/data",
            params={"limit": "10", "offset": "0"},
        )
        await ingestor.connect()

        await ingestor._fetch_once()
        # Request was made successfully with params

        await ingestor.close()
