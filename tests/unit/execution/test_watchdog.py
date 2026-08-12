# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import threading
import time

from execution.watchdog import Watchdog
from observability.health import HealthServer


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_watchdog_restarts_dead_threads() -> None:
    runs: list[float] = []

    def worker(stop_event: threading.Event) -> None:
        runs.append(time.monotonic())
        if len(runs) == 1:
            return
        while not stop_event.wait(0.05):
            pass

    watchdog = Watchdog(name="test-watchdog", monitor_interval=0.05)
    try:
        watchdog.register("flaky", worker, args=(watchdog.stop_event,))
        assert _wait_for(lambda: len(runs) >= 2)
    finally:
        watchdog.stop()

    assert len(runs) >= 2


def test_watchdog_updates_live_probe_status() -> None:
    with HealthServer(host="127.0.0.1", port=0) as server:
        url = f"http://127.0.0.1:{server.port}/health/live"
        watchdog = Watchdog(
            name="probe-watchdog",
            monitor_interval=0.05,
            health_url=url,
            health_probe_interval=0.1,
        )
        try:

            def worker(stop_event: threading.Event) -> None:
                while not stop_event.wait(0.05):
                    pass

            watchdog.register("steady", worker, args=(watchdog.stop_event,))
            assert _wait_for(lambda: watchdog.last_live_probe_ok is True)

            server.set_live(False)
            assert _wait_for(lambda: watchdog.last_live_probe_ok is False)
        finally:
            watchdog.stop()
