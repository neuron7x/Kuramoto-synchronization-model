"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "cortex_service.app.api:create_app",
        host=os.getenv("CORTEX_SERVICE_HOST", "127.0.0.1"),
        port=int(os.getenv("CORTEX_SERVICE_PORT", "8001")),
        factory=True,
    )
