# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import itertools

import pytest

from core.data.adapters.unified import (
    BackoffPolicy,
    RateLimiter,
    RateLimitRule,
    RestIngestionAdapter,
    WebSocketIngestionAdapter,
)


def test_rate_limiter_waits_when_budget_exhausted(monkeypatch):
    rule = RateLimitRule(max_calls=2, period_s=1.0)
    limiter = RateLimiter(rule)

    times = [0.0]

    def fake_monotonic():
        return times[0]

    monkeypatch.setattr("core.data.adapters.unified.monotonic", fake_monotonic)

    assert limiter.consume() == 0.0
    assert limiter.consume() == 0.0
    wait = limiter.consume()
    assert pytest.approx(wait, rel=1e-3) == 0.5
    times[0] += 1.0
    assert limiter.consume() == 0.0


def test_rest_adapter_deduplicates_and_retries(monkeypatch):
    calls = []

    payloads = itertools.cycle(
        [
            [
                {"timestamp": 1, "price": 100},
                {"timestamp": 1, "price": 100},
                {"timestamp": 2, "price": 101},
            ]
        ]
    )

    def request_fn():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("boom")
        return next(payloads)

    sleeps: list[float] = []
    adapter = RestIngestionAdapter(
        request_fn,
        rate_limiter=RateLimiter(RateLimitRule(max_calls=10, period_s=1.0)),
        backoff=BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1),
        max_retries=2,
        sleep=sleeps.append,
    )

    result = adapter.fetch()
    assert result == [{"timestamp": 1, "price": 100}, {"timestamp": 2, "price": 101}]
    assert sleeps[0] >= 0.0


def test_rest_adapter_injects_trace_context():
    captured: dict[str, dict[str, str]] = {}

    def request_fn(*_, **kwargs):
        captured["headers"] = dict(kwargs.get("headers", {}))
        return []

    adapter = RestIngestionAdapter(
        request_fn,
        rate_limiter=RateLimiter(RateLimitRule(max_calls=10, period_s=1.0)),
        backoff=BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1),
        context_injector=lambda headers: headers.__setitem__("traceparent", "00-test"),
    )

    adapter.fetch()
    assert captured["headers"]["traceparent"] == "00-test"


def test_websocket_adapter_reconnects(monkeypatch):
    attempts = [0]

    def connect():
        attempts[0] += 1
        if attempts[0] == 1:
            raise ConnectionError("drop")
        return [
            {"timestamp": 1, "value": "a"},
            {"timestamp": 1, "value": "a"},
            {"timestamp": 2, "value": "b"},
        ]

    sleeps: list[float] = []
    adapter = WebSocketIngestionAdapter(
        connect,
        backoff=BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1),
        sleep=sleeps.append,
    )
    messages = list(adapter.messages())
    assert messages == [{"timestamp": 1, "value": "a"}, {"timestamp": 2, "value": "b"}]
    assert sleeps[0] >= 0.0


def test_websocket_adapter_context_injection():
    seen: list[dict[str, str]] = []

    def connect(**kwargs):
        seen.append(dict(kwargs.get("headers", {})))
        return []

    adapter = WebSocketIngestionAdapter(
        connect,
        context_injector=lambda headers: headers.__setitem__("traceparent", "00-ws"),
    )

    list(adapter.messages())
    assert seen[0]["traceparent"] == "00-ws"


class _FakeLimiter:
    """A rate limiter that always reports a fixed wait -- lets us pin the sleep
    guard without depending on the real token-bucket timing."""

    def __init__(self, wait: float) -> None:
        self._wait = wait

    def consume(self) -> float:
        return self._wait


def test_rest_sleep_fires_only_for_positive_wait(monkeypatch):
    """`if seconds > 0` gates the rate-limit sleep on a POSITIVE wait only.

    Under Gt->LtE the guard inverts: a real positive wait is skipped and a
    zero/negative wait triggers a pointless sleep.
    """
    positive_sleeps: list[float] = []
    RestIngestionAdapter(
        lambda *a, **k: [], rate_limiter=_FakeLimiter(0.5),
        backoff=BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1), sleep=positive_sleeps.append
    ).fetch()
    assert 0.5 in positive_sleeps  # positive wait DID sleep

    zero_sleeps: list[float] = []
    RestIngestionAdapter(
        lambda *a, **k: [], rate_limiter=_FakeLimiter(0.0),
        backoff=BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1), sleep=zero_sleeps.append
    ).fetch()
    assert 0.0 not in zero_sleeps  # zero wait did NOT sleep


def test_websocket_custom_backoff_is_kept_not_replaced():
    """`backoff or BackoffPolicy()` keeps a caller-supplied policy.

    Under Or->And a truthy custom policy collapses to a fresh default,
    discarding the caller's delay schedule.
    """
    custom = BackoffPolicy(base_delay_s=0.1, max_delay_s=0.1)
    adapter = WebSocketIngestionAdapter(lambda: [], backoff=custom)
    assert adapter._backoff is custom


def test_websocket_rate_limit_sleep_fires_only_for_positive_wait():
    """`if wait_time > 0` in the stream loop sleeps only on a positive wait.

    Under Gt->LtE a positive rate-limit wait would be ignored inside messages().
    """
    sleeps: list[float] = []
    adapter = WebSocketIngestionAdapter(
        lambda **_: [{"timestamp": 1, "value": "a"}],
        rate_limiter=_FakeLimiter(0.25),
        sleep=sleeps.append,
    )
    list(adapter.messages())
    assert 0.25 in sleeps
