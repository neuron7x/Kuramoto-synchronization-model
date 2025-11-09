"""Helpers to run observability exporters in isolated processes."""

from __future__ import annotations

import multiprocessing
import time
from typing import Optional

try:  # pragma: no cover - optional dependency import guarded at runtime
    from prometheus_client import start_http_server

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - prometheus_client is optional
    start_http_server = None  # type: ignore[assignment]
    _PROM_AVAILABLE = False


def _run_prometheus_exporter(
    port: int, addr: str, ready: multiprocessing.Event
) -> None:
    if not _PROM_AVAILABLE or start_http_server is None:  # pragma: no cover - defensive
        return
    start_http_server(port, addr)
    ready.set()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:  # pragma: no cover - normal shutdown
        return


def start_prometheus_exporter_process(
    port: int = 8000, addr: str = ""
) -> multiprocessing.Process:
    """Spawn a dedicated process that serves Prometheus metrics."""

    if not _PROM_AVAILABLE:
        raise RuntimeError("prometheus_client is not installed")

    ready = multiprocessing.Event()
    process = multiprocessing.Process(
        target=_run_prometheus_exporter,
        name="prometheus-exporter",
        args=(port, addr, ready),
        daemon=True,
    )
    process.start()
    ready.wait(timeout=5)
    return process


def stop_exporter_process(
    process: Optional[multiprocessing.Process], *, timeout: float = 5.0
) -> None:
    """Terminate an exporter process if it is still alive."""

    if process is None:
        return
    if not process.is_alive():
        return
    process.terminate()
    process.join(timeout=timeout)


__all__ = [
    "start_prometheus_exporter_process",
    "stop_exporter_process",
]
