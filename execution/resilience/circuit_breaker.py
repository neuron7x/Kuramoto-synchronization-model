"""Resilience primitives for exchange connectors.

This module provides Hystrix-style resilience patterns adapted for TradePulse's
execution layer. It combines circuit breakers, adaptive rate limiting, bulkhead
isolation, and fallback strategies in a cohesive toolkit. The implementation is
thread-safe and intentionally lightweight so it can be used from synchronous or
asynchronous contexts (with thread offloading for blocking work).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Protocol, Tuple


class CircuitBreakerState(str, Enum):
    """Enumerates the supported circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration knobs for the circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    rolling_window: int = 50
    breaches_threshold: int = 5
    breaches_window_seconds: float = 300.0


class CircuitBreaker:
    """Implements a basic failure-count based circuit breaker."""

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self._config = config
        self._state = CircuitBreakerState.CLOSED
        self._lock = threading.RLock()
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._recent_outcomes: Deque[bool] = deque(maxlen=config.rolling_window)
        self._half_open_calls = 0
        self._risk_breaches: Deque[Tuple[float, str]] = deque()
        self._last_trip_reason: Optional[str] = None

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if self._state is CircuitBreakerState.OPEN:
                if now - self._last_failure_time >= self._config.recovery_timeout:
                    self._transition_to_half_open()
                else:
                    return False

            if (
                self._state is CircuitBreakerState.HALF_OPEN
                and self._half_open_calls >= self._config.half_open_max_calls
            ):
                return False

            if self._state is CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1
            return True

    def record_success(self) -> None:
        with self._lock:
            self._recent_outcomes.append(True)
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._transition_to_closed()
            else:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._recent_outcomes.append(False)
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state is CircuitBreakerState.HALF_OPEN:
                self._transition_to_open()
            elif self._consecutive_failures >= self._config.failure_threshold:
                self._transition_to_open()

    def failure_rate(self) -> float:
        with self._lock:
            if not self._recent_outcomes:
                return 0.0
            failures = sum(1 for outcome in self._recent_outcomes if not outcome)
            return failures / len(self._recent_outcomes)

    def _transition_to_open(self) -> None:
        self._state = CircuitBreakerState.OPEN
        self._consecutive_failures = 0
        self._half_open_calls = 0

    def _transition_to_half_open(self) -> None:
        self._state = CircuitBreakerState.HALF_OPEN
        self._half_open_calls = 0

    def _transition_to_closed(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._half_open_calls = 0

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state.

        This method is intended for administrative purposes such as manual
        intervention or testing. It should not be called automatically in
        response to failures.
        """
        with self._lock:
            self._transition_to_closed()

    def record_risk_breach(self, reason: str) -> None:
        """Record a risk compliance breach."""
        with self._lock:
            now = time.monotonic()
            self._risk_breaches.append((now, reason))
            self._last_trip_reason = reason
            self._clean_old_breaches(now)

    def _clean_old_breaches(self, now: float) -> None:
        """Remove breaches outside the rolling window."""
        window = getattr(self._config, "breaches_window_seconds", 300)
        while self._risk_breaches and now - self._risk_breaches[0][0] > window:
            self._risk_breaches.popleft()

    def can_execute(self) -> bool:
        """Check if execution is allowed based on circuit breaker state."""
        with self._lock:
            if self._state is CircuitBreakerState.OPEN:
                now = time.monotonic()
                if now - self._last_failure_time >= self._config.recovery_timeout:
                    self._transition_to_half_open()
                    return True
                return False
            return self._state in (
                CircuitBreakerState.CLOSED,
                CircuitBreakerState.HALF_OPEN,
            )

    def get_last_trip_reason(self) -> Optional[str]:
        """Get the reason for the last trip."""
        with self._lock:
            return self._last_trip_reason

    def get_time_until_recovery(self) -> float:
        """Get time in seconds until recovery if breaker is open."""
        with self._lock:
            if self._state is not CircuitBreakerState.OPEN:
                return 0.0
            elapsed = time.monotonic() - self._last_failure_time
            remaining = max(0.0, self._config.recovery_timeout - elapsed)
            return remaining


class RateLimiter(Protocol):
    """Protocol for rate limiter implementations.

    Rate limiters control the rate of operations by consuming tokens.
    Implementations should be thread-safe.
    """

    def allow(self, tokens: float = 1.0) -> bool:
        """Check if the specified number of tokens can be consumed.

        Args:
            tokens: Number of tokens to consume (default 1.0).

        Returns:
            bool: True if tokens were consumed successfully, False if rate limit exceeded.
        """
        ...

    def get_utilization(self) -> float:
        """Get current utilization as a fraction of capacity.

        Returns:
            float: Utilization in range [0.0, 1.0] where 1.0 means fully utilized.
        """
        ...


@dataclass(slots=True)
class TokenBucketRateLimiter:
    """Token bucket rate limiter for burst handling."""

    capacity: float
    refill_rate_per_sec: float
    _tokens: float = field(init=False)
    _last_refill_ts: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = self.capacity

    def allow(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill_ts
        if elapsed <= 0:
            return
        refill_amount = elapsed * self.refill_rate_per_sec
        self._tokens = min(self.capacity, self._tokens + refill_amount)
        self._last_refill_ts = now

    def get_utilization(self) -> float:
        with self._lock:
            return 1.0 - (self._tokens / self.capacity if self.capacity else 1.0)


@dataclass(slots=True)
class LeakyBucketRateLimiter:
    """Leaky bucket rate limiter for steady rate enforcement."""

    capacity: int
    leak_rate_per_sec: float
    _queue: Deque[float] = field(default_factory=deque, init=False)
    _last_leak_ts: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def allow(self, tokens: float = 1.0) -> bool:
        if tokens != 1.0:
            raise ValueError("Leaky bucket limiter only supports unit tokens")

        with self._lock:
            self._leak()
            if len(self._queue) < self.capacity:
                self._queue.append(time.monotonic())
                return True
            return False

    def _leak(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_leak_ts
        leaks = int(elapsed * self.leak_rate_per_sec)
        for _ in range(min(leaks, len(self._queue))):
            self._queue.popleft()
        if leaks > 0:
            self._last_leak_ts = now

    def get_utilization(self) -> float:
        with self._lock:
            return len(self._queue) / self.capacity if self.capacity else 1.0


@dataclass(slots=True)
class AdaptiveThrottler:
    """Adapts rate limiter pressure based on response times."""

    target_p95_ms: float = 250.0
    smoothing: float = 0.2
    min_multiplier: float = 0.5
    max_multiplier: float = 2.5
    window_size: int = 100
    _recent_latencies: Deque[float] = field(default_factory=deque, init=False)
    _multiplier: float = field(default=1.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def record_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._recent_latencies.append(latency_ms)
            if len(self._recent_latencies) > self.window_size:
                self._recent_latencies.popleft()
            self._recalculate_multiplier()

    def throttle_factor(self) -> float:
        with self._lock:
            return self._multiplier

    def _recalculate_multiplier(self) -> None:
        if not self._recent_latencies:
            return

        latencies = sorted(self._recent_latencies)
        index = max(int(math.ceil(0.95 * len(latencies))) - 1, 0)
        p95 = latencies[index]
        baseline = self.target_p95_ms or 1.0
        ratio = p95 / baseline
        desired_multiplier = max(self.min_multiplier, min(self.max_multiplier, ratio))
        self._multiplier = (self.smoothing * desired_multiplier) + (
            (1 - self.smoothing) * self._multiplier
        )


class FallbackStrategy(Protocol):
    """Protocol for fallback implementations.

    Fallback strategies provide alternative behavior when primary operations fail.
    Implementations should gracefully handle errors and return valid responses or raise
    appropriate exceptions.
    """

    def can_handle(self, exchange: str, operation: str) -> bool:
        """Check if this fallback can handle the specified exchange and operation.

        Args:
            exchange: Name of the exchange (e.g., 'binance', 'coinbase').
            operation: Type of operation (e.g., 'fetch_balance', 'place_order').

        Returns:
            bool: True if this fallback can handle the request.
        """
        ...

    def execute(self, exchange: str, operation: str, *args, **kwargs):
        """Execute the fallback logic.

        Args:
            exchange: Name of the exchange.
            operation: Type of operation.
            *args: Positional arguments passed to the fallback.
            **kwargs: Keyword arguments passed to the fallback.

        Returns:
            Result of the fallback operation.

        Raises:
            RuntimeError: If fallback cannot provide a valid response.
        """
        ...


@dataclass(slots=True)
class CachedDataFallback:
    """Serves cached data when primary execution fails."""

    cache_provider: Callable[[str, str], Optional[object]]

    def can_handle(self, exchange: str, operation: str) -> bool:
        return True

    def execute(self, exchange: str, operation: str, *args, **kwargs):
        data = self.cache_provider(exchange, operation)
        if data is None:
            raise RuntimeError("No cached data available for fallback")
        return data


@dataclass(slots=True)
class DegradedModeFallback:
    """Returns a degraded mode response when no cache exists."""

    message_factory: Callable[[str, str], object]

    def can_handle(self, exchange: str, operation: str) -> bool:
        return True

    def execute(self, exchange: str, operation: str, *args, **kwargs):
        return self.message_factory(exchange, operation)


@dataclass
class HealthMetrics:
    """Aggregated health metrics for a connector."""

    total_requests: int = 0
    rejected_requests: int = 0
    failures: int = 0
    successful_requests: int = 0
    average_latency_ms: float = 0.0
    last_error: Optional[str] = None

    def snapshot(self) -> Dict[str, object]:
        return {
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "failures": self.failures,
            "successful_requests": self.successful_requests,
            "average_latency_ms": self.average_latency_ms,
            "last_error": self.last_error,
        }


@dataclass
class Bulkhead:
    """Bulkhead isolation using semaphores."""

    max_concurrency: int
    _semaphore: threading.Semaphore = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _in_use: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._semaphore = threading.Semaphore(self.max_concurrency)

    def acquire(self, timeout: Optional[float] = None) -> bool:
        acquired = self._semaphore.acquire(timeout=timeout)
        if acquired:
            with self._lock:
                self._in_use += 1
        return acquired

    def release(self) -> None:
        with self._lock:
            if self._in_use > 0:
                self._in_use -= 1
        self._semaphore.release()

    def utilization(self) -> float:
        with self._lock:
            if self.max_concurrency <= 0:
                return 1.0
            return min(1.0, self._in_use / self.max_concurrency)


@dataclass
class ExchangeResilienceProfile:
    """Aggregates resilience mechanisms for a single exchange."""

    circuit_breaker: CircuitBreaker
    token_bucket: TokenBucketRateLimiter
    leaky_bucket: LeakyBucketRateLimiter
    throttler: AdaptiveThrottler
    bulkhead: Bulkhead
    fallbacks: Tuple[FallbackStrategy, ...]
    health: HealthMetrics = field(default_factory=HealthMetrics)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def allow_request(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self.health.total_requests += 1

        if not self.circuit_breaker.allow_request():
            self._register_rejection("circuit_open")
            return False

        if not self.leaky_bucket.allow():
            self._register_rejection("leaky_bucket")
            return False

        if not self.bulkhead.acquire(timeout=0):
            self._register_rejection("bulkhead")
            return False

        throttle_factor = self.throttler.throttle_factor()
        token_cost = tokens * throttle_factor
        if not self.token_bucket.allow(token_cost):
            self.bulkhead.release()
            self._register_rejection("token_bucket")
            return False

        return True

    def release(
        self, success: bool, latency_ms: float, error: Optional[Exception] = None
    ) -> None:
        self.bulkhead.release()
        if success:
            self.circuit_breaker.record_success()
            self.throttler.record_latency(latency_ms)
            with self._lock:
                self.health.successful_requests += 1
                self._update_latency(latency_ms)
        else:
            self.circuit_breaker.record_failure()
            with self._lock:
                self.health.failures += 1
                if error is not None:
                    self.health.last_error = str(error)

    def execute_with_fallback(
        self,
        exchange: str,
        operation: str,
        primary: Callable[..., object],
        *args,
        **kwargs,
    ) -> object:
        try:
            return primary(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - intentionally broad for resilience
            with self._lock:
                self.health.failures += 1
                self.health.last_error = str(exc)
            for fallback in self.fallbacks:
                if not fallback.can_handle(exchange, operation):
                    continue
                try:
                    return fallback.execute(exchange, operation, *args, **kwargs)
                except (
                    Exception
                ):  # noqa: BLE001 - fallback errors should not mask original
                    continue
            raise

    def _register_rejection(self, reason: str) -> None:
        with self._lock:
            self.health.rejected_requests += 1
            self.health.last_error = reason

    def _update_latency(self, latency_ms: float) -> None:
        avg = self.health.average_latency_ms
        count = max(self.health.successful_requests, 1)
        self.health.average_latency_ms = avg + ((latency_ms - avg) / count)


class ExchangeResilienceManager:
    """Coordinates resilience features for multiple exchanges."""

    def __init__(self, profiles: Dict[str, ExchangeResilienceProfile]):
        self._profiles = profiles

    def get_profile(self, exchange: str) -> ExchangeResilienceProfile:
        return self._profiles[exchange]

    def health_report(self) -> Dict[str, Dict[str, object]]:
        return {
            exchange: profile.health.snapshot()
            for exchange, profile in self._profiles.items()
        }


def default_resilience_profile(
    *,
    failure_threshold: int = 5,
    recovery_timeout: float = 15.0,
    half_open_max_calls: int = 2,
    token_bucket_capacity: float = 50.0,
    token_bucket_refill_per_sec: float = 25.0,
    leaky_bucket_capacity: int = 40,
    leaky_bucket_leak_rate: float = 40.0,
    bulkhead_concurrency: int = 8,
    cache_provider: Optional[Callable[[str, str], Optional[object]]] = None,
    degraded_factory: Optional[Callable[[str, str], object]] = None,
) -> ExchangeResilienceProfile:
    """Factory helper to create a sensible default profile."""

    circuit_breaker = CircuitBreaker(
        CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )
    )
    token_bucket = TokenBucketRateLimiter(
        token_bucket_capacity, token_bucket_refill_per_sec
    )
    leaky_bucket = LeakyBucketRateLimiter(leaky_bucket_capacity, leaky_bucket_leak_rate)
    throttler = AdaptiveThrottler()
    bulkhead = Bulkhead(bulkhead_concurrency)

    fallbacks: Tuple[FallbackStrategy, ...]
    fallback_list: List[FallbackStrategy] = []
    if cache_provider is not None:
        fallback_list.append(CachedDataFallback(cache_provider))
    if degraded_factory is not None:
        fallback_list.append(DegradedModeFallback(degraded_factory))
    fallbacks = tuple(fallback_list)

    return ExchangeResilienceProfile(
        circuit_breaker=circuit_breaker,
        token_bucket=token_bucket,
        leaky_bucket=leaky_bucket,
        throttler=throttler,
        bulkhead=bulkhead,
        fallbacks=fallbacks,
    )


__all__ = [
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "TokenBucketRateLimiter",
    "LeakyBucketRateLimiter",
    "AdaptiveThrottler",
    "CachedDataFallback",
    "DegradedModeFallback",
    "HealthMetrics",
    "Bulkhead",
    "ExchangeResilienceProfile",
    "ExchangeResilienceManager",
    "default_resilience_profile",
]
