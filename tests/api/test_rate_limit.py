import asyncio
from collections import deque
from typing import Any

import pytest
from fastapi import HTTPException

from application.api.rate_limit import (
    InMemorySlidingWindowBackend,
    RedisSlidingWindowBackend,
    SlidingWindowRateLimiter,
)
from application.settings import ApiRateLimitSettings, RateLimitPolicy


class _FakePipeline:
    """Minimal async pipeline emulating the redis client behaviour."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._execute_result: tuple[Any, ...] = (None, None, 0, True)

    def zremrangebyscore(self, *args: Any) -> "_FakePipeline":
        self.calls.append(("zremrangebyscore", args))
        return self

    def zadd(self, *args: Any) -> "_FakePipeline":
        self.calls.append(("zadd", args))
        return self

    def zcard(self, *args: Any) -> "_FakePipeline":
        self.calls.append(("zcard", args))
        return self

    def expire(self, *args: Any) -> "_FakePipeline":
        self.calls.append(("expire", args))
        return self

    async def execute(self) -> tuple[Any, ...]:
        self.calls.append(("execute", tuple()))
        return self._execute_result


class _FakeRedisClient:
    def __init__(self, pipeline: _FakePipeline) -> None:
        self._pipeline = pipeline

    def pipeline(self) -> _FakePipeline:
        return self._pipeline


@pytest.mark.anyio
async def test_redis_backend_hit_invokes_expected_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 123.456
    window_seconds = 10.2
    pipeline = _FakePipeline()
    pipeline._execute_result = (1, 1, 5, True)
    client = _FakeRedisClient(pipeline)
    backend = RedisSlidingWindowBackend(client, key_prefix="trade")

    monkeypatch.setattr("application.api.rate_limit.time.time", lambda: now)

    count = await backend.hit("user", limit=20, window_seconds=window_seconds)

    assert count == 5
    redis_key = "trade:user"
    expected_calls = {
        "zremrangebyscore": (redis_key, 0, pytest.approx(now - window_seconds)),
        "zadd": (redis_key, {str(now): now}),
        "zcard": (redis_key,),
        "expire": (redis_key, int(window_seconds) + 1),
    }

    # verify ordering prior to execute
    for name, args in pipeline.calls[:-1]:
        assert name in expected_calls
        expected = expected_calls[name]
        assert args == expected
    assert pipeline.calls[-1][0] == "execute"
    assert pipeline.calls[-1][1] == tuple()


@pytest.mark.anyio
async def test_rate_limiter_check_allows_within_limit() -> None:
    backend = InMemorySlidingWindowBackend()
    settings = ApiRateLimitSettings(
        default_policy=RateLimitPolicy(max_requests=2, window_seconds=30.0)
    )
    limiter = SlidingWindowRateLimiter(backend, settings)

    await limiter.check(subject="alice", ip_address=None)
    await limiter.check(subject="alice", ip_address=None)


@pytest.mark.anyio
async def test_rate_limiter_check_raises_on_limit_exceeded() -> None:
    backend = InMemorySlidingWindowBackend()
    settings = ApiRateLimitSettings(
        default_policy=RateLimitPolicy(max_requests=2, window_seconds=30.0)
    )
    limiter = SlidingWindowRateLimiter(backend, settings)

    await limiter.check(subject="bob", ip_address=None)
    await limiter.check(subject="bob", ip_address=None)
    with pytest.raises(HTTPException) as exc:
        await limiter.check(subject="bob", ip_address=None)

    assert exc.value.status_code == 429


@pytest.mark.anyio
async def test_snapshot_filters_expired_entries_and_schedules_cleanup() -> None:
    backend = InMemorySlidingWindowBackend()
    loop = asyncio.get_running_loop()
    now = loop.time()

    vip_policy = RateLimitPolicy(max_requests=2, window_seconds=5.0)
    default_policy = RateLimitPolicy(max_requests=5, window_seconds=10.0)
    settings = ApiRateLimitSettings(
        default_policy=default_policy,
        client_policies={"vip": vip_policy},
    )
    limiter = SlidingWindowRateLimiter(backend, settings)

    backend._records = {
        "subject:vip": deque([now - 10.0, now - 4.0, now - 1.0]),
        "ip:1.2.3.4": deque([now - 1.0]),
        "subject:stale": deque([now - 20.0]),
    }

    snapshot = limiter.snapshot()
    assert snapshot.backend == "InMemorySlidingWindowBackend"
    assert snapshot.tracked_keys == 2
    assert snapshot.max_utilization == pytest.approx(1.0)
    assert snapshot.saturated_keys == ["subject:vip"]

    await asyncio.sleep(0)

    vip_bucket = backend._records["subject:vip"]
    assert list(vip_bucket) == [pytest.approx(now - 4.0), pytest.approx(now - 1.0)]
    assert "subject:stale" not in backend._records
