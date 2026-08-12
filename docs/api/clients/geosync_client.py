# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Auto-generated GeoSync REST client."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

API_V1_BASE = "/api/v1"


class GeoSyncAPIClient:
    """Minimal synchronous client for the GeoSync public API."""

    def __init__(
        self,
        base_url: str,
        *,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") or "https://api.geosync"
        self._default_headers = dict(default_headers or {})
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._default_headers,
            timeout=httpx.Timeout(timeout, read=timeout),
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying httpx client."""

        self._client.close()

    def with_headers(self, headers: Mapping[str, str]) -> "GeoSyncAPIClient":
        """Return a shallow copy with additional default headers."""

        combined = dict(self._default_headers)
        combined.update(headers)
        return GeoSyncAPIClient(
            base_url=self._base_url,
            default_headers=combined,
            timeout=float(self._client.timeout.connect),
        )

    def get_market_signal(
        self,
        symbol: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Retrieve the latest trading signal for a symbol.

        Method: GET /api/v1/signals/{symbol}
        Scope: signals:read
        Cache: public; max-age=15s
        Idempotency: optional
        """
        request_headers = dict(self._default_headers)
        if headers:
            request_headers.update(headers)
        request_kwargs: dict[str, Any] = {"headers": request_headers}
        response = self._client.request(
            "GET",
            f"{API_V1_BASE}/signals/{symbol}",
            **request_kwargs,
        )
        response.raise_for_status()
        return response

    def create_prediction(
        self,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Submit feature vectors and request an inference run.

        Method: POST /api/v1/predictions
        Scope: predictions:write
        Cache: no-store; max-age=0s
        Idempotency: required via X-Idempotency-Key ttl=86400s
        """
        request_headers = dict(self._default_headers)
        if headers:
            request_headers.update(headers)
        request_kwargs: dict[str, Any] = {"headers": request_headers}
        if payload is not None:
            request_kwargs["json"] = payload
        response = self._client.request(
            "POST",
            f"{API_V1_BASE}/predictions",
            **request_kwargs,
        )
        response.raise_for_status()
        return response
