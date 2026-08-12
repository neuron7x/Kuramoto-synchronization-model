# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Periodic health monitoring utilities for GeoSync services."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Iterable, Mapping, MutableMapping

from core.utils.metrics import get_metrics_collector

from .health import HealthServer

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HealthCheckResult:
    """Structured outcome returned by health probe callables."""

    healthy: bool
    detail: str | None = None
    metrics: Mapping[str, object] | None = None


ProbeReturn = (
    HealthCheckResult
    | bool
    | tuple[bool, str | None]
    | tuple[bool, str | None, Mapping[str, object]]
)
Probe = Callable[[], ProbeReturn]


@dataclass(slots=True)
class HealthCheck:
    """Configuration describing a periodic health probe."""

    name: str
    probe: Probe
    interval: float = 30.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Health check name must be provided")
        if self.interval <= 0:
            raise ValueError("Health check interval must be positive")


class PeriodicHealthMonitor:
    """Background worker that executes health checks on a fixed cadence."""

    def __init__(self, server: HealthServer, checks: Iterable[HealthCheck]) -> None:
        self._server = server
        self._checks = list(checks)
        if not self._checks:
            raise ValueError("At least one health check must be configured")

        self._metrics = get_metrics_collector()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_run: MutableMapping[str, float] = {check.name: 0.0 for check in self._checks}
        self._statuses: MutableMapping[str, bool] = {check.name: False for check in self._checks}
        self._lock = threading.Lock()
        self._poll_interval = min(check.interval for check in self._checks)

    def start(self) -> None:
        """Start the monitoring thread."""

        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="health-monitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop monitoring and join the worker thread."""

        with self._lock:
            thread = self._thread
            if not thread:
                return
            self._stop_event.set()
        thread.join(timeout or 5.0)
        with self._lock:
            self._thread = None

    def run_once(self) -> None:
        """Execute all configured checks once synchronously."""

        for check in self._checks:
            self._run_check(check)
        self._refresh_server_state()

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            now = time.monotonic()
            executed = False
            for check in self._checks:
                target = self._next_run.get(check.name, 0.0)
                if now < target:
                    continue
                self._run_check(check)
                self._next_run[check.name] = now + check.interval
                executed = True

            if executed:
                self._refresh_server_state()

    def _run_check(self, check: HealthCheck) -> None:
        start = perf_counter()
        try:
            result = check.probe()
        except Exception as exc:  # pragma: no cover - defensive logging path
            duration = perf_counter() - start
            LOGGER.exception("Health check probe failed", extra={"check": check.name})
            detail = str(exc)
            healthy = False
            metrics: Mapping[str, object] | None = None
        else:
            duration = perf_counter() - start
            healthy, detail, metrics = self._normalise_result(result)

        self._metrics.observe_health_check_latency(check.name, duration)
        self._metrics.set_health_check_status(check.name, healthy)
        message = self._format_message(detail, metrics)
        self._server.update_component(check.name, healthy, message)
        self._statuses[check.name] = healthy

        log_fn = LOGGER.info if healthy else LOGGER.warning
        log_fn(
            "Health check evaluated",
            extra={
                "event": "health.check",
                "check": check.name,
                "healthy": healthy,
                "detail": detail,
                "metrics": dict(metrics or {}),
                "duration_seconds": round(duration, 4),
            },
        )

    def _refresh_server_state(self) -> None:
        self._server.set_live(True)
        overall = all(self._statuses.values())
        self._server.set_ready(overall)

    @staticmethod
    def _normalise_result(
        result: ProbeReturn,
    ) -> tuple[bool, str | None, Mapping[str, object] | None]:
        if isinstance(result, HealthCheckResult):
            return result.healthy, result.detail, result.metrics
        if isinstance(result, tuple):
            if len(result) == 2:
                return bool(result[0]), result[1], None
            if len(result) == 3:
                return bool(result[0]), result[1], result[2]
            raise ValueError("Health check tuple results must contain 2 or 3 elements")
        return bool(result), None, None

    @staticmethod
    def _format_message(detail: str | None, metrics: Mapping[str, object] | None) -> str | None:
        if not metrics:
            return detail

        parts = [f"{key}={value}" for key, value in sorted(metrics.items())]
        metrics_payload = ", ".join(parts)
        if detail:
            return f"{detail} | {metrics_payload}"
        return metrics_payload


__all__ = ["HealthCheck", "HealthCheckResult", "PeriodicHealthMonitor"]
