"""Auto-generated HTTPX client for TradePulse Public API."""

from __future__ import annotations

from typing import Any

import httpx


class TradePulsePublicAPI:
    """Client generated from schemas. Do not edit manually."""

    def __init__(self, base_url: str = "https://api.tradepulse.dev", client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url)

    def close(self) -> None:
        self._client.close()

    def get_health(
        self,
        **request_kwargs: Any,
    ) -> httpx.Response:
        """Health probe"""

        url = f"{self._base_url}/health"
        response = self._client.request(
            "GET",
            url,
            params={
            },
            json=None,
            **request_kwargs,
        )
        response.raise_for_status()
        return response

    def create_signal(
        self,
        *,
        dry_run: bool | None,
        payload: dict[str, Any],
        **request_kwargs: Any,
    ) -> httpx.Response:
        """Create signal"""

        url = f"{self._base_url}/signals"
        response = self._client.request(
            "POST",
            url,
            params={
                "dry_run": dry_run,
            },
            json=payload,
            **request_kwargs,
        )
        response.raise_for_status()
        return response

__all__ = ["TradePulsePublicAPI"]
