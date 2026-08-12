# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from prometheus_client import CollectorRegistry

from observability.health_monitor import (
    HealthCheck,
    HealthCheckResult,
    PeriodicHealthMonitor,
)


class _StubHealthServer:
    def __init__(self) -> None:
        self.live: bool | None = None
        self.ready: bool | None = None
        self.components: dict[str, tuple[bool, str | None]] = {}

    def set_live(self, live: bool) -> None:
        self.live = live

    def set_ready(self, ready: bool) -> None:
        self.ready = ready

    def update_component(self, name: str, healthy: bool, message: str | None = None) -> None:
        self.components[name] = (healthy, message)


def test_periodic_health_monitor_records_metrics(monkeypatch) -> None:
    registry = CollectorRegistry()

    from core.utils.metrics import MetricsCollector

    collector = MetricsCollector(registry)
    monkeypatch.setattr("observability.health_monitor.get_metrics_collector", lambda: collector)

    server = _StubHealthServer()

    checks: list[HealthCheck] = [
        HealthCheck(name="healthy", probe=lambda: HealthCheckResult(True, "ok"), interval=1.0),
        HealthCheck(
            name="unhealthy",
            probe=lambda: HealthCheckResult(False, "failure"),
            interval=1.0,
        ),
    ]

    monitor = PeriodicHealthMonitor(server, checks)
    monitor.run_once()

    assert server.live is True
    assert server.ready is False
    assert server.components["healthy"] == (True, "ok")
    assert server.components["unhealthy"] == (False, "failure")

    healthy_count = registry.get_sample_value(
        "geosync_health_check_latency_seconds_count", {"check_name": "healthy"}
    )
    unhealthy_status = registry.get_sample_value(
        "geosync_health_check_status", {"check_name": "unhealthy"}
    )

    assert healthy_count == 1.0
    assert unhealthy_status == 0.0
