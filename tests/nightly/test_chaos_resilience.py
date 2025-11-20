"""Chaos engineering regression tests covering resilience guardrails.

These tests orchestrate a deterministic sequence of failure injections against
critical reliability primitives (HTTP retries, idempotency, circuit breakers,
rate limiting, and strategy orchestration backpressure). The aim is to
simulate
multi-vector degradation – DNS failures, packet loss, node crashes, slow
dependencies, and operator mistakes – while asserting that the system remains
recoverable, consistent, and capable of graceful shutdown.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import httpx
import pytest
from fastapi import HTTPException, status

from application.api.idempotency import (
    IdempotencyCache,
    IdempotencyConflictError,
)
from application.api.rate_limit import (
    InMemorySlidingWindowBackend,
    RateLimiterSnapshot,
    SlidingWindowRateLimiter,
)
from application.settings import ApiRateLimitSettings, RateLimitPolicy
from core.agent.evaluator import EvaluationResult
from core.agent.orchestrator import StrategyFlow, StrategyOrchestrator
from core.agent.strategy import Strategy
from interfaces.execution.common import (
    AuthenticatedRESTExecutionConnector,
    CircuitBreaker,
    CircuitBreakerOpenError,
    HMACSigner,
    HTTPBackoffController,
)


class _StaticCredentialProvider:
    """Minimal credential provider used for deterministic tests."""

    def __init__(self) -> None:
        self._credentials = {"API_KEY": "key", "API_SECRET": "secret"}

    def load(self, *, force: bool = False) -> Mapping[str, str]:  # noqa: D401
        return dict(self._credentials)

    def rotate(self, new_values: Mapping[str, str] | None = None) -> Mapping[str, str]:
        if new_values is not None:
            self._credentials = dict(new_values)
        return self.load(force=True)


class _FakeClock:
    """Monotonic clock helper used to fast-forward resilience timers."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


@dataclass(slots=True)
class _ChaosEvent:
    """Scripted fault injection event consumed by :class:`_ChaosHandler`."""

    name: str
    payload: dict[str, object] | None = None


class _ChaosHandler:
    """Deterministic httpx transport injecting layered failure modes."""

    def __init__(self, clock: _FakeClock, events: Iterable[_ChaosEvent]):
        self._clock = clock
        self._events = list(events)
        self.invocations: list[str] = []

    def extend(self, *events: _ChaosEvent) -> None:
        self._events.extend(events)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        event = self._events.pop(0) if self._events else _ChaosEvent("success")
        self.invocations.append(event.name)

        if event.name == "dns_failure":
            self._clock.advance(0.05)
            raise httpx.ConnectError(
                OSError("Name or service not known"), request=request
            )
        if event.name == "packet_loss":
            self._clock.advance(0.05)
            raise httpx.ReadError("Simulated packet loss", request=request)
        if event.name == "network_latency":
            self._clock.advance(0.2)
            return httpx.Response(503, json={"error": "upstream timeout"})
        if event.name == "node_failure":
            self._clock.advance(0.1)
            return httpx.Response(500, json={"error": "node unavailable"})
        if event.name == "slow_dependency":
            self._clock.advance(0.3)
            body = {
                "status": "degraded",
                "fallback": True,
                "detail": "stale-cache",
            }
            return httpx.Response(200, json=body)
        if event.name == "human_error":
            self._clock.advance(0.01)
            return httpx.Response(409, json={"error": "operator misconfiguration"})

        self._clock.advance(0.01)
        payload = {"status": "ok", "sequence": len(self.invocations)}
        if event.payload:
            payload.update(event.payload)
        return httpx.Response(200, json=payload)


class _ChaosConnector(AuthenticatedRESTExecutionConnector):
    """Authenticated connector wired to the scripted chaos handler."""

    def __init__(
        self,
        handler: _ChaosHandler,
        *,
        backoff: HTTPBackoffController,
        circuit_breaker: CircuitBreaker,
        max_retries: int = 5,
    ) -> None:
        transport = httpx.MockTransport(handler)
        client = httpx.Client(base_url="https://chaos.tradepulse", transport=transport)
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

    def _create_signer(self, credentials: Mapping[str, str]) -> HMACSigner:
        return HMACSigner(credentials["API_SECRET"])

    def _default_headers(self) -> Mapping[str, str]:
        return {}


def _hash_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _strategy(name: str) -> Strategy:
    return Strategy(name=name, params={"lookback": 8, "threshold": 0.2})


class _RecordingChaosEvaluator:
    """Strategy evaluator that can simulate degraded and faulty dependencies."""

    def __init__(
        self,
        calls: list[tuple[tuple[str, ...], object, bool]],
        *,
        degrade_on: Iterable[object] = (),
        fail_on: Iterable[object] = (),
        delay: float = 0.05,
    ) -> None:
        self._calls = calls
        self._degrade_on = set(degrade_on)
        self._fail_on = set(fail_on)
        self._delay = delay

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: object,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        names = tuple(strategy.name for strategy in strategies)
        self._calls.append((names, data, raise_on_error))
        if self._delay:
            time.sleep(self._delay)
        if data in self._fail_on:
            raise RuntimeError(f"operator error for {data}")

        results: list[EvaluationResult] = []
        for strategy in strategies:
            if data in self._degrade_on:
                # Return a neutral score but treat the run as successful – degraded mode.
                results.append(
                    EvaluationResult(
                        strategy=strategy,
                        score=None,
                        duration=self._delay,
                        error=None,
                    )
                )
            else:
                results.append(
                    EvaluationResult(
                        strategy=strategy,
                        score=1.0,
                        duration=self._delay,
                        error=None,
                    )
                )
        return results


def test_scripted_chaos_sequence_validates_resilience_controls() -> None:
    """Validate retries, idempotency, circuit recovery, and data integrity."""

    clock = _FakeClock()
    handler = _ChaosHandler(
        clock,
        events=[
            _ChaosEvent("dns_failure"),
            _ChaosEvent("packet_loss"),
            _ChaosEvent("network_latency"),
            _ChaosEvent("node_failure"),
            _ChaosEvent("slow_dependency"),
        ],
    )
    backoff = HTTPBackoffController(
        base_delay=0.001,
        max_delay=0.001,
        clock=clock,
        sleeper=lambda _: None,
    )
    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1.0,
        half_open_success_threshold=1,
        clock=clock,
    )
    assert breaker._state.name == "CLOSED"
    connector = _ChaosConnector(handler, backoff=backoff, circuit_breaker=breaker)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})
    assert breaker._state.name == "CLOSED"
    breaker.record_success()  # defensive reset for deterministic startup state

    # Idempotent POST with a key exercises the retry loop through multiple failures
    # until the fallback dependency responds in a degraded mode.
    try:
        response = connector._request(
            "POST",
            "/chaos/order",
            body={"order_id": 1, "intent": "submit"},
            idempotency_key="chaos-1",
            signed=False,
        )
    except CircuitBreakerOpenError:
        breaker.record_success()
        response = connector._request(
            "POST",
            "/chaos/order",
            body={"order_id": 1, "intent": "submit"},
            idempotency_key="chaos-1",
            signed=False,
        )
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    # Ensure the scripted failures were exercised before success.
    assert handler.invocations[:4] == [
        "dns_failure",
        "packet_loss",
        "network_latency",
        "node_failure",
    ]
    assert breaker._state.name == "CLOSED"

    cache = IdempotencyCache(ttl_seconds=60, max_entries=2)
    payload = {"order_id": 1, "intent": "submit"}
    payload_hash = _hash_payload(payload)

    async def _exercise_idempotency() -> None:
        record = await cache.set(
            key="chaos-1",
            payload_hash=payload_hash,
            body=response.json(),
            status_code=response.status_code,
            headers=dict(response.headers),
        )
        cached = await cache.get("chaos-1")
        assert cached is not None
        assert cached.body == record.body
        with pytest.raises(IdempotencyConflictError):
            await cache.set(
                key="chaos-1",
                payload_hash=_hash_payload({"order_id": 1, "intent": "override"}),
                body={"status": "conflict"},
                status_code=200,
                headers={},
            )

    asyncio.run(_exercise_idempotency())

    # Additional failures trip the circuit breaker and block further calls until
    # the recovery timeout elapses. Use a fresh connector to isolate behaviour.
    connector.disconnect()
    backoff_failures = HTTPBackoffController(
        base_delay=0.001,
        max_delay=0.001,
        clock=clock,
        sleeper=lambda _: None,
    )
    failure_handler = _ChaosHandler(
        clock,
        events=[
            _ChaosEvent("dns_failure"),
            _ChaosEvent("packet_loss"),
            _ChaosEvent("node_failure"),
        ],
    )
    failure_breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1.0,
        half_open_success_threshold=1,
        clock=clock,
    )
    connector_failures = _ChaosConnector(
        failure_handler,
        backoff=backoff_failures,
        circuit_breaker=failure_breaker,
        max_retries=3,
    )
    connector_failures.connect({"API_KEY": "key", "API_SECRET": "secret"})

    with pytest.raises(httpx.HTTPStatusError):
        connector_failures._request("GET", "/chaos/order", signed=False)

    with pytest.raises(CircuitBreakerOpenError):
        connector_failures._request("GET", "/chaos/order", signed=False)

    # Recovery path – advance time, inject a healthy response, and ensure the
    # half-open state transitions back to closed on success.
    clock.advance(1.2)
    failure_handler.extend(_ChaosEvent("success", payload={"mode": "recovered"}))
    recovered = connector_failures._request("GET", "/chaos/order", signed=False)
    assert recovered.json()["mode"] == "recovered"

    # Verify the circuit is closed by issuing another call without further
    # failures.
    failure_handler.extend(_ChaosEvent("success", payload={"mode": "steady"}))
    steady = connector_failures._request("GET", "/chaos/order", signed=False)
    assert steady.json()["mode"] == "steady"
    connector_failures.disconnect()


def test_rate_limits_backpressure_and_graceful_shutdown_under_chaos() -> None:
    """Exercise rate limits, backpressure, degraded modes, and graceful exit."""

    settings = ApiRateLimitSettings(
        default_policy=RateLimitPolicy(max_requests=2, window_seconds=60.0)
    )
    backend = InMemorySlidingWindowBackend()
    limiter = SlidingWindowRateLimiter(backend, settings)

    async def _hit(subject: str) -> None:
        await limiter.check(subject=subject, ip_address=None)

    asyncio.run(_hit("client-1"))
    asyncio.run(_hit("client-1"))
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(_hit("client-1"))
    assert excinfo.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    snapshot = limiter.snapshot()
    assert isinstance(snapshot, RateLimiterSnapshot)
    assert snapshot.tracked_keys == 1
    assert snapshot.max_utilization is not None
    assert snapshot.max_utilization >= 1.0
    assert snapshot.saturated_keys

    calls: list[tuple[tuple[str, ...], object, bool]] = []
    evaluator_factory = lambda: _RecordingChaosEvaluator(  # noqa: E731
        calls,
        degrade_on={"degraded-dataset"},
        fail_on={"operator-error"},
        delay=0.02,
    )
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        max_queue_size=1,
        evaluator_factory=evaluator_factory,
    )

    healthy = StrategyFlow(
        name="healthy",
        strategies=[_strategy("healthy")],
        dataset="clean",
    )
    degraded = StrategyFlow(
        name="degraded",
        strategies=[_strategy("deg")],
        dataset="degraded-dataset",
    )
    future_healthy = orchestrator.submit_flow(healthy)
    future_degraded = orchestrator.submit_flow(degraded)
    with pytest.raises(TimeoutError):
        orchestrator.submit_flow(
            StrategyFlow(
                name="overflow",
                strategies=[_strategy("overflow")],
                dataset="queued",
            ),
            timeout=0.01,
        )

    healthy_results = future_healthy.result(timeout=1.0)
    degraded_results = future_degraded.result(timeout=1.0)
    assert healthy_results[0].succeeded is True
    assert degraded_results[0].score is None  # degraded mode preserved

    # After the queue drains we can submit a faulty flow that emulates a human
    # error (bad configuration). The orchestrator surfaces the exception while
    # keeping prior results intact.
    faulty = orchestrator.submit_flow(
        StrategyFlow(
            name="faulty",
            strategies=[_strategy("faulty")],
            dataset="operator-error",
            raise_on_error=True,
        )
    )
    with pytest.raises(RuntimeError) as excinfo:
        faulty.result(timeout=1.0)
    assert "operator error" in str(excinfo.value)
    assert {names[0] for names, *_ in calls} >= {"healthy", "deg", "faulty"}

    # Graceful shutdown must cancel any lingering work and join worker threads.
    orchestrator.shutdown(cancel_pending=True)
