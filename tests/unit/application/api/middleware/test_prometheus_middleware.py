# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
import types

import pytest

from application.api.middleware.prometheus import PrometheusMetricsMiddleware


class DummyCollector:
    def __init__(self) -> None:
        self.enabled = True
        self.in_flight: list[float] = []
        self.observations: list[tuple[str, str, int, float]] = []

    def track_api_in_flight(self, route: str, method: str, delta: float) -> None:
        current = self.in_flight[-1] if self.in_flight else 0.0
        self.in_flight.append(current + delta)

    def observe_api_request(
        self, route: str, method: str, status_code: int, duration: float
    ) -> None:
        self.observations.append((route, method, status_code, duration))


def _make_request(path: str = "/health"):
    scope = {"path": path, "route": types.SimpleNamespace(path=path)}
    return types.SimpleNamespace(scope=scope, method="GET", url=types.SimpleNamespace(path=path))


@pytest.mark.asyncio
async def test_inflight_gauge_balances(monkeypatch):
    collector = DummyCollector()
    middleware = PrometheusMetricsMiddleware(lambda req: None, collector=collector)

    async def call_next(request):
        return types.SimpleNamespace(status_code=200)

    await middleware.dispatch(_make_request(), call_next)

    assert collector.in_flight[0] == 1.0
    assert collector.in_flight[-1] == 0.0
    assert all(value >= 0 for value in collector.in_flight)


@pytest.mark.asyncio
async def test_latency_observation_non_negative(monkeypatch):
    collector = DummyCollector()
    middleware = PrometheusMetricsMiddleware(lambda req: None, collector=collector)

    async def call_next(request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await middleware.dispatch(_make_request("/items"), call_next)

    route, method, status, duration = collector.observations[-1]
    assert route == "/items"
    assert method == "GET"
    assert status == 500
    assert duration >= 0.0


@pytest.mark.asyncio
async def test_server_error_logs_a_traceback_and_client_error_does_not(caplog):
    """The `status_code >= 500` severity split feeds ONLY the log, so no numeric assertion
    could ever see it: a mutation probe killed 1 of 2 mutants here, and the survivor was
    `GtE -> Lt` — an inverted severity that would bury 5xx tracebacks at INFO while shouting
    about every 404. Observability that cannot fail a test is not observability.
    """
    collector = DummyCollector()
    middleware = PrometheusMetricsMiddleware(lambda req: None, collector=collector)

    class _Failure(RuntimeError):
        status_code = 503

    async def raise_server_error(request):
        raise _Failure("upstream down")

    caplog.set_level(logging.INFO, logger="geosync.api.metrics")
    with pytest.raises(_Failure):
        await middleware.dispatch(_make_request("/upstream"), raise_server_error)

    server_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert server_records, "a 5xx failure produced no ERROR-level record"
    assert server_records[-1].exc_info is not None, "the 5xx path logged without a traceback"

    caplog.clear()

    class _ClientFailure(RuntimeError):
        status_code = 404

    async def raise_client_error(request):
        raise _ClientFailure("no such item")

    with pytest.raises(_ClientFailure):
        await middleware.dispatch(_make_request("/missing"), raise_client_error)

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "a 4xx failure was logged at ERROR — the severity split is inverted"
    )
    assert [r for r in caplog.records if r.levelno == logging.INFO], (
        "a 4xx failure produced no INFO record at all"
    )
