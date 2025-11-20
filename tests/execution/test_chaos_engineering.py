from __future__ import annotations

import contextlib
from collections import deque
from dataclasses import dataclass

import httpx
import pytest

from interfaces.execution.common import (
    AuthenticatedRESTExecutionConnector,
    CircuitBreaker,
    CircuitBreakerOpenError,
    HMACSigner,
    HTTPBackoffController,
)
from observability.tracing import chaos_span


@dataclass(slots=True)
class _ChaosEvent:
    name: str
    response: httpx.Response | None = None
    exception: Exception | None = None


class _FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def sleep(self, delta: float) -> None:
        self._now += delta


class _ChaosTransport:
    def __init__(self, events: deque[_ChaosEvent], clock: _FakeClock) -> None:
        self._events = events
        self._clock = clock
        self.invocations: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        event = self._events.popleft() if self._events else _ChaosEvent("success")
        self.invocations.append(event.name)

        if event.exception is not None:
            self._clock.sleep(0.05)
            raise event.exception
        if event.response is not None:
            self._clock.sleep(0.05)
            return event.response

        self._clock.sleep(0.01)
        return httpx.Response(200, json={"status": "ok"})


class _StaticCredentialProvider:
    def load(self, *, force: bool = False) -> dict[str, str]:
        return {"API_KEY": "key", "API_SECRET": "secret"}

    def rotate(self, new_values: dict[str, str] | None = None) -> dict[str, str]:
        if new_values:
            return dict(new_values)
        return self.load(force=True)


class _DeterministicConnector(AuthenticatedRESTExecutionConnector):
    def __init__(
        self,
        transport: _ChaosTransport,
        *,
        backoff: HTTPBackoffController,
        circuit_breaker: CircuitBreaker,
        max_retries: int = 5,
    ) -> None:
        client = httpx.Client(
            base_url="https://chaos.tradepulse",
            transport=httpx.MockTransport(transport),
        )
        super().__init__(
            "chaos",
            sandbox=True,
            base_url="https://chaos.tradepulse",
            http_client=client,
            credential_provider=_StaticCredentialProvider(),
            enable_stream=False,
            backoff=backoff,
            circuit_breaker=circuit_breaker,
            max_retries=max_retries,
        )
        self._transport = transport

    def _create_signer(self, credentials: dict[str, str]) -> HMACSigner:
        return HMACSigner(credentials["API_SECRET"])

    @property
    def invocations(self) -> list[str]:
        return list(self._transport.invocations)


def test_connector_recovers_from_layered_network_chaos(monkeypatch):
    captured = {}

    def fake_pipeline(stage: str, **attrs):
        captured["stage"] = stage
        captured["attrs"] = attrs
        return contextlib.nullcontext(None)

    monkeypatch.setattr("observability.tracing.pipeline_span", fake_pipeline)
    monkeypatch.setattr("interfaces.execution.common.random.uniform", lambda a, b: a)

    clock = _FakeClock()
    events = deque(
        [
            _ChaosEvent(
                "dns_failure",
                exception=httpx.ConnectError(
                    OSError("dns"), request=httpx.Request("GET", "https://chaos")
                ),
            ),
            _ChaosEvent(
                "latency", response=httpx.Response(503, json={"error": "timeout"})
            ),
            _ChaosEvent("success"),
        ]
    )
    transport = _ChaosTransport(events, clock)
    backoff = HTTPBackoffController(
        base_delay=0.05,
        max_delay=0.2,
        clock=clock,
        sleeper=clock.sleep,
    )
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.5, clock=clock)
    connector = _DeterministicConnector(
        transport, backoff=backoff, circuit_breaker=breaker
    )
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})

    with chaos_span("rest-connector", disruption="network-delay"):
        response = connector._request("GET", "/status", idempotency_key="abc-1")

    assert response.status_code == 200
    assert connector.invocations == ["dns_failure", "latency", "success"]
    assert clock() <= 0.25 * 1.05

    assert captured["stage"] == "chaos.rest-connector"
    assert captured["attrs"]["chaos.experiment"] == "rest-connector"
    assert captured["attrs"]["disruption"] == "network-delay"


def test_circuit_breaker_opens_after_repeated_chaos_events(monkeypatch):
    clock = _FakeClock()
    events = deque(
        [
            _ChaosEvent(
                "outage", response=httpx.Response(500, json={"error": "outage"})
            ),
            _ChaosEvent(
                "outage", response=httpx.Response(500, json={"error": "outage"})
            ),
        ]
    )
    transport = _ChaosTransport(events, clock)
    backoff = HTTPBackoffController(
        base_delay=0.05,
        max_delay=0.05,
        clock=clock,
        sleeper=clock.sleep,
    )
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0, clock=clock)
    connector = _DeterministicConnector(
        transport, backoff=backoff, circuit_breaker=breaker, max_retries=1
    )
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})

    with pytest.raises(httpx.HTTPStatusError):
        connector._request("GET", "/order", idempotency_key="chaos")

    with pytest.raises(CircuitBreakerOpenError):
        connector._request("GET", "/order", idempotency_key="chaos-2")

    with chaos_span("rest-connector", disruption="broker-outage"):
        breaker.record_success()

    assert clock() >= 0.05
    breaker.before_call()
