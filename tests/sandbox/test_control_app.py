# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from fastapi.testclient import TestClient

from sandbox.control.app import create_app
from sandbox.control.state import ControlState
from sandbox.models import AuditEvent
from sandbox.settings import ControlSettings


def test_control_app_manages_kill_switch_and_audit_feed() -> None:
    settings = ControlSettings()
    state = ControlState(health_targets={})
    app = create_app(settings=settings, state=state)
    client = TestClient(app)

    engage_response = client.post("/kill-switch/engage", json={"reason": "demo"})
    assert engage_response.status_code == 200
    assert engage_response.json()["engaged"] is True

    state.ingest_audit_event(
        AuditEvent(
            source="test",
            category="demo",
            message="event",
            created_at=state.state().engaged_at,
            payload={},
        )
    )

    feed_response = client.get("/audit/feed")
    assert feed_response.status_code == 200
    assert feed_response.json()["events"]

    reset_response = client.post("/kill-switch/reset")
    assert reset_response.status_code == 200
    assert reset_response.json()["engaged"] is False
