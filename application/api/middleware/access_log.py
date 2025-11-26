"""Middleware that records HTTP access events for audit purposes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Iterable, Mapping, Sequence
from uuid import uuid4

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from observability.audit.trail import (
    AuditTrail,
    AuditTrailError,
    get_access_audit_trail,
)


def _resolve_ip_address(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        candidate = real_ip.strip()
        if candidate:
            return candidate
    if request.client and request.client.host:
        return request.client.host
    return None


def _normalise_role(value: str) -> str | None:
    candidate = value.strip().lower()
    return candidate or None


def _extract_roles(claims: Mapping[str, object]) -> tuple[str, ...]:
    roles: set[str] = set()

    def _ingest(candidate: object) -> None:
        if isinstance(candidate, str):
            for fragment in candidate.replace(",", " ").split():
                normalised = _normalise_role(fragment)
                if normalised:
                    roles.add(normalised)
        elif isinstance(candidate, Sequence):
            for item in candidate:
                if isinstance(item, str):
                    normalised = _normalise_role(item)
                    if normalised:
                        roles.add(normalised)

    for key in ("roles", "permissions", "scope"):
        entry = claims.get(key)
        if entry is not None:
            _ingest(entry)

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, Mapping):
        _ingest(realm_access.get("roles"))

    resource_access = claims.get("resource_access")
    if isinstance(resource_access, Mapping):
        for entry in resource_access.values():
            if isinstance(entry, Mapping):
                _ingest(entry.get("roles"))

    return tuple(sorted(roles))


def _resolve_identity(request: Request) -> tuple[str | None, tuple[str, ...]]:
    claims = getattr(request.state, "token_claims", None)
    if isinstance(claims, Mapping):
        subject = claims.get("sub")
        if not isinstance(subject, str):
            subject = None
        roles = _extract_roles(claims)
        return subject, roles
    return None, ()


def _truncate(value: str, *, limit: int = 1024) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit structured access logs for every HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        audit_trail: AuditTrail | None = None,
        logger: logging.Logger | None = None,
        service: str | None = None,
        capture_headers: Iterable[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._audit_trail = audit_trail or get_access_audit_trail()
        self._logger = logger or logging.getLogger("tradepulse.audit.access")
        self._service = service
        headers = capture_headers or ("x-request-id", "x-correlation-id")
        self._capture_headers = tuple(
            {header.lower(): header for header in headers}.values()
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = None
        correlation_headers: dict[str, str] = {}
        for header in self._capture_headers:
            value = request.headers.get(header)
            if not value:
                continue
            correlation_headers[header] = value
            if request_id is None and header in {"x-request-id", "x-correlation-id"}:
                request_id = value

        if request_id is None:
            request_id = uuid4().hex
        request.state.request_id = request_id

        ip_address = _resolve_ip_address(request)
        subject, roles = _resolve_identity(request)
        mtls_present = bool(getattr(request.state, "client_certificate", None))

        start = perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except HTTPException as exc:
            status_code = exc.status_code
            raise
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 3)
            details: dict[str, object] = {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "http_version": request.scope.get("http_version", "1.1"),
            }
            if self._service:
                details["service"] = self._service
            if request.url.query:
                details["query"] = _truncate(request.url.query, limit=512)
            if ip_address:
                details["remote_ip"] = ip_address
            if roles:
                details["roles"] = roles
            if mtls_present:
                details["mutual_tls"] = True
            if request.client and request.client.port:
                details["remote_port"] = request.client.port
            user_agent = request.headers.get("user-agent")
            if user_agent:
                details["user_agent"] = _truncate(user_agent, limit=512)
            host = request.headers.get("host")
            if host:
                details["host"] = host
            if correlation_headers:
                details["correlation_headers"] = correlation_headers

            severity = "info"
            if 400 <= status_code < 500:
                severity = "warning"
            elif status_code >= 500:
                severity = "error"

            if self._audit_trail is not None:
                try:
                    payload = self._audit_trail.record(
                        "http.access",
                        severity=severity,
                        subject=subject,
                        ip_address=ip_address,
                        request_id=request_id,
                        details=details,
                    )
                except AuditTrailError:
                    self._logger.error(
                        "access.audit.write_failed",
                        extra={
                            "event": "http.access",
                            "severity": severity,
                            "request_id": request_id,
                        },
                        exc_info=True,
                    )
                    payload = None
            else:
                payload = None

            if payload is None:
                payload = {
                    "event": "http.access",
                    "severity": severity,
                    "subject": subject,
                    "ip_address": ip_address,
                    "request_id": request_id,
                    "details": details,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            if severity == "error":
                log_level = logging.ERROR
            elif severity == "warning":
                log_level = logging.WARNING
            else:
                log_level = logging.INFO

            self._logger.log(log_level, "http.access", extra={"audit": payload})

            if response is not None:
                response.headers.setdefault("x-request-id", request_id)

            # Exceptions are re-raised automatically after the finally block completes.
