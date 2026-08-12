# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Real-wire integration test for ``LoopbackHttpTransport``.

This test does not mock httpx. It spawns a stdlib ``http.server`` on
loopback that mirrors the contract of the OpenClaw-side
``geosync-bridge`` plugin (``openclaw-main/extensions/geosync-bridge/
src/server.mjs``), then exercises ``CognitiveSidecar`` end-to-end:

    Cycle → AdvisoryRequest → LoopbackHttpTransport
                            → real HTTP roundtrip
                            → AdvisoryResponse → host

The bridge contract is the same on both sides; this proves the wire
agrees with the schema without needing the Node plugin at test time.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, Mapping

import pytest

from runtime.cognitive_bridge import (
    PROTOCOL_VERSION,
    AdvisoryRequest,
    AdvisoryStatus,
    CognitiveSidecar,
    LoopbackHttpTransport,
    SidecarConfig,
)

ENDPOINT = "/v1/cognitive-bridge/exchange"


class _Handler(BaseHTTPRequestHandler):
    """Minimal stand-in for the geosync-bridge plugin server."""

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        if self.path == "/healthz":
            payload = {"status": "ok", "protocol_version": PROTOCOL_VERSION}
            self._reply(200, payload)
            return
        self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        if self.path != ENDPOINT:
            self._reply(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        envelope = json.loads(body)
        cid = envelope["correlation_id"]
        request = envelope["request"]
        coherence = float(request.get("coherence", 0.0))
        recommendation = "maintain" if coherence >= 0.5 else "narrow_exposure"
        rationale = f"coherence={coherence:.3f}; mode=heuristic"
        self._reply(
            200,
            {
                "protocol_version": PROTOCOL_VERSION,
                "correlation_id": cid,
                "status": "ok",
                "tier": "speculative",
                "recommendation": recommendation,
                "rationale": rationale,
                "received_at": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args  # silence default test-output spam

    def _reply(self, code: int, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def _running_server() -> Iterator[str]:
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}{ENDPOINT}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@pytest.fixture
def endpoint() -> Iterator[str]:
    with _running_server() as url:
        yield url


def _request(*, coherence: float = 0.82) -> AdvisoryRequest:
    return AdvisoryRequest(
        agent_state="REVIEW",
        coherence=coherence,
        kill_switch_active=False,
        stressed_state=False,
        question="hold or narrow?",
    )


def test_real_wire_roundtrip_returns_ok_with_matching_correlation(
    endpoint: str,
) -> None:
    transport = LoopbackHttpTransport(endpoint=endpoint)
    sidecar = CognitiveSidecar(
        transport=transport,
        config=SidecarConfig(timeout_s=2.0),
    )
    request = _request()
    response = sidecar.advise(request)
    assert response.status is AdvisoryStatus.OK
    assert response.correlation_id == request.correlation_id()
    assert response.tier.value == "speculative"
    assert response.protocol_version == PROTOCOL_VERSION


def test_real_wire_classifies_low_coherence_as_narrow_exposure(
    endpoint: str,
) -> None:
    transport = LoopbackHttpTransport(endpoint=endpoint)
    sidecar = CognitiveSidecar(transport=transport, config=SidecarConfig(timeout_s=2.0))
    response = sidecar.advise(_request(coherence=0.30))
    assert response.recommendation == "narrow_exposure"


def test_real_wire_kill_switch_short_circuits_before_transport(
    endpoint: str,
) -> None:
    transport = LoopbackHttpTransport(endpoint=endpoint)
    sidecar = CognitiveSidecar(transport=transport, config=SidecarConfig(timeout_s=2.0))
    request = AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.82,
        kill_switch_active=True,
        stressed_state=False,
        question="hold or narrow?",
    )
    response = sidecar.advise(request)
    assert response.status is AdvisoryStatus.DISABLED


def test_real_wire_unreachable_endpoint_collapses_to_unavailable() -> None:
    transport = LoopbackHttpTransport(endpoint="http://127.0.0.1:1/closed")
    sidecar = CognitiveSidecar(transport=transport, config=SidecarConfig(timeout_s=1.0))
    response = sidecar.advise(_request())
    assert response.status is AdvisoryStatus.UNAVAILABLE
