from __future__ import annotations

import asyncio
import math
import sys
import types

import pytest

from core.data.adapters import base


def test_default_retry_exceptions_include_optional_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dummy_httpx = types.ModuleType("httpx")
    dummy_ccxt = types.ModuleType("ccxt")

    class DummyHTTPError(Exception):
        pass

    class DummyCCXTError(Exception):
        pass

    dummy_httpx.HTTPError = DummyHTTPError  # type: ignore[attr-defined]
    dummy_ccxt.BaseError = DummyCCXTError  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "httpx", dummy_httpx)
    monkeypatch.setitem(sys.modules, "ccxt", dummy_ccxt)

    exceptions = base._default_retry_exceptions()
    assert DummyHTTPError in exceptions
    assert DummyCCXTError in exceptions
    assert asyncio.TimeoutError in exceptions


def test_retry_config_compute_backoff_applies_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = base.RetryConfig(multiplier=1.0, max_backoff=4.0, jitter=0.5)

    calls: list[tuple[float, float]] = []

    def fake_uniform(low: float, high: float) -> float:
        calls.append((low, high))
        return high  # return the max jitter so the result is deterministic

    # Patch the SystemRandom instance's uniform method
    monkeypatch.setattr(config._rng, "uniform", fake_uniform)

    delay = config.compute_backoff(attempt_number=2)
    assert math.isclose(delay, 3.0, rel_tol=1e-9)
    assert calls == [(0.0, 1.0)]


def test_retry_config_compute_backoff_respects_max_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = base.RetryConfig(multiplier=1.0, max_backoff=5.0, jitter=0.5)

    def fake_uniform(low: float, high: float) -> float:
        # Use the maximum jitter to attempt to exceed max_backoff.
        return high

    # Patch the SystemRandom instance's uniform method
    monkeypatch.setattr(config._rng, "uniform", fake_uniform)

    delay = config.compute_backoff(attempt_number=3)
    assert delay == pytest.approx(config.max_backoff)


@pytest.mark.asyncio
async def test_fault_tolerance_policy_retries_with_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: list[str] = []

    class DummyLimiter:
        def __init__(self, rate: int, period: float) -> None:
            self.rate = rate
            self.period = period

        async def __aenter__(self) -> "DummyLimiter":
            entries.append("enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            entries.append("exit")

    monkeypatch.setattr(base, "AsyncLimiter", DummyLimiter)

    policy = base.FaultTolerancePolicy(
        retry=base.RetryConfig(
            attempts=3,
            multiplier=0.0,
            max_backoff=0.0,
            jitter=0.0,
            exceptions=(RuntimeError,),
        ),
        rate_limit=base.RateLimitConfig(rate=2, period_seconds=0.1),
    )

    attempts = 0

    async def flaky_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("boom")
        return "ok"

    result = await policy.run(flaky_operation)
    assert result == "ok"
    assert attempts == 3
    assert entries == ["enter", "exit", "enter", "exit", "enter", "exit"]


@pytest.mark.asyncio
async def test_sleep_for_attempt_uses_retry_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, float] = {}

    async def fake_sleep(delay: float) -> None:
        recorded["delay"] = delay

    monkeypatch.setattr(base.asyncio, "sleep", fake_sleep)

    policy = base.FaultTolerancePolicy(
        retry=base.RetryConfig(multiplier=0.25, max_backoff=10.0, jitter=0.0)
    )

    await policy.sleep_for_attempt(4)
    assert math.isclose(
        recorded["delay"], policy.retry.compute_backoff(4), rel_tol=1e-9
    )
