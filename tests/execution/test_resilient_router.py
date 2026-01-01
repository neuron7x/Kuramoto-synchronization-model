# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for the resilient execution router abstraction."""

from __future__ import annotations

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import ExecutionConnector, OrderError, TransientOrderError
from execution.resilience.circuit_breaker import (
    AdaptiveThrottler,
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerConfig,
    ExchangeResilienceProfile,
    LeakyBucketRateLimiter,
    TokenBucketRateLimiter,
)
from execution.router import (
    ExecutionRoute,
    ResilientExecutionRouter,
    SlippageModel,
)


class DummyConnector(ExecutionConnector):
    """Deterministic connector used for router tests."""

    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self.failures: list[Exception] = []
        self.submissions: list[Order] = []

    def schedule_failure(self, error: Exception) -> None:
        self.failures.append(error)

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:  # type: ignore[override]
        if self.failures:
            raise self.failures.pop(0)
        placed = super().place_order(order, idempotency_key=idempotency_key)
        self.submissions.append(placed)
        return placed


def _resilience_profile(
    *,
    leaky_capacity: int = 5,
    leak_rate: float = 50.0,
    token_capacity: float = 50.0,
    token_refill: float = 50.0,
) -> ExchangeResilienceProfile:
    return ExchangeResilienceProfile(
        circuit_breaker=CircuitBreaker(CircuitBreakerConfig(failure_threshold=3)),
        token_bucket=TokenBucketRateLimiter(token_capacity, token_refill),
        leaky_bucket=LeakyBucketRateLimiter(leaky_capacity, leak_rate),
        throttler=AdaptiveThrottler(),
        bulkhead=Bulkhead(max_concurrency=5),
        fallbacks=(),
    )


def _order() -> Order:
    return Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        price=10.0,
        order_type=OrderType.LIMIT,
    )


def test_place_order_applies_slippage_and_normalises_state() -> None:
    connector = DummyConnector()
    route = ExecutionRoute(
        name="binance",
        connector=connector,
        resilience=_resilience_profile(),
        slippage_model=SlippageModel(max_slippage_bps=50.0, limit_buffer_bps=25.0),
    )
    router = ResilientExecutionRouter()
    router.register_route("binance", route)

    state = router.place_order("binance", _order(), idempotency_key="abc")

    assert state.status is OrderStatus.OPEN
    assert pytest.approx(connector.submissions[0].price, rel=1e-6) == 10.0 * (
        1 + (0.25 + 0.5) / 100
    )


def test_idempotency_uses_cached_identifier() -> None:
    connector = DummyConnector()
    route = ExecutionRoute(
        name="coinbase",
        connector=connector,
        resilience=_resilience_profile(),
    )
    router = ResilientExecutionRouter()
    router.register_route("coinbase", route)

    first = router.place_order("coinbase", _order(), idempotency_key="id1")
    second = router.place_order("coinbase", _order(), idempotency_key="id1")

    assert first == second
    assert len(connector.submissions) == 1


def test_failover_to_backup_route_on_error() -> None:
    primary = DummyConnector()
    backup = DummyConnector()
    primary.schedule_failure(OrderError("network outage"))

    primary_route = ExecutionRoute(
        name="primary",
        connector=primary,
        resilience=_resilience_profile(),
    )
    backup_route = ExecutionRoute(
        name="backup",
        connector=backup,
        resilience=_resilience_profile(),
    )

    router = ResilientExecutionRouter()
    router.register_route("failover", primary_route, backup=backup_route)

    state = router.place_order("failover", _order(), idempotency_key="f1")

    assert state.status is OrderStatus.OPEN
    assert not primary.submissions
    assert backup.submissions


def test_throttled_route_raises_transient_error() -> None:
    connector = DummyConnector()
    route = ExecutionRoute(
        name="slow",
        connector=connector,
        resilience=_resilience_profile(leaky_capacity=1, leak_rate=0.0),
    )
    router = ResilientExecutionRouter()
    router.register_route("slow", route)

    router.place_order("slow", _order())
    with pytest.raises(TransientOrderError):
        router.place_order("slow", _order())


def test_latency_spike_increases_throttle_factor() -> None:
    throttler = AdaptiveThrottler(
        target_p95_ms=100.0,
        smoothing=1.0,
        min_multiplier=0.5,
        max_multiplier=3.0,
        window_size=20,
    )
    for _ in range(10):
        throttler.record_latency(80.0)
    baseline = throttler.throttle_factor()

    for _ in range(5):
        throttler.record_latency(400.0)

    assert throttler.throttle_factor() > baseline
