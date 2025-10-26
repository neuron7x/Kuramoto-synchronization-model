"""Utilities for exposing authenticated debug routes in FastAPI apps."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from core.utils.debug import VariableInspector

__all__ = ["DebugVariablesResponse", "install_debug_routes"]


class DebugVariablesResponse(BaseModel):
    """Structured payload returned by the debug variables endpoint."""

    variables: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def install_debug_routes(
    app: FastAPI,
    *,
    inspector: VariableInspector,
    enabled: bool,
    identity_dependency: Callable[..., Any] | None = None,
) -> None:
    """Attach the ``/debug/variables`` endpoint when *enabled* is True."""

    if not enabled:
        return

    router = APIRouter(prefix="/debug", tags=["debug"])

    if identity_dependency is not None:
        dependency = identity_dependency

        @router.get("/variables", response_model=DebugVariablesResponse)
        async def read_variables(
            _: Any = Depends(dependency),
        ) -> DebugVariablesResponse:
            snapshot = await inspector.snapshot()
            return DebugVariablesResponse(variables=snapshot)

    else:

        @router.get("/variables", response_model=DebugVariablesResponse)
        async def read_variables() -> DebugVariablesResponse:
            snapshot = await inspector.snapshot()
            return DebugVariablesResponse(variables=snapshot)

    app.include_router(router)
