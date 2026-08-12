# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Thread watchdog supervising background worker threads.

The watchdog keeps a registry of worker callables, restarting them if the
underlying :class:`threading.Thread` stops unexpectedly.  It can optionally
publish heartbeats to Redis and perform periodic liveness probes against the
process health endpoint so operators receive fast feedback when workers crash.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

try:  # pragma: no cover - ``httpx`` is an optional dependency at runtime
    import httpx
except Exception:  # pragma: no cover - defensive, used in degraded mode
    httpx = None  # type: ignore[assignment]

from core.utils.metrics import get_metrics_collector

LOGGER = logging.getLogger(__name__)

RedisPublisher = Any


@dataclass(slots=True)
class _WorkerSpec:
    """Book-keeping container describing a supervised worker."""

    target: Callable[..., None]
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    restart: bool = True
    thread: threading.Thread | None = None
    restarts: int = 0


class Watchdog:
    """Supervise background workers and restart them when they exit."""

    def __init__(
        self,
        *,
        name: str = "watchdog",
        redis_client: RedisPublisher | None = None,
        heartbeat_channel: str | None = None,
        heartbeat_interval: float = 30.0,
        monitor_interval: float = 1.0,
        health_url: str | None = "http://127.0.0.1:8085/health/live",
        health_probe_interval: float = 5.0,
        health_timeout: float = 2.0,
    ) -> None:
        self._name = name
        self._redis_client = redis_client
        self._heartbeat_channel = heartbeat_channel
        self._heartbeat_interval = max(1.0, float(heartbeat_interval))
        self._monitor_interval = max(0.05, float(monitor_interval))
        self._health_url = health_url
        self._health_probe_interval = max(0.5, float(health_probe_interval))
        self._health_timeout = max(0.1, float(health_timeout))

        self._metrics = get_metrics_collector()

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._workers: Dict[str, _WorkerSpec] = {}
        self._monitor_thread: threading.Thread | None = None
        self._stopping = False
        self._last_live_probe_ok: bool | None = None
        self._last_live_probe_at: float | None = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def __enter__(self) -> "Watchdog":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:
        self.stop()
        return None

    @property
    def stop_event(self) -> threading.Event:
        """Event set when the watchdog is shutting down."""

        return self._stop_event

    @property
    def last_live_probe_ok(self) -> bool | None:
        """Return the outcome of the most recent liveness probe."""

        return self._last_live_probe_ok

    @property
    def last_live_probe_at(self) -> float | None:
        """Return the timestamp of the most recent liveness probe."""

        return self._last_live_probe_at

    def start(self) -> None:
        """Start the watchdog monitor thread."""

        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                return
            if self._stopping:
                # Fresh start after a previous stop; reset state.
                self._stop_event.clear()
                self._stopping = False

            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"{self._name}-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def stop(self, *, timeout: float | None = None) -> None:
        """Stop monitoring and prevent further restarts."""

        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._stop_event.set()

        monitor = self._monitor_thread
        if monitor and monitor.is_alive():
            monitor.join(timeout=timeout or 5.0)

        with self._lock:
            for name, spec in list(self._workers.items()):
                thread = spec.thread
                if thread and thread.is_alive():
                    thread.join(timeout or 5.0)
            self._workers.clear()
            self._monitor_thread = None

    def snapshot(self) -> Dict[str, object]:
        """Return a thread-safe snapshot of worker and probe status."""

        with self._lock:
            workers = {
                name: {
                    "alive": bool(spec.thread and spec.thread.is_alive()),
                    "restarts": spec.restarts,
                }
                for name, spec in self._workers.items()
            }
            live_probe_ok = self._last_live_probe_ok
            live_probe_at = self._last_live_probe_at

        return {
            "workers": workers,
            "live_probe_ok": live_probe_ok,
            "live_probe_at": live_probe_at,
        }

    # ------------------------------------------------------------------
    # Worker management
    def register(
        self,
        name: str,
        target: Callable[..., None],
        *,
        args: tuple[Any, ...] | None = None,
        kwargs: Dict[str, Any] | None = None,
        restart: bool = True,
    ) -> None:
        """Register and immediately start a worker."""

        if self._stopping:
            raise RuntimeError("Cannot register workers after watchdog has been stopped")

        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}

        with self._lock:
            if name in self._workers:
                raise ValueError(f"Worker '{name}' already registered")
            spec = _WorkerSpec(target=target, args=args, kwargs=kwargs, restart=restart)
            self._workers[name] = spec
            self._start_worker(name, spec)

        self.start()

    # ------------------------------------------------------------------
    # Internal behaviour
    def _start_worker(self, name: str, spec: _WorkerSpec) -> None:
        def _runner() -> None:
            try:
                spec.target(*spec.args, **spec.kwargs)
            except Exception as exc:  # pragma: no cover - defensive logging path
                LOGGER.exception(
                    "Worker crashed",
                    extra={
                        "event": "watchdog.worker_crash",
                        "worker": name,
                        "error": str(exc),
                    },
                )

        thread = threading.Thread(target=_runner, name=f"{self._name}-{name}", daemon=True)
        spec.thread = thread
        thread.start()

    def _monitor_loop(self) -> None:
        next_heartbeat = time.monotonic() + self._heartbeat_interval
        next_probe = time.monotonic() + self._health_probe_interval if self._health_url else None

        while not self._stop_event.wait(self._monitor_interval):
            self._check_workers()

            now = time.monotonic()
            if self._redis_client is not None and self._heartbeat_channel and now >= next_heartbeat:
                self._publish_heartbeat()
                next_heartbeat = now + self._heartbeat_interval

            if self._health_url and next_probe is not None and now >= next_probe:
                self._probe_live()
                next_probe = now + self._health_probe_interval

    def _check_workers(self) -> None:
        with self._lock:
            workers = list(self._workers.items())

        for name, spec in workers:
            thread = spec.thread
            if thread is None:
                continue
            if thread.is_alive():
                continue
            if self._stopping or not spec.restart:
                continue

            spec.restarts += 1
            LOGGER.warning(
                "Restarting worker",
                extra={
                    "event": "watchdog.worker_restart",
                    "worker": name,
                    "restarts": spec.restarts,
                },
            )
            self._metrics.record_watchdog_restart(self._name, name)
            self._start_worker(name, spec)

    def _publish_heartbeat(self) -> None:
        status = {
            name: bool(spec.thread and spec.thread.is_alive())
            for name, spec in list(self._workers.items())
        }
        payload = json.dumps({"watchdog": self._name, "timestamp": time.time(), "workers": status})
        try:
            if self._redis_client is not None and self._heartbeat_channel:
                self._redis_client.publish(self._heartbeat_channel, payload)
        except Exception as exc:  # pragma: no cover - redis outages only exercised in production
            LOGGER.warning(
                "Failed to publish watchdog heartbeat",
                extra={"event": "watchdog.heartbeat_error", "error": str(exc)},
            )
        else:
            self._metrics.set_watchdog_heartbeat(self._name, time.time())

    def _probe_live(self) -> None:
        if httpx is None:
            return

        try:
            response = httpx.get(self._health_url, timeout=self._health_timeout)
            healthy = response.status_code == 200
        except Exception as exc:  # pragma: no cover - defensive logging path
            healthy = False
            LOGGER.error(
                "Watchdog live probe failed",
                extra={"event": "watchdog.live_probe_error", "error": str(exc)},
            )
        else:
            if not healthy:
                LOGGER.error(
                    "Watchdog live probe reported unhealthy",  # pragma: no cover - requires unhealthy endpoint
                    extra={
                        "event": "watchdog.live_probe_unhealthy",
                        "status": response.status_code,
                    },
                )

        timestamp = time.time()
        self._last_live_probe_ok = healthy
        self._last_live_probe_at = timestamp
        self._metrics.set_watchdog_live_probe(self._name, healthy)


__all__ = ["Watchdog"]
