from __future__ import annotations

import itertools

import pytest

from tradepulse.core.data.adapters.unified import (
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
