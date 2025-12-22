"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import os

import uvicorn
from core.utils.network import is_public_bind

if __name__ == "__main__":
    host = os.getenv("CORTEX_SERVICE_HOST", "127.0.0.1")
    if is_public_bind(host):
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
