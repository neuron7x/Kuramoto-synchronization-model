# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Transport adapters for the cognitive bridge.

Two transports ship with the package:

* ``InMemoryTransport`` — deterministic, dependency-free; used in tests
  and offline replay. Accepts a ``handler`` callable and applies it
  synchronously.
* ``LoopbackHttpTransport`` — POSTs the canonical JSON envelope to a
  local OpenClaw gateway (default ``http://127.0.0.1:18789``). Network
  faults are wrapped as ``BridgeTransportError`` so the sidecar can
  collapse to UNAVAILABLE.

Custom transports must implement the ``Transport`` Protocol.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

import httpx

from runtime.cognitive_bridge.errors import BridgeTransportError
from runtime.cognitive_bridge.protocol import AdvisoryRequest, AdvisoryResponse


@runtime_checkable
class Transport(Protocol):
    """Send an ``AdvisoryRequest`` and return an ``AdvisoryResponse``."""

    def exchange(self, request: AdvisoryRequest, *, timeout_s: float) -> AdvisoryResponse: ...


class InMemoryTransport:
    """Deterministic transport backed by a Python callable.

    The handler is responsible for producing a valid ``AdvisoryResponse``;
    the transport itself only enforces the contract that whatever the
    handler returns is forwarded verbatim.
    """

    def __init__(
        self,
        handler: Callable[[AdvisoryRequest], AdvisoryResponse],
    ) -> None:
        self._handler = handler

    def exchange(self, request: AdvisoryRequest, *, timeout_s: float) -> AdvisoryResponse:
        del timeout_s  # In-memory handler runs synchronously; budget is host-side.
        return self._handler(request)


class LoopbackHttpTransport:
    """Talk to a local OpenClaw gateway over loopback HTTP.

    The geosync-bridge plugin (an autonomous Node HTTP server bundled
    with OpenClaw at ``openclaw-main/extensions/geosync-bridge``) listens
    on loopback port 18790 by default and exposes the JSON endpoint
    ``/v1/cognitive-bridge/exchange``. The OpenClaw gateway proper is on
    18789 — the two are deliberately separated so they can run side by
    side. We POST the canonical request envelope and parse the JSON
    reply into ``AdvisoryResponse``.

    Any network or codec failure is wrapped as ``BridgeTransportError``;
    the caller (``CognitiveSidecar``) maps that into
    ``AdvisoryStatus.UNAVAILABLE`` per CB-INV-2.
    """

    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:18790/v1/cognitive-bridge/exchange",
        client: httpx.Client | None = None,
    ) -> None:
        # Default port is 18790, NOT 18789. The OpenClaw gateway already
        # owns 18789 on this host; the geosync-bridge plugin sits on 18790
        # so the two services can run side-by-side without EADDRINUSE.
        self._endpoint = endpoint
        self._client = client or httpx.Client()

    def exchange(self, request: AdvisoryRequest, *, timeout_s: float) -> AdvisoryResponse:
        envelope = {
            "request": request.model_dump(mode="json"),
            "correlation_id": request.correlation_id(),
        }
        try:
            response = self._client.post(self._endpoint, json=envelope, timeout=timeout_s)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BridgeTransportError(str(exc)) from exc
        return AdvisoryResponse.model_validate(payload)


__all__ = ["InMemoryTransport", "LoopbackHttpTransport", "Transport"]
