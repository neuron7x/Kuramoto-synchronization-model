"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    import os
    # Security: Allow binding configuration via env var, default to localhost
    host = os.getenv("CORTEX_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("CORTEX_SERVICE_PORT", "8001"))
    uvicorn.run(
        "cortex_service.app.api:create_app", host=host, port=port, factory=True
    )
