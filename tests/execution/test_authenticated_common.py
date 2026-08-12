# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from typing import Mapping

import httpx
import pytest

from interfaces.execution.common import (
    AuthenticatedRESTExecutionConnector,
    CircuitBreaker,
    CircuitBreakerOpenError,
    DuplicateResponseDetector,
    HMACSigner,
    HTTPBackoffController,
)


class _StaticCredentialProvider:
    def __init__(self) -> None:
        self._credentials = {"API_KEY": "key", "API_SECRET": "secret"}

    def load(self, *, force: bool = False) -> dict[str, str]:  # noqa: D401 - simple helper
        return dict(self._credentials)

    def rotate(self, new_values: Mapping[str, str] | None = None) -> dict[str, str]:
        if new_values is not None:
            self._credentials = dict(new_values)
        return self.load(force=True)


class DummyAuthenticatedConnector(AuthenticatedRESTExecutionConnector):
    def __init__(self, handler, **kwargs):
        transport = httpx.MockTransport(handler)
        client = httpx.Client(base_url="https://example.com", transport=transport)
        super().__init__(
            "dummy",
            sandbox=True,
            base_url="https://example.com",
            http_client=client,
            credential_provider=_StaticCredentialProvider(),
            enable_stream=False,
            backoff=HTTPBackoffController(base_delay=0.01, max_delay=0.02, sleeper=lambda _: None),
            circuit_breaker=kwargs.get("circuit_breaker"),
            duplicate_detector=kwargs.get("duplicate_detector"),
            max_retries=kwargs.get("max_retries", 3),
        )

    def _create_signer(self, credentials):
        return HMACSigner(credentials["API_SECRET"])

    def _default_headers(self):
        return {}


@pytest.mark.parametrize("provide_idem", [True, False])
def test_request_retries_only_with_idempotency(provide_idem):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"ok": True})

    connector = DummyAuthenticatedConnector(handler, max_retries=3)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})
    if provide_idem:
        response = connector._request(
            "POST",
            "/test",
            body={"value": 1},
            idempotency_key="req-1",
        )
        assert response.json()["ok"] is True
        assert calls["count"] == 2
    else:
        with pytest.raises(httpx.HTTPStatusError):
            connector._request("POST", "/test", body={"value": 1})
        assert calls["count"] == 1
    connector.disconnect()


def test_circuit_breaker_opens_after_failures():
    failures = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        failures["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, clock=lambda: 0.0)
    connector = DummyAuthenticatedConnector(handler, circuit_breaker=breaker, max_retries=2)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})

    with pytest.raises(httpx.HTTPStatusError):
        connector._request("GET", "/unhealthy")
    assert failures["count"] == 2

    with pytest.raises(CircuitBreakerOpenError):
        connector._request("GET", "/unhealthy")
    connector.disconnect()


def test_duplicate_response_detection_marks_extension():
    payload = {"value": 42}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    detector = DuplicateResponseDetector(ttl=60.0, max_entries=8)
    connector = DummyAuthenticatedConnector(handler, duplicate_detector=detector)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})

    first = connector._request("GET", "/resource")
    second = connector._request("GET", "/resource")
    assert first.extensions.get("geosync_duplicate") is False
    assert second.extensions.get("geosync_duplicate") is True
    connector.disconnect()


def test_clock_skew_on_success_aborts_not_silently_accepted():
    # A 2xx response with a wildly wrong server clock must NOT be accepted:
    # raise_for_status() is a no-op on 2xx, so the skew guard has to re-raise.
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, headers={"X-Server-Time": "1000000000"})

    connector = DummyAuthenticatedConnector(handler, max_retries=1)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})
    with pytest.raises(RuntimeError, match="skew"):
        connector._request("GET", "/skewed")
    connector.disconnect()


def test_successful_response_with_exhausted_quota_is_not_a_failure():
    # HTTP 200 (order accepted) carrying `x-ratelimit-remaining: 0` must be
    # returned as success — converting it to a RuntimeError would make the caller
    # think the order failed and risk a double-submit.
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"filled": True}, headers={"x-ratelimit-remaining": "0"})

    connector = DummyAuthenticatedConnector(handler, max_retries=2)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})
    resp = connector._request("POST", "/order", body={"q": 1}, idempotency_key="quota-1")
    assert resp.status_code == 200
    assert resp.json()["filled"] is True
    connector.disconnect()


def test_actual_429_is_still_a_rate_limit_failure():
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"})

    connector = DummyAuthenticatedConnector(handler, max_retries=2)
    connector.connect({"API_KEY": "key", "API_SECRET": "secret"})
    with pytest.raises(httpx.HTTPStatusError):
        connector._request("GET", "/limited")
    assert calls["n"] >= 1
    connector.disconnect()
