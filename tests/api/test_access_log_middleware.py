from __future__ import annotations

import json

from fastapi import FastAPI
from starlette.testclient import TestClient

from application.api.middleware import AccessLogMiddleware
from observability.audit.trail import AuditTrail


def test_access_log_middleware_records_request(tmp_path) -> None:
    app = FastAPI()
    trail_path = tmp_path / "access.jsonl"
    audit_trail = AuditTrail(trail_path)

    app.add_middleware(
        AccessLogMiddleware,
        audit_trail=audit_trail,
        service="test_service",
        capture_headers=("x-request-id", "traceparent"),
    )

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/ping", headers={"x-request-id": "req-123", "User-Agent": "pytest"}
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"

    payloads = [
        json.loads(line)
        for line in trail_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["event"] == "http.access"
    assert payload["severity"] == "info"
    assert payload["request_id"] == "req-123"
    details = payload["details"]
    assert details["service"] == "test_service"
    assert details["path"] == "/ping"
    assert details["status_code"] == 200
    assert details["correlation_headers"]["x-request-id"] == "req-123"
    assert details["user_agent"] == "pytest"
    assert details["duration_ms"] >= 0
