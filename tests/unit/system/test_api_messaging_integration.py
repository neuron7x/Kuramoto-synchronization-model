from __future__ import annotations

import json
from typing import Awaitable, Callable

import pytest

from core.messaging.event_bus import (
    BaseEventBus,
    EventBusBackend,
    EventBusConfig,
    EventEnvelope,
    EventTopic,
)
from src.system.api_messaging_integration import (
    GatewayRequest,
    IntegrationRouteConflictError,
    IntegrationRouteNotFoundError,
    IntegrationRouter,
)


class StubEventBus(BaseEventBus):
    def __init__(self) -> None:
        super().__init__(EventBusConfig(backend=EventBusBackend.KAFKA))
        self.published: list[tuple[EventTopic, EventEnvelope]] = []

    async def publish(self, topic: EventTopic, envelope: EventEnvelope) -> None:  # type: ignore[override]
        self.published.append((topic, envelope))

    async def subscribe(  # type: ignore[override]
        self,
        topic: EventTopic,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        durable_name: str | None = None,
    ) -> None:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_dispatch_publishes_envelope_with_expected_metadata() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus, event_id_factory=lambda: "event-123")

    router.register_route(
        name="submit-order",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
        partition_resolver=lambda request, match: request.payload["symbol"],
    )

    request = GatewayRequest(
        path="/orders",
        method="post",
        payload={"symbol": "BTC-USD", "quantity": 1.0},
        headers={"Content-Type": "application/json"},
    )

    result = await router.dispatch(request)

    assert result.topic is EventTopic.ORDERS
    assert result.envelope.event_id == "event-123"
    assert result.envelope.partition_key == "BTC-USD"
    assert json.loads(result.envelope.payload.decode("utf-8")) == {
        "symbol": "BTC-USD",
        "quantity": 1.0,
    }
    assert bus.published == [(EventTopic.ORDERS, result.envelope)]


def test_route_request_populates_path_params_and_headers() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus, event_id_factory=lambda: "event-456")
    router.register_route(
        name="positions",
        methods={"GET"},
        path_pattern=r"/positions/(?P<venue>[A-Z0-9_-]+)/(?P<symbol>[A-Z0-9_-]+)",
        topic=EventTopic.MARKET_TICKS,
    )

    request = GatewayRequest(
        path="/positions/BINANCE/BTCUSDT",
        method="GET",
        query_params={"limit": "10"},
        headers={"X-Correlation-Id": "corr-789"},
    )

    result = router.route_request(request)

    assert result.path_params == {"venue": "BINANCE", "symbol": "BTCUSDT"}
    assert result.envelope.partition_key == "corr-789"
    assert result.envelope.headers["x-gateway-path"] == "/positions/BINANCE/BTCUSDT"
    assert json.loads(result.envelope.headers["x-gateway-query"]) == {"limit": "10"}


def test_route_registration_conflict_is_rejected() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="orders",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
    )

    with pytest.raises(IntegrationRouteConflictError):
        router.register_route(
            name="orders",
            methods={"POST"},
            path_pattern=r"/orders",
            topic=EventTopic.ORDERS,
        )


def test_missing_route_raises_descriptive_error() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)

    with pytest.raises(IntegrationRouteNotFoundError):
        router.route_request(GatewayRequest(path="/unknown", method="GET"))
