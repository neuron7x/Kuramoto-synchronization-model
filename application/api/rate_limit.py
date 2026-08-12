# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Sliding window rate limiter utilities for GeoSync APIs."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status

from application.settings import ApiRateLimitSettings, RateLimitPolicy

__all__ = [
    "RateLimiterBackend",
    "InMemorySlidingWindowBackend",
    "RedisSlidingWindowBackend",
    "SlidingWindowRateLimiter",
    "RateLimiterSnapshot",
    "build_rate_limiter",
]


@dataclass(slots=True)
class RateLimiterSnapshot:
    """Point-in-time utilisation view of a :class:`SlidingWindowRateLimiter`."""

    backend: str
    tracked_keys: int
    max_utilization: float | None
    saturated_keys: list[str]


class RateLimiterBackend(Protocol):
    """Protocol describing a sliding window limiter backend."""

    async def hit(self, key: str, *, limit: int, window_seconds: float) -> int:
        """Register a hit for *key* and return the number of requests in the window."""


class InMemorySlidingWindowBackend:
    """Simple asyncio-aware sliding window backend for single-instance deployments."""

    def __init__(self) -> None:
        self._records: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def hit(self, key: str, *, limit: int, window_seconds: float) -> int:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        now = loop.time()
        async with self._lock:
            bucket = self._records.setdefault(key, deque())
            threshold = now - window_seconds
            while bucket and bucket[0] <= threshold:
                bucket.popleft()
            bucket.append(now)
            return len(bucket)


class RedisSlidingWindowBackend:
    """Redis based backend suitable for horizontally scaled deployments."""

    def __init__(self, client, *, key_prefix: str = "geosync:rate") -> None:  # type: ignore[no-untyped-def]
        self._client = client
        self._prefix = key_prefix.rstrip(":")

    async def hit(self, key: str, *, limit: int, window_seconds: float) -> int:
        redis_key = f"{self._prefix}:{key}"
        now = time.time()
        window_start = now - window_seconds
        pipeline = self._client.pipeline()
        pipeline.zremrangebyscore(redis_key, 0, window_start)
        pipeline.zadd(redis_key, {str(now): now})
        pipeline.zcard(redis_key)
        pipeline.expire(redis_key, int(window_seconds) + 1)
        _, _, count, _ = await pipeline.execute()
        return int(count)


class SlidingWindowRateLimiter:
    """Coordinator that selects policies and delegates hit tracking."""

    def __init__(
        self,
        backend: RateLimiterBackend,
        settings: ApiRateLimitSettings,
    ) -> None:
        self._backend = backend
        self._settings = settings

    async def check(self, *, subject: str | None, ip_address: str | None) -> None:
        policy, key = self._resolve_policy(subject, ip_address)
        count = await self._backend.hit(
            key, limit=policy.max_requests, window_seconds=policy.window_seconds
        )
        if count > policy.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for this client.",
            )

    def snapshot(self) -> RateLimiterSnapshot:
        """Return utilisation metrics for observability and health checks."""

        backend_name = type(self._backend).__name__
        records = getattr(self._backend, "_records", None)
        tracked_keys = 0
        max_utilization: float | None = None
        saturated: list[str] = []

        if isinstance(records, dict):
            utilisation_values: list[float] = []
            cleanup_thresholds: dict[str, float] = {}
            remove_empty: set[str] = set()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
                current_time = time.monotonic()
            else:
                current_time = loop.time()

            for storage_key, bucket in list(records.items()):
                if not hasattr(bucket, "__len__"):
                    continue
                policy = self._policy_for_storage_key(storage_key)
                if policy.max_requests <= 0:
                    continue
                active_count: int | None = None
                if isinstance(bucket, deque):
                    snapshot_bucket = tuple(bucket)
                    bucket_length = len(snapshot_bucket)
                    if policy.window_seconds > 0 and bucket_length:
                        threshold = current_time - policy.window_seconds
                        expired = 0
                        for timestamp in snapshot_bucket:
                            if timestamp <= threshold:
                                expired += 1
                            else:
                                break
                        if expired:
                            cleanup_thresholds[storage_key] = threshold
                        active_count = bucket_length - expired
                        if active_count == 0 and bucket_length:
                            remove_empty.add(storage_key)
                    else:
                        active_count = bucket_length
                else:
                    active_count = len(bucket)

                if not active_count:
                    continue

                tracked_keys += 1
                utilisation = active_count / float(policy.max_requests)
                utilisation_values.append(utilisation)
                if utilisation >= 1.0:
                    saturated.append(storage_key)

            if utilisation_values:
                max_utilization = max(utilisation_values)

            if cleanup_thresholds or remove_empty:
                cleanup_coro = self._prune_snapshot_buckets(
                    cleanup_thresholds,
                    remove_empty,
                )
                if loop is not None:
                    loop.create_task(cleanup_coro)
                else:
                    backend_loop = getattr(self._backend, "_loop", None)
                    if backend_loop is not None and backend_loop.is_running():
                        asyncio.run_coroutine_threadsafe(cleanup_coro, backend_loop)

        return RateLimiterSnapshot(
            backend=backend_name,
            tracked_keys=tracked_keys,
            max_utilization=max_utilization,
            saturated_keys=saturated,
        )

    def _resolve_policy(
        self, subject: str | None, ip_address: str | None
    ) -> tuple[RateLimitPolicy, str]:
        if subject:
            specific = self._settings.client_policies.get(subject)
            if specific is not None:
                return specific, f"subject:{subject}"
            return self._settings.default_policy, f"subject:{subject}"
        if ip_address:
            policy = self._settings.unauthenticated_policy or self._settings.default_policy
            return policy, f"ip:{ip_address}"
        return self._settings.default_policy, "anonymous"

    def _policy_for_storage_key(self, storage_key: str) -> RateLimitPolicy:
        """Infer the governing policy for the stored key."""

        if storage_key.startswith("subject:"):
            subject = storage_key.split(":", 1)[1]
            policy, _ = self._resolve_policy(subject, None)
            return policy
        if storage_key.startswith("ip:"):
            ip = storage_key.split(":", 1)[1]
            policy, _ = self._resolve_policy(None, ip)
            return policy
        policy, _ = self._resolve_policy(None, None)
        return policy

    async def _prune_snapshot_buckets(
        self,
        cleanup_thresholds: dict[str, float],
        remove_empty: set[str],
    ) -> None:
        records = getattr(self._backend, "_records", None)
        lock = getattr(self._backend, "_lock", None)
        if not isinstance(records, dict) or lock is None:
            return

        async with lock:
            for storage_key, threshold in cleanup_thresholds.items():
                bucket = records.get(storage_key)
                if not isinstance(bucket, deque):
                    continue
                while bucket and bucket[0] <= threshold:
                    bucket.popleft()
                if not bucket:
                    records.pop(storage_key, None)

            for storage_key in remove_empty:
                bucket = records.get(storage_key)
                if not bucket:
                    records.pop(storage_key, None)


def build_rate_limiter(settings: ApiRateLimitSettings) -> SlidingWindowRateLimiter:
    """Instantiate a rate limiter using the most appropriate backend."""

    if settings.redis_url is not None:
        try:
            from redis.asyncio import from_url
        except ModuleNotFoundError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                "Redis-backed rate limiting requires the 'redis' package to be installed."
            ) from exc

        client = from_url(str(settings.redis_url), encoding="utf-8", decode_responses=False)
        backend: RateLimiterBackend = RedisSlidingWindowBackend(
            client, key_prefix=settings.redis_key_prefix
        )
    else:
        backend = InMemorySlidingWindowBackend()

    return SlidingWindowRateLimiter(backend, settings)
