"""Public API surface for TradePulse FastAPI applications."""

from __future__ import annotations

from typing import Any

from .system_access import (
    OrderRequest,
    OrderResponse,
    PositionSnapshot,
    PositionsResponse,
    StatusResponse,
    SystemAccess,
    create_system_app,
)


def create_app(*args: Any, **kwargs: Any):
    """Proxy to :func:`application.api.service.create_app` with lazy import."""

    from .service import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = [
    "create_app",
    "SystemAccess",
    "StatusResponse",
    "PositionsResponse",
    "PositionSnapshot",
    "OrderRequest",
    "OrderResponse",
    "create_system_app",
]
