"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "cortex_service.app.api:create_app", host="0.0.0.0", port=8001, factory=True
    )
