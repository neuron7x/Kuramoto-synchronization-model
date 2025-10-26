from __future__ import annotations

import random
from typing import Awaitable, Callable

import pytest

from core.messaging.event_bus import (
    BaseEventBus,
    EventBusBackend,
    EventBusConfig,
    EventEnvelope,
    EventTopic,
)
from src.system.api_messaging_integration import GatewayRequest, IntegrationRouter
from src.system.integration_contracts import (
    ApiBinding,
    AuthorizationPolicy,
    AuthorizationScheme,
    ContractValidationError,
    EventBinding,
    IntegrationContract,
    IntegrationContractRegistry,
)
from src.system.integration_gateway import ModuleIntegrationGateway


class RecordingEventBus(BaseEventBus):
    def __init__(self, *, fail_attempts: int = 0) -> None:
        super().__init__(EventBusConfig(backend=EventBusBackend.KAFKA))
        self.fail_attempts = fail_attempts
        self.published: list[tuple[EventTopic, EventEnvelope]] = []

    async def publish(self, topic: EventTopic, envelope: EventEnvelope) -> None:  # type: ignore[override]
        if self.fail_attempts > 0:
            self.fail_attempts -= 1
            raise RuntimeError("transient failure")
        self.published.append((topic, envelope))

    async def subscribe(  # type: ignore[override]
        self,
        topic: EventTopic,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        durable_name: str | None = None,
    ) -> None:
        raise NotImplementedError


def _build_contract(version: str = "1.0") -> IntegrationContract:
    return IntegrationContract(
        name="submit-order",
        producer="api-gateway",
        consumer="execution",
        version=version,
        api=ApiBinding(
            method="POST",
            path_pattern=r"/orders",
            payload_schema="schemas/orders/submit_v1.json",
        ),
        event=EventBinding(
            topic=EventTopic.ORDERS.metadata.name,
            schema="schemas/events/order_submitted_v1.json",
            version=version,
        ),
        authorization=AuthorizationPolicy(
            scheme=AuthorizationScheme.API_KEY,
            audience="execution",
            allowed_callers={"api-gateway": "super-secret"},
        ),
    )


def _build_router(event_bus: RecordingEventBus) -> IntegrationRouter:
    router = IntegrationRouter(event_bus=event_bus, event_id_factory=lambda: "auto-event")
    router.register_route(
        name="submit-order",
        methods={"POST"},
        path_pattern=r"/orders",
        topic=EventTopic.ORDERS,
        partition_resolver=lambda request, match: request.payload["symbol"],
    )
    return router


def _build_request(idempotency_key: str = "order-123") -> GatewayRequest:
    return GatewayRequest(
        path="/orders",
        method="POST",
        payload={"symbol": "BTC-USD", "quantity": 1.0},
        headers={
            "Content-Type": "application/json",
            "X-Service-Name": "api-gateway",
            "X-Service-Token": "super-secret",
            "X-Idempotency-Key": idempotency_key,
        },
    )


@pytest.mark.asyncio
async def test_dispatch_retries_and_injects_tracing() -> None:
    bus = RecordingEventBus(fail_attempts=1)
    router = _build_router(bus)
    registry = IntegrationContractRegistry()
    registry.register(_build_contract())
    gateway = ModuleIntegrationGateway(router=router, registry=registry, rng=random.Random(42))

    request = _build_request()
    report = await gateway.dispatch("submit-order", request)

    assert report.attempts == 2
    assert report.deduplicated is False
    assert report.traceparent is not None
    assert len(bus.published) == 1
    _, envelope = bus.published[0]
    assert envelope.event_id == "order-123"
    assert envelope.headers["x-idempotency-key"] == "order-123"


@pytest.mark.asyncio
async def test_deduplicated_requests_short_circuit_publish() -> None:
    bus = RecordingEventBus()
    router = _build_router(bus)
    registry = IntegrationContractRegistry()
    contract = _build_contract()
    registry.register(contract)
    gateway = ModuleIntegrationGateway(router=router, registry=registry)

    request = _build_request()
    first = await gateway.dispatch("submit-order", request)
    assert first.deduplicated is False

    second = await gateway.dispatch("submit-order", request)
    assert second.deduplicated is True
    assert second.attempts == 0
    assert len(bus.published) == 1


@pytest.mark.asyncio
async def test_missing_authorisation_is_rejected() -> None:
    bus = RecordingEventBus()
    router = _build_router(bus)
    registry = IntegrationContractRegistry()
    registry.register(_build_contract())
    gateway = ModuleIntegrationGateway(router=router, registry=registry)

    request = GatewayRequest(path="/orders", method="POST", payload={})

    with pytest.raises(ContractValidationError):
        await gateway.dispatch("submit-order", request)


def test_registry_returns_latest_version() -> None:
    registry = IntegrationContractRegistry()
    registry.register(_build_contract("1.0"))
    registry.register(_build_contract("1.1"))

    resolved = registry.get("submit-order")
    assert resolved.version == "1.1"
