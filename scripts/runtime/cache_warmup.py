"""Lightweight cache warm-up routine for TradePulse services.

The helper hits a configurable list of HTTP endpoints so upstream caches,
feature stores, and auth tokens are primed before traffic is shifted during
rollouts. It is designed to run both as a standalone CLI and as part of the
Helm hook defined in ``deploy/helm/tradepulse/templates/cache-warmup-job.yaml``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Sequence

import httpx

DEFAULT_ENDPOINTS = (
    "http://127.0.0.1:8001/health",
    "http://127.0.0.1:8001/metrics",
)
DEFAULT_TIMEOUT = 10.0
DEFAULT_CONCURRENCY = 4


@dataclass(slots=True)
class WarmupResult:
    """Result of priming a single endpoint."""

    url: str
    success: bool
    status_code: int | None
    error: str | None = None


async def _fetch(client: httpx.AsyncClient, url: str) -> WarmupResult:
    try:
        response = await client.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network/io errors are logged
        return WarmupResult(url, False, getattr(exc, "response", None) and getattr(exc.response, "status_code", None), str(exc))
    return WarmupResult(url, True, response.status_code)


async def warm_endpoints(endpoints: Sequence[str]) -> list[WarmupResult]:
    """Prime *endpoints* concurrently and return their outcomes."""

    limits = httpx.Limits(max_keepalive_connections=DEFAULT_CONCURRENCY)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        tasks = [_fetch(client, url) for url in endpoints]
        return await asyncio.gather(*tasks)


def _parse_endpoints(raw: str | None) -> Sequence[str]:
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return DEFAULT_ENDPOINTS


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="[cache-warmup] %(levelname)s %(message)s")


def main(args: Sequence[str] | None = None) -> int:
    """Run the cache warm-up routine.

    ``args`` are ignored so the entry point is compatible with the Helm hook
    which only sets environment variables.
    """

    _configure_logging()
    endpoints = _parse_endpoints(os.getenv("TRADEPULSE_CACHE_ENDPOINTS"))
    if not endpoints:
        logging.warning("No endpoints configured; skipping cache warm-up")
        return 0

    logging.info("Priming %s endpoint(s)", len(endpoints))
    results = asyncio.run(warm_endpoints(endpoints))
    failures = [result for result in results if not result.success]

    for result in results:
        if result.success:
            logging.info("%s ✓ status=%s", result.url, result.status_code)
        else:
            logging.error("%s ✗ error=%s status=%s", result.url, result.error, result.status_code)

    if failures:
        logging.error("Cache warm-up failed for %s endpoint(s)", len(failures))
        return 1

    logging.info("Cache warm-up completed successfully")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
