from __future__ import annotations

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
