# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Network identity edge tests for the system-access rate-limit key resolver.

Regression coverage for the per-IP rate-limit bypass and the malformed-header
500 in ``application.api.system_access._resolve_ip``. The pre-auth throttle keys
its bucket on ``_resolve_ip``; if a client could spoof ``X-Forwarded-For`` from
an untrusted peer, every request would mint a fresh bucket and the throttle
would never trip. An empty/whitespace forwarded segment must also not raise.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from starlette.requests import Request

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")

from application.api.system_access import _peer_is_trusted_proxy, _resolve_ip


def _request(peer: str | None, headers: Mapping[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/status",
        "headers": raw_headers,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    if peer is not None:
        scope["client"] = (peer, 44321)
    return Request(scope)


def test_peer_trust_accepts_exact_ip_and_cidr_entries() -> None:
    assert _peer_is_trusted_proxy("10.10.1.4", {"10.10.1.0/24"}) is True
    assert _peer_is_trusted_proxy("192.0.2.10", {"192.0.2.10"}) is True


def test_peer_trust_rejects_invalid_peer_and_ignores_invalid_proxy_entries() -> None:
    assert _peer_is_trusted_proxy(None, {"10.0.0.0/8"}) is False
    assert _peer_is_trusted_proxy("not-an-ip", {"10.0.0.0/8"}) is False
    assert _peer_is_trusted_proxy("203.0.113.7", {"bad-cidr", "10.0.0.0/8"}) is False


def test_forwarded_header_from_untrusted_peer_is_ignored() -> None:
    """(a) An untrusted client cannot key its bucket by a spoofed header."""

    request = _request(
        "198.51.100.44",
        {
            "x-forwarded-for": "203.0.113.9, 10.0.0.5",
            "x-real-ip": "203.0.113.10",
        },
    )

    # No trusted proxies configured (production default) -> headers ignored.
    assert _resolve_ip(request) == "198.51.100.44"
    # Explicit trusted set that does NOT include the direct peer -> ignored.
    assert _resolve_ip(request, trusted_proxies={"10.0.0.0/8"}) == "198.51.100.44"


def test_untrusted_peer_bucket_is_stable_across_rotating_spoofed_headers() -> None:
    """(a) Rotating the spoofed header per request yields ONE stable bucket key.

    This is the anti-bypass invariant: the rate-limit precheck keys on
    ``_resolve_ip``; a fresh key per request would defeat the throttle.
    """

    keys = {
        _resolve_ip(_request("198.51.100.44", {"x-forwarded-for": f"203.0.113.{i}"}))
        for i in range(1, 6)
    }
    assert keys == {"198.51.100.44"}


def test_forwarded_header_from_trusted_proxy_is_honored() -> None:
    """(b) A trusted proxy's first forwarded hop becomes the client identity."""

    request = _request(
        "10.0.0.5",
        {"x-forwarded-for": "203.0.113.9, 198.51.100.1"},
    )

    assert _resolve_ip(request, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.9"


def test_trusted_proxy_falls_back_to_real_ip_then_direct_peer() -> None:
    """(b) X-Real-IP is honored for a trusted proxy; missing headers use peer."""

    real_ip = _request("10.0.0.5", {"x-real-ip": "203.0.113.42"})
    no_headers = _request("10.0.0.5")

    assert _resolve_ip(real_ip, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.42"
    assert _resolve_ip(no_headers, trusted_proxies={"10.0.0.0/8"}) == "10.0.0.5"


def test_empty_or_whitespace_forwarded_header_does_not_raise() -> None:
    """(c) Malformed forwarded segments must not raise IndexError (no 500)."""

    # Blank / whitespace-only header value.
    blank = _request("198.51.100.44", {"x-forwarded-for": "   "})
    # Leading empty segment before a real value.
    leading_empty = _request("10.0.0.5", {"x-forwarded-for": ",203.0.113.9"})
    # Whitespace-only real-ip on a trusted proxy.
    blank_real = _request("10.0.0.5", {"x-real-ip": "   "})

    # Untrusted peer: header ignored, no raise, direct peer returned.
    assert _resolve_ip(blank) == "198.51.100.44"
    # Trusted proxy: blank leading segment skipped, first valid hop returned.
    assert _resolve_ip(leading_empty, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.9"
    # Trusted proxy with only a blank real-ip: falls back to the direct peer.
    assert _resolve_ip(blank_real, trusted_proxies={"10.0.0.0/8"}) == "10.0.0.5"


def test_missing_client_returns_unknown() -> None:
    assert _resolve_ip(_request(None)) == "unknown"
