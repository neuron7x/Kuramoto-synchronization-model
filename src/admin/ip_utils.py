"""Utilities for safely extracting client IP addresses from ASGI requests."""

from __future__ import annotations

import ipaddress
from typing import Iterable

from fastapi import Request

__all__ = ["normalize_ip_header", "resolve_request_ip"]


def normalize_ip_header(raw: str | None) -> str | None:
    """Return a validated IP address extracted from an HTTP header value.

    Header values may include surrounding whitespace, multiple comma-separated
    addresses (``X-Forwarded-For``), zone identifiers for IPv6 addresses, or
    other attacker-controlled decorations.  The function normalises the first
    token that represents a syntactically valid IP address and rejects values
    that fail validation to prevent header injection attacks.
    """

    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    # Split on whitespace to mitigate attempts such as "1.2.3.4 malicious".
    candidate = candidate.split()[0]

    # Remove square brackets that may wrap IPv6 literals.
    candidate = candidate.strip("[]")

    # Drop a zone identifier (e.g. "fe80::1%eth0") as ``ipaddress`` cannot
    # parse scoped addresses directly.
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]

    # Handle IPv4 addresses that include a port component.
    if candidate.count(":") == 1 and "." in candidate:
        host, _, port = candidate.rpartition(":")
        if port.isdigit():
            candidate = host

    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _iter_header_values(raw: str | None) -> Iterable[str]:
    if raw is None:
        return ()
    return (part.strip() for part in raw.split(","))


def resolve_request_ip(request: Request) -> str:
    """Determine the client IP address for *request* in a defensive manner.

    The function honours standard proxy headers and falls back to the socket
    address associated with the request.  Each candidate is normalised via
    :func:`normalize_ip_header` to ensure untrusted data cannot reach audit
    logs or rate limiting components in an unsafe form.
    """

    for candidate in _iter_header_values(request.headers.get("X-Forwarded-For")):
        normalised = normalize_ip_header(candidate)
        if normalised is not None:
            return normalised

    normalised = normalize_ip_header(request.headers.get("X-Real-IP"))
    if normalised is not None:
        return normalised

    if request.client is not None and request.client.host:
        fallback = normalize_ip_header(request.client.host)
        if fallback is not None:
            return fallback
        return request.client.host

    return "unknown"
