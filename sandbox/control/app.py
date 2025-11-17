"""FastAPI application orchestrating sandbox control operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from ..models import AuditEvent, KillSwitchState
from ..settings import ControlSettings, control_settings
from .state import ControlState


class KillSwitchRequest(BaseModel):
    reason: str


def create_state(settings: ControlSettings) -> ControlState:
    return ControlState(
        health_targets={name: str(url) for name, url in settings.health_targets.items()}
    )


def create_app(
    settings: ControlSettings | None = None, state: ControlState | None = None
) -> FastAPI:
    config = settings or control_settings()
    control_state = state or create_state(config)

    app = FastAPI(title="TradePulse Sandbox Control API", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        results = await control_state.health()
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc),
            "services": results,
        }

    @app.get("/kill-switch")
    async def kill_switch_state() -> KillSwitchState:
        return control_state.state()

    @app.post("/kill-switch/engage")
    async def engage(payload: dict[str, Any] = Body(...)) -> KillSwitchState:
        try:
            request = KillSwitchRequest.model_validate(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors()) from error
        return control_state.engage(request.reason)

    @app.post("/kill-switch/reset")
    async def reset() -> KillSwitchState:
        return control_state.reset()

    @app.post("/audit/events")
    async def audit_event(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
        try:
            event = AuditEvent.model_validate(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors()) from error
        control_state.ingest_audit_event(event)
        return {"status": "accepted"}

    @app.get("/audit/feed")
    async def audit_feed() -> dict[str, Any]:
        events = [event.model_dump() for event in control_state.audit_log().snapshot()]
        return {"events": events}

    return app
