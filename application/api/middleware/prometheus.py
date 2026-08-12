# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FastAPI middleware emitting Prometheus metrics for HTTP requests."""

from __future__ import annotations

import logging
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.utils.metrics import MetricsCollector, get_metrics_collector

LOGGER = logging.getLogger("geosync.api.metrics")


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Record request/response metrics compatible with Prometheus."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        collector: MetricsCollector | None = None,
    ) -> None:
        super().__init__(app)
        self._collector = collector or get_metrics_collector()

    async def dispatch(self, request: Request, call_next):
        if not self._collector.enabled:
            return await call_next(request)

        route = self._resolve_route_template(request)
        method = request.method.upper()

        self._collector.track_api_in_flight(route, method, 1.0)
        start = perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - defensive guard
            duration = perf_counter() - start
            status_code = getattr(exc, "status_code", 500)
            if status_code >= 500:
                LOGGER.exception(
                    "Unhandled exception while processing request with status %s",
                    status_code,
                )
            else:
                LOGGER.info(
                    "Handled HTTP exception with status %s while processing request",
                    status_code,
                )
            self._collector.observe_api_request(route, method, status_code, duration)
            raise
        else:
            duration = perf_counter() - start
            self._collector.observe_api_request(
                route, method, getattr(response, "status_code", 200), duration
            )
            return response
        finally:
            self._collector.track_api_in_flight(route, method, -1.0)

    @staticmethod
    def _resolve_route_template(request: Request) -> str:
        """Best-effort resolution of the route template for labelling."""

        scope_route = request.scope.get("route")
        if scope_route is not None:
            for attr in ("path", "path_format", "path_regex"):
                template = getattr(scope_route, attr, None)
                if template:
                    return str(template)

        scope_path = request.scope.get("path")
        if scope_path:
            return str(scope_path)

        try:
            return str(request.url.path)
        except Exception:  # pragma: no cover - defensive
            return "unknown"


__all__ = ["PrometheusMetricsMiddleware"]
