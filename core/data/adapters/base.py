"""Base abstractions for resilient data ingestion adapters."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from secrets import SystemRandom
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, TypeVar

from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from core.data.models import PriceTick as Ticker
from core.utils.logging import get_logger

__all__ = [
    "RetryConfig",
    "RateLimitConfig",
    "TimeoutConfig",
    "FaultTolerancePolicy",
    "IngestionAdapter",
]

logger = get_logger(__name__)

T = TypeVar("T")


def _default_retry_exceptions() -> tuple[type[BaseException], ...]:
    """Return the default set of retry-able exceptions."""

    exceptions: tuple[type[BaseException], ...] = (
        asyncio.TimeoutError,
        TimeoutError,
        ConnectionError,
    )

    try:  # Optional dependency - ``httpx`` is only used by HTTP adapters.
        import httpx
    except Exception:  # pragma: no cover - fallback when httpx is unavailable
        httpx_exceptions: tuple[type[BaseException], ...] = tuple()
    else:
        httpx_exceptions = (httpx.HTTPError,)

    try:  # ``ccxt`` may not always be installed in lightweight environments.
        import ccxt  # pragma: no cover - optional import guard
    except Exception:
        ccxt_exceptions: tuple[type[BaseException], ...] = tuple()
    else:
        ccxt_exceptions = (ccxt.BaseError,)

    return exceptions + httpx_exceptions + ccxt_exceptions


@dataclass(frozen=True)
class RetryConfig:
    """Configuration describing retry/backoff behaviour."""

    attempts: int = 5
    multiplier: float = 0.5
    max_backoff: float = 15.0
    jitter: float = 0.1
    exceptions: tuple[type[BaseException], ...] = field(
        default_factory=_default_retry_exceptions
    )
    _rng: SystemRandom = field(default_factory=SystemRandom, init=False, repr=False)

    def compute_backoff(self, attempt_number: int) -> float:
        """Return the exponential backoff for a given retry attempt."""

        base_delay = min(
            self.max_backoff, self.multiplier * (2 ** max(0, attempt_number - 1))
        )
        if self.jitter <= 0:
            return base_delay
        jitter_delta = self._rng.uniform(0, base_delay * self.jitter)
        delay = base_delay + jitter_delta
        return min(self.max_backoff, delay)


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration describing rate limit constraints."""

    rate: int
    period_seconds: float

    def create_limiter(self) -> AsyncLimiter:
        return AsyncLimiter(self.rate, self.period_seconds)


@dataclass(frozen=True)
class TimeoutConfig:
    """Configuration describing timeout handling."""

    total_seconds: float


class FaultTolerancePolicy:
    """Composes retry, rate limit, and timeout protections for IO operations."""

    def __init__(
        self,
        *,
        retry: Optional[RetryConfig] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        timeout: Optional[TimeoutConfig] = None,
    ) -> None:
        self.retry = retry
        self.timeout = timeout
        self._limiter = rate_limit.create_limiter() if rate_limit else None

    async def _apply_timeout(self, operation: Callable[[], Awaitable[T]]) -> T:
        if self.timeout is None:
            return await operation()
        return await asyncio.wait_for(operation(), timeout=self.timeout.total_seconds)

    async def _apply_rate_limit(self, operation: Callable[[], Awaitable[T]]) -> T:
        if self._limiter is None:
            return await self._apply_timeout(operation)

        async with self._limiter:
            return await self._apply_timeout(operation)

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Execute *operation* with the configured protections."""

        if self.retry is None:
            return await self._apply_rate_limit(operation)

        retry = self.retry

        async for attempt in AsyncRetrying(
            wait=wait_random_exponential(
                multiplier=retry.multiplier, max=retry.max_backoff
            ),
            stop=stop_after_attempt(retry.attempts),
            retry=retry_if_exception_type(retry.exceptions),
            reraise=True,
        ):
            with attempt:
                return await self._apply_rate_limit(operation)

        raise RuntimeError(
            "AsyncRetrying did not execute any attempts"
        )  # pragma: no cover - defensive

    async def sleep_for_attempt(self, attempt_number: int) -> None:
        """Sleep using the computed backoff for streaming reconnects."""

        if self.retry is None:
            return
        delay = self.retry.compute_backoff(attempt_number)
        logger.debug("retry_backoff", attempt=attempt_number, delay=delay)
        await asyncio.sleep(delay)


class IngestionAdapter(ABC):
    """Abstract ingestion adapter exposing fetch & stream primitives."""

    def __init__(
        self,
        *,
        retry: Optional[RetryConfig] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        timeout: Optional[TimeoutConfig] = None,
    ) -> None:
        self._policy = FaultTolerancePolicy(
            retry=retry, rate_limit=rate_limit, timeout=timeout
        )

    async def _run_with_policy(self, operation: Callable[[], Awaitable[T]]) -> T:
        return await self._policy.run(operation)

    async def _sleep_backoff(self, attempt_number: int) -> None:
        await self._policy.sleep_for_attempt(attempt_number)

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> Any:
        """Fetch a bounded snapshot from the data source."""

    @abstractmethod
    async def stream(self, **kwargs: Any) -> AsyncIterator[Ticker]:
        """Stream a live feed of ticks from the data source."""

    async def aclose(self) -> None:
        """Release adapter resources."""

    async def __aenter__(self) -> "IngestionAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
