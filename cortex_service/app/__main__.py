"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import ipaddress
import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("CORTEX_SERVICE_HOST", "127.0.0.1")
    try:
        ip = ipaddress.ip_address(host)
        is_public = not ip.is_loopback
    except ValueError:
        is_public = host not in {"localhost", "127.0.0.1", "::1"}
    if is_public:
        import logging

        logging.getLogger(__name__).warning(
            "Cortex service binding to non-loopback interface '%s'; use a reverse proxy for external access.",
            host,
        )
    uvicorn.run(
        "cortex_service.app.api:create_app",
        host=host,
        port=int(os.getenv("CORTEX_SERVICE_PORT", "8001")),
        factory=True,
    )
