from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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
    IntegrationRouteError,
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


def test_gateway_request_header_lookup_is_case_insensitive() -> None:
    request = GatewayRequest(
        path="/ping",
        method="get",
        headers={"X-Correlation-Id": "header-id"},
        correlation_id="explicit-id",
    )

    assert request.get_header("x-correlation-id") == "header-id"
    assert request.get_header("x-request-id") is None
    assert request.get_header("missing", "fallback") == "fallback"
    assert request.resolved_correlation_id == "explicit-id"


def test_default_partition_resolver_uses_symbol_path_parameter() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="symbol-stream",
        methods={"get"},
        path_pattern=r"/stream/(?P<symbol>[A-Z0-9_-]+)",
        topic=EventTopic.MARKET_TICKS,
    )

    result = router.route_request(GatewayRequest(path="/stream/ETHUSD", method="GET"))

    assert result.envelope.partition_key == "ETHUSD"
    assert json.loads(result.envelope.headers["x-gateway-path-params"]) == {
        "symbol": "ETHUSD"
    }


def test_default_partition_resolver_falls_back_to_request_path() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="health",
        methods={"GET"},
        path_pattern=r"/health",
        topic=EventTopic.MARKET_TICKS,
    )

    result = router.route_request(GatewayRequest(path="/health", method="GET"))

    assert result.envelope.partition_key == "/health"


def test_event_id_is_propagated_as_correlation_header_when_missing() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus, event_id_factory=lambda: "generated-id")
    router.register_route(
        name="orders",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
    )

    request = GatewayRequest(path="/orders", method="POST", payload={"id": 1})

    result = router.route_request(request)

    assert result.envelope.event_id == "generated-id"
    assert result.envelope.headers["x-correlation-id"] == "generated-id"


def test_route_request_rejects_empty_partition_key() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="orders",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
        partition_resolver=lambda request, match: "",
    )

    with pytest.raises(IntegrationRouteError):
        router.route_request(GatewayRequest(path="/orders", method="POST"))


def test_route_request_rejects_non_bytes_payload() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="orders",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
        payload_encoder=lambda request: "not-bytes",
    )

    with pytest.raises(IntegrationRouteError):
        router.route_request(GatewayRequest(path="/orders", method="POST"))


def test_register_route_requires_http_methods() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)

    with pytest.raises(IntegrationRouteError):
        router.register_route(
            name="invalid",
            methods=[],
            path_pattern=r"/invalid",
            topic=EventTopic.ORDERS,
        )


def test_available_routes_preserves_registration_order() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="first",
        methods={"GET"},
        path_pattern=r"/first",
        topic=EventTopic.MARKET_TICKS,
    )
    router.register_route(
        name="second",
        methods={"POST"},
        path_pattern=r"/second",
        topic=EventTopic.ORDERS,
    )

    routes = router.available_routes()

    assert [route.name for route in routes] == ["first", "second"]
    routes.append(None)  # mutation should not leak into router
    assert [route.name for route in router.available_routes()] == ["first", "second"]


def test_default_payload_encoder_serialises_dataclasses_and_datetimes() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus, event_id_factory=lambda: "event-id")

    @dataclass
    class Payload:
        symbol: str
        created_at: datetime

    router.register_route(
        name="orders",
        methods={"post"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
    )

    payload = Payload(
        symbol="BTC-USD", created_at=datetime(2024, 1, 2, tzinfo=timezone.utc)
    )
    request = GatewayRequest(path="/orders", method="POST", payload=payload)

    result = router.route_request(request)

    decoded = json.loads(result.envelope.payload.decode("utf-8"))
    assert decoded == {
        "symbol": "BTC-USD",
        "created_at": payload.created_at.isoformat(),
    }


def test_register_route_accepts_mapping_of_methods() -> None:
    bus = StubEventBus()
    router = IntegrationRouter(event_bus=bus)
    router.register_route(
        name="orders",
        methods={"post": True, "get": False},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
    )

    result = router.route_request(
        GatewayRequest(path="/orders", method="POST", payload={"foo": "bar"})
    )

    assert result.envelope.partition_key == "/orders"
