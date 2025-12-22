"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import ipaddress
import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("CORTEX_SERVICE_HOST", "127.0.0.1")
    if ipaddress.ip_address(host).is_unspecified:
        import logging

        logging.getLogger(__name__).warning(
            "Cortex service binding to 0.0.0.0; use a reverse proxy for external access."
        )
    uvicorn.run(
        "cortex_service.app.api:create_app",
        host=host,
        port=int(os.getenv("CORTEX_SERVICE_PORT", "8001")),
        factory=True,
    )
