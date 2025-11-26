"""Lightweight health check HTTP server for TradePulse services."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional


class _HealthState:
    def __init__(self) -> None:
        self.live = True
        self.ready = False
        self.components: Dict[str, Dict[str, object]] = {}
        self._lock = threading.Lock()

    def set_ready(self, ready: bool) -> None:
        with self._lock:
            self.ready = ready

    def set_live(self, live: bool) -> None:
        with self._lock:
            self.live = live

    def update_component(
        self, name: str, healthy: bool, message: str | None = None
    ) -> None:
        payload: Dict[str, object] = {"healthy": bool(healthy)}
        if message:
            payload["message"] = message
        with self._lock:
            self.components[name] = payload

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "live": self.live,
                "ready": self.ready,
                "components": dict(self.components),
            }


class HealthServer:
    """Threaded HTTP server exposing ``/healthz`` and ``/readyz`` endpoints."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8085) -> None:
        self._state = _HealthState()
        self._server = ThreadingHTTPServer(
            (host, port), self._handler_factory(self._state)
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="health-server", daemon=True
        )
        self._started = threading.Event()

    @staticmethod
    def _handler_factory(state: _HealthState):
        class Handler(BaseHTTPRequestHandler):
            def _write(self, status: int, payload: Dict[str, object]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(
                self,
            ) -> None:  # noqa: N802 - interface defined by BaseHTTPRequestHandler
                snapshot = state.snapshot()
                if self.path == "/healthz":
                    status = 200 if snapshot["live"] else 503
                    payload = {
                        "status": "ok" if snapshot["live"] else "down",
                        **snapshot,
                    }
                    self._write(status, payload)
                    return
                if self.path == "/health/live":
                    status = 200 if snapshot["live"] else 503
                    payload = {
                        "status": "live" if snapshot["live"] else "down",
                        **snapshot,
                    }
                    self._write(status, payload)
                    return
                if self.path == "/readyz":
                    status = 200 if snapshot["ready"] else 503
                    payload = {
                        "status": "ready" if snapshot["ready"] else "not-ready",
                        **snapshot,
                    }
                    self._write(status, payload)
                    return
                self._write(404, {"status": "unknown", **snapshot})

            def log_message(self, *args, **kwargs):
                return  # suppress noisy default logging

        return Handler

    @property
    def port(self) -> int:
        addr = self._server.server_address
        # server_address is (host, port) for IPv4 or (host, port, flow, scope) for IPv6
        return int(addr[1])

    def start(self) -> None:
        if self._started.is_set():
            return
        self._thread.start()
        self._started.set()

    def shutdown(self) -> None:
        if not self._started.is_set():
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._started.clear()

    def set_ready(self, ready: bool = True) -> None:
        self._state.set_ready(ready)

    def set_live(self, live: bool = True) -> None:
        self._state.set_live(live)

    def update_component(
        self, name: str, healthy: bool, message: str | None = None
    ) -> None:
        self._state.update_component(name, healthy, message)

    def __enter__(self) -> "HealthServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:
        self.shutdown()
        return None


__all__ = ["HealthServer"]
