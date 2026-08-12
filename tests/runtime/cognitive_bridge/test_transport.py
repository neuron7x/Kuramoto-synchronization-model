# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Transport adapter tests."""

from __future__ import annotations

import httpx
import pytest

from runtime.cognitive_bridge.errors import BridgeTransportError
from runtime.cognitive_bridge.protocol import (
    PROTOCOL_VERSION,
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
)
from runtime.cognitive_bridge.transport import (
    InMemoryTransport,
    LoopbackHttpTransport,
)


def _request() -> AdvisoryRequest:
    return AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.5,
        kill_switch_active=False,
        stressed_state=False,
        question="q",
    )


def test_in_memory_transport_forwards_handler_output() -> None:
    sentinel = AdvisoryResponse(
        correlation_id="b" * 64,
        status=AdvisoryStatus.OK,
        recommendation="x",
    )
    transport = InMemoryTransport(lambda _: sentinel)
    out = transport.exchange(_request(), timeout_s=1.0)
    assert out is sentinel


def test_loopback_http_transport_parses_json_reply() -> None:
    request = _request()
    cid = request.correlation_id()
    captured: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content.decode("utf-8"))
        captured.update(body)
        return httpx.Response(
            200,
            json={
                "protocol_version": PROTOCOL_VERSION,
                "correlation_id": cid,
                "status": "ok",
                "tier": "speculative",
                "recommendation": "hold",
                "rationale": "stub",
                "received_at": "2026-01-01T00:00:00+00:00",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = LoopbackHttpTransport(
        endpoint="http://127.0.0.1:18789/v1/cognitive-bridge/exchange",
        client=client,
    )
    response = transport.exchange(request, timeout_s=1.0)
    assert response.status is AdvisoryStatus.OK
    assert response.correlation_id == cid
    assert captured["correlation_id"] == cid


def test_loopback_http_transport_wraps_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = LoopbackHttpTransport(client=client)
    with pytest.raises(BridgeTransportError):
        transport.exchange(_request(), timeout_s=1.0)


def test_loopback_http_transport_wraps_bad_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = LoopbackHttpTransport(client=client)
    with pytest.raises(BridgeTransportError):
        transport.exchange(_request(), timeout_s=1.0)
