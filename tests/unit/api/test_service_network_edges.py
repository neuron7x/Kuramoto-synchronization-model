# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Network identity edge tests for API service helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from starlette.requests import Request

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")

from application.api.service import _peer_is_trusted_proxy, _resolve_ip


def _request(peer: str | None, headers: Mapping[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
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
    assert (
        _peer_is_trusted_proxy("203.0.113.7", {"bad-cidr", "10.0.0.0/8"})
        is False
    )


def test_resolve_ip_ignores_forwarded_headers_from_untrusted_peer() -> None:
    request = _request(
        "198.51.100.44",
        {
            "x-forwarded-for": "203.0.113.9, 10.0.0.5",
            "x-real-ip": "203.0.113.10",
        },
    )

    assert (
        _resolve_ip(request, trusted_proxies={"10.0.0.0/8"})
        == "198.51.100.44"
    )


def test_resolve_ip_prefers_first_forwarded_for_from_trusted_proxy() -> None:
    request = _request(
        "10.0.0.5",
        {"x-forwarded-for": "203.0.113.9, 198.51.100.1"},
    )

    assert _resolve_ip(request, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.9"


def test_resolve_ip_falls_back_to_real_ip_then_unknown() -> None:
    proxied = _request("10.0.0.5", {"x-real-ip": "203.0.113.42"})
    missing_peer = _request(None)

    assert _resolve_ip(proxied, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.42"
    assert _resolve_ip(missing_peer, trusted_proxies={"10.0.0.0/8"}) == "unknown"


def test_resolve_ip_skips_empty_forwarded_segments_without_raising() -> None:
    """A blank or whitespace-only forwarded segment must not raise IndexError.

    ``",203.0.113.9"`` and ``"   "`` both previously indexed ``[0]`` on an empty
    ``split()`` result, surfacing as an unhandled 500 through the rate-limit
    precheck. The leading empty hop is now skipped and a blank header falls back
    to the direct peer.
    """

    leading_empty = _request("10.0.0.5", {"x-forwarded-for": ",203.0.113.9"})
    blank = _request("10.0.0.5", {"x-forwarded-for": "   ", "x-real-ip": "   "})

    assert _resolve_ip(leading_empty, trusted_proxies={"10.0.0.0/8"}) == "203.0.113.9"
    assert _resolve_ip(blank, trusted_proxies={"10.0.0.0/8"}) == "10.0.0.5"
