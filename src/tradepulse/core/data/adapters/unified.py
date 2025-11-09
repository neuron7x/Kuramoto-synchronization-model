"""Unified ingestion adapters with rate limiting, retries and deduplication.

The production ingestion layer needs to work with heterogeneous market APIs:
REST endpoints for historical and incremental backfills as well as WebSocket
streams for live data.  The primitives in this module provide a small and
testable surface to implement those adapters while satisfying the operational
requirements outlined in the user story:

* **Rate limiting and backoff** – requests are throttled according to the
  exchange rules and reconnect attempts honour an exponential backoff policy.
* **Retry orchestration** – transient failures raise retriable exceptions that
  can be replayed automatically, while respecting the rate limiter budget.
* **Deduplication** – incoming messages are filtered using deterministic keys
  so consumers never see duplicate ticks even when exchanges replay data after
  reconnects.

The classes are deliberately dependency-free to keep them easy to reuse from
both synchronous and asynchronous ingestion pipelines.  A ``sleep`` callback is
accepted by the adapters so unit tests can run without incurring actual delays
and production code can inject either ``time.sleep`` or ``asyncio.sleep``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import (
    Any,
    Callable,
    Deque,
    Iterable,
    Iterator,
    MutableMapping,
    Optional,
    Sequence,
)


class RateLimitExceededError(RuntimeError):
    """Raised when the consumer does not respect the configured rate limit."""


@dataclass(frozen=True)
class RateLimitRule:
    """Token bucket configuration used by :class:`RateLimiter`."""

    max_calls: int
    period_s: float

    def __post_init__(self) -> None:  # pragma: no cover - defensive guards
        if self.max_calls <= 0:
            raise ValueError("max_calls must be strictly positive")
        if self.period_s <= 0:
            raise ValueError("period_s must be strictly positive")


class RateLimiter:
    """Simple token bucket rate limiter returning the required sleep budget."""

    def __init__(self, rule: RateLimitRule) -> None:
        self._rule = rule
        self._tokens = float(rule.max_calls)
        self._updated_at = monotonic()

    def _refill(self, now: float) -> None:
        elapsed = now - self._updated_at
        if elapsed <= 0:
            return
        refill_rate = self._rule.max_calls / self._rule.period_s
        self._tokens = min(self._rule.max_calls, self._tokens + elapsed * refill_rate)
        self._updated_at = now

    def consume(self, weight: float = 1.0) -> float:
        """Reserve ``weight`` tokens and return the required wait time."""

        if weight <= 0:
            raise ValueError("weight must be strictly positive")
        now = monotonic()
        self._refill(now)
        if weight <= self._tokens:
            self._tokens -= weight
            return 0.0
        required = weight - self._tokens
        refill_rate = self._rule.max_calls / self._rule.period_s
        wait_time = required / refill_rate
        self._tokens = 0.0
        self._updated_at = now + wait_time
        return wait_time


@dataclass(frozen=True)
class BackoffPolicy:
    """Exponential backoff configuration."""

    base_delay_s: float = 0.5
    max_delay_s: float = 15.0
    multiplier: float = 2.0
    jitter: float = 0.0

    def delay(self, attempt: int) -> float:
        """Return the delay (in seconds) for the provided retry ``attempt``."""

        if attempt <= 0:
            return 0.0
        delay = self.base_delay_s * (self.multiplier ** (attempt - 1))
        delay = min(delay, self.max_delay_s)
        if self.jitter:
            jitter = (attempt % 7) / 7 * self.jitter
            delay = min(self.max_delay_s, delay + jitter)
        return delay


class Deduplicator:
    """Keep track of recently seen message identifiers."""

    def __init__(self, *, max_items: int = 10_000) -> None:
        self._seen: set[str] = set()
        self._order: Deque[str] = deque(maxlen=max_items)

    @staticmethod
    def _normalise_key(message: Any, key_fields: Sequence[str]) -> str:
        values = []
        for field in key_fields:
            value = message
            for part in field.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = getattr(value, part, None)
            values.append(str(value))
        return "|".join(values)

    def seen(self, message: Any, *, key_fields: Sequence[str]) -> bool:
        """Return ``True`` if the message was already processed."""

        key = self._normalise_key(message, key_fields)
        if key in self._seen:
            return True
        if self._order.maxlen is not None and len(self._order) == self._order.maxlen:
            oldest = self._order.popleft()
            self._seen.discard(oldest)
        self._order.append(key)
        self._seen.add(key)
        return False


class RestIngestionAdapter:
    """Thin wrapper around a callable performing REST requests."""

    def __init__(
        self,
        request_fn: Callable[..., Any],
        *,
        rate_limiter: RateLimiter,
        backoff: BackoffPolicy,
        max_retries: int = 5,
        deduplicator: Optional[Deduplicator] = None,
        key_fields: Sequence[str] = ("timestamp",),
        sleep: Callable[[float], None] | None = None,
        retriable_exceptions: tuple[type[BaseException], ...] = (ConnectionError,),
        context_injector: Callable[[MutableMapping[str, str]], None] | None = None,
    ) -> None:
        self._request_fn = request_fn
        self._rate_limiter = rate_limiter
        self._backoff = backoff
        self._max_retries = max_retries
        self._deduplicator = deduplicator or Deduplicator()
        self._key_fields = key_fields
        self._sleep = sleep or (lambda seconds: None)
        self._retriable_exceptions = retriable_exceptions
        self._context_injector = context_injector

    def _sleep_if_needed(self, seconds: float) -> None:
        if seconds > 0:
            self._sleep(seconds)

    def fetch(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Fetch a payload honouring rate limits, retries and deduplication."""

        attempt = 0
        while True:
            wait_time = self._rate_limiter.consume()
            self._sleep_if_needed(wait_time)
            try:
                if self._context_injector is not None:
                    headers = kwargs.get("headers")
                    header_carrier: MutableMapping[str, str]
                    if headers is None:
                        header_carrier = {}
                    elif isinstance(headers, MutableMapping):
                        header_carrier = headers
                    else:
                        header_carrier = dict(headers)
                    self._context_injector(header_carrier)
                    kwargs["headers"] = header_carrier
                payload = self._request_fn(*args, **kwargs)
            except self._retriable_exceptions:
                attempt += 1
                if attempt > self._max_retries:
                    raise
                delay = self._backoff.delay(attempt)
                self._sleep_if_needed(delay)
                continue

            if payload is None:
                return []
            if isinstance(payload, dict):
                payload = [payload]
            if not isinstance(payload, Iterable):
                raise TypeError("request_fn must return an iterable or mapping")

            result: list[Any] = []
            for message in payload:
                if self._deduplicator.seen(message, key_fields=self._key_fields):
                    continue
                result.append(message)
            return result


class WebSocketIngestionAdapter:
    """Orchestrate WebSocket message consumption with deduplication."""

    def __init__(
        self,
        connect: Callable[[], Iterable[Any]],
        *,
        rate_limiter: Optional[RateLimiter] = None,
        backoff: BackoffPolicy | None = None,
        deduplicator: Optional[Deduplicator] = None,
        key_fields: Sequence[str] = ("timestamp",),
        sleep: Callable[[float], None] | None = None,
        retriable_exceptions: tuple[type[BaseException], ...] = (
            ConnectionError,
            TimeoutError,
        ),
        context_injector: Callable[[MutableMapping[str, str]], None] | None = None,
    ) -> None:
        self._connect = connect
        self._rate_limiter = rate_limiter
        self._backoff = backoff or BackoffPolicy()
        self._deduplicator = deduplicator or Deduplicator()
        self._key_fields = key_fields
        self._sleep = sleep or (lambda seconds: None)
        self._retriable_exceptions = retriable_exceptions
        self._context_injector = context_injector

    def messages(self) -> Iterator[Any]:
        """Yield deduplicated messages, reconnecting with backoff as needed."""

        attempt = 0
        while True:
            try:
                if self._rate_limiter is not None:
                    wait_time = self._rate_limiter.consume()
                    if wait_time > 0:
                        self._sleep(wait_time)
                connect_kwargs: dict[str, MutableMapping[str, str]] = {}
                if self._context_injector is not None:
                    headers: MutableMapping[str, str] = {}
                    self._context_injector(headers)
                    if headers:
                        connect_kwargs["headers"] = headers
                try:
                    stream = self._connect(**connect_kwargs)
                except TypeError:
                    stream = self._connect()
                for message in stream:
                    if self._deduplicator.seen(message, key_fields=self._key_fields):
                        continue
                    attempt = 0
                    yield message
                return
            except self._retriable_exceptions:
                attempt += 1
                delay = self._backoff.delay(attempt)
                self._sleep(delay)
                continue


__all__ = [
    "BackoffPolicy",
    "Deduplicator",
    "RateLimitExceededError",
    "RateLimitRule",
    "RateLimiter",
    "RestIngestionAdapter",
    "WebSocketIngestionAdapter",
]
