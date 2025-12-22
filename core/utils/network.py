from __future__ import annotations

import ipaddress


def is_public_bind(host: str) -> bool:
    """Return True if host is a non-loopback, non-private bind (including 0.0.0.0/::)."""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_unspecified:
            return True
        if ip.is_loopback or ip.is_private:
            return False
        return True
    except ValueError:
        return host not in {"localhost", "127.0.0.1", "::1"}
