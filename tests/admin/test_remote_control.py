from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from execution.risk import RiskLimits, RiskManager
from src.admin.remote_control import (
    AdminIdentity,
    AdminRateLimiter,
    AdminRateLimiterSnapshot,
    _normalize_ip,
    _resolve_ip,
    create_remote_control_router,
)
from src.audit.audit_logger import AuditLogger, AuditRecord
from src.risk.risk_manager import KillSwitchState, RiskManagerFacade
from src.security import AccessController, AccessPolicy

RemoteControlBundle = tuple[TestClient, RiskManager, list[AuditRecord], AuditLogger]


@pytest.fixture()
def remote_control_fixture() -> Iterator[RemoteControlBundle]:
    records: list[AuditRecord] = []
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=records.append,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    risk_manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(risk_manager)

    async def identity_dependency(request: Request) -> AdminIdentity:
        header_subject = request.headers.get("X-Test-Admin-Subject")
        subject = header_subject or "unit-admin"
        return AdminIdentity(subject=subject)

    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            facade,
            audit_logger,
            identity_dependency=identity_dependency,
        )
    )
    client = TestClient(app)
    try:
        yield client, risk_manager, records, audit_logger
    finally:
        client.close()


def test_kill_switch_endpoint_engages_kill_switch(
    remote_control_fixture: RemoteControlBundle,
) -> None:
    client, risk_manager, records, audit_logger = remote_control_fixture
    response = client.post(
        "/admin/kill-switch",
        headers={"X-Test-Admin-Subject": "root"},
        json={"reason": "manual intervention"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kill_switch_engaged"] is True
    assert body["already_engaged"] is False
    assert risk_manager.kill_switch.is_triggered()
    assert len(records) == 1
    record = records[0]
    assert record.event_type == "kill_switch_engaged"
    assert record.details["reason"] == "manual intervention"
    assert record.actor == "root"
    assert audit_logger.verify(record)


def test_kill_switch_endpoint_uses_default_subject(
    remote_control_fixture: RemoteControlBundle,
) -> None:
    client, risk_manager, records, audit_logger = remote_control_fixture
    response = client.post(
        "/admin/kill-switch",
        json={"reason": "manual intervention"},
    )
    assert response.status_code == 200
    assert risk_manager.kill_switch.is_triggered()
    assert len(records) == 1
    record = records[0]
    assert record.actor == "unit-admin"
    assert audit_logger.verify(record)


def test_kill_switch_endpoint_reflects_facade_state() -> None:
    class StubFacade:
        def __init__(self) -> None:
            self.reasons: list[str] = []

        def engage_kill_switch(
            self, reason: str, *, actor: str = "system", roles: tuple[str, ...] = ()
        ) -> KillSwitchState:
            self.reasons.append(reason)
            return KillSwitchState(engaged=False, reason=reason, already_engaged=False)

    records: list[AuditRecord] = []
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=records.append,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    facade = StubFacade()

    async def identity_dependency(request: Request) -> AdminIdentity:
        subject = request.headers.get("X-Test-Admin-Subject", "unit-admin")
        return AdminIdentity(subject=subject)

    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            facade, audit_logger, identity_dependency=identity_dependency
        )
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/admin/kill-switch",
            headers={"X-Test-Admin-Subject": "ops"},
            json={"reason": "scheduled maintenance"},
        )
    finally:
        client.close()
    assert response.status_code == 200
    body = response.json()
    assert body["kill_switch_engaged"] is False
    assert body["reason"] == "scheduled maintenance"
    assert facade.reasons == ["scheduled maintenance"]


def test_kill_switch_rejects_whitespace_reason(
    remote_control_fixture: RemoteControlBundle,
) -> None:
    client, risk_manager, records, _ = remote_control_fixture
    response = client.post(
        "/admin/kill-switch",
        json={"reason": "   \t\n"},
    )
    assert response.status_code == 422
    assert not risk_manager.kill_switch.is_triggered()
    assert records == []


def test_kill_switch_reaffirmation_is_audited(
    remote_control_fixture: RemoteControlBundle,
) -> None:
    client, _, records, _ = remote_control_fixture
    headers = {"X-Test-Admin-Subject": "auditor"}
    first = client.post(
        "/admin/kill-switch", headers=headers, json={"reason": "initial"}
    )
    assert first.status_code == 200
    second = client.post(
        "/admin/kill-switch", headers=headers, json={"reason": "still engaged"}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["already_engaged"] is True
    assert len(records) == 2
    reaffirmation = records[1]
    assert reaffirmation.event_type == "kill_switch_reaffirmed"
    assert reaffirmation.details["already_engaged"] is True
    assert reaffirmation.details["reason"] == "still engaged"


def test_admin_rate_limiter_blocks_excessive_attempts() -> None:
    records: list[AuditRecord] = []
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=records.append,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    risk_manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(risk_manager)

    async def identity_dependency(_: Request) -> AdminIdentity:
        return AdminIdentity(subject="unit-admin")

    limiter = AdminRateLimiter(max_attempts=1, interval_seconds=60.0)
    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            facade,
            audit_logger,
            identity_dependency=identity_dependency,
            rate_limiter=limiter,
        )
    )
    client = TestClient(app)
    try:
        first = client.post(
            "/admin/kill-switch",
            json={"reason": "initial"},
        )
        assert first.status_code == 200

        second = client.post(
            "/admin/kill-switch",
            json={"reason": "repeat"},
        )
    finally:
        client.close()
    assert second.status_code == 429
    assert len(records) == 1


def test_identity_dependency_errors_are_propagated() -> None:
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=lambda record: None,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    risk_manager = RiskManagerFacade(RiskManager(RiskLimits()))

    async def failing_identity(_: Request) -> AdminIdentity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid cert"
        )

    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            risk_manager,
            audit_logger,
            identity_dependency=failing_identity,
        )
    )
    client = TestClient(app)
    response = client.post("/admin/kill-switch", json={"reason": "manual"})
    assert response.status_code == 401


def test_permission_dependency_is_respected() -> None:
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=lambda record: None,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    risk_manager = RiskManagerFacade(RiskManager(RiskLimits()))

    async def identity(_: Request) -> AdminIdentity:
        return AdminIdentity(subject="unit-admin")

    async def forbidden(_: Request) -> AdminIdentity:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="denied")

    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            risk_manager,
            audit_logger,
            identity_dependency=identity,
            execute_permission=forbidden,
        )
    )
    client = TestClient(app)
    response = client.post("/admin/kill-switch", json={"reason": "manual"})
    assert response.status_code == 403


def test_kill_switch_endpoint_requires_access_policy(tmp_path: Path) -> None:
    records: list[AuditRecord] = []
    audit_logger = AuditLogger(
        secret="unit-test-secret",
        sink=records.append,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "subjects": {"system": {"permissions": ["reset_kill_switch"]}},
                "roles": {"observer": {"permissions": ["read_kill_switch_state"]}},
            }
        ),
        encoding="utf-8",
    )
    controller = AccessController(AccessPolicy.load(policy_path))
    risk_manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(risk_manager, access_controller=controller)

    async def identity(_: Request) -> AdminIdentity:
        return AdminIdentity(subject="alice", roles=("observer",))

    app = FastAPI()
    app.include_router(
        create_remote_control_router(
            facade,
            audit_logger,
            identity_dependency=identity,
        )
    )
    client = TestClient(app)
    try:
        response = client.post("/admin/kill-switch", json={"reason": "manual"})
    finally:
        client.close()

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert risk_manager.kill_switch.is_triggered() is False
    assert records == []


def _request_from_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/kill-switch",
        "headers": [
            (key.lower().encode("utf-8"), value.encode("utf-8"))
            for key, value in headers.items()
        ],
        "client": ("10.0.0.99", 443),
    }
    return StarletteRequest(scope)


def test_resolve_ip_prefers_forwarded_header() -> None:
    request = _request_from_headers(
        {
            "X-Forwarded-For": " 203.0.113.7 , 10.0.0.1",
            "X-Real-IP": "198.51.100.5",
        }
    )
    assert _resolve_ip(request) == "203.0.113.7"


def test_normalize_ip_strips_port_and_zone() -> None:
    assert _normalize_ip("203.0.113.9 malicious") == "203.0.113.9"
    assert _normalize_ip("[2001:db8::1]") == "2001:db8::1"
    assert _normalize_ip("[2001:db8::1]:443") is None
    assert _normalize_ip("fe80::1%eth0") == "fe80::1"
    assert _normalize_ip("invalid ip") is None


@pytest.mark.asyncio
async def test_admin_rate_limiter_snapshot_reports_saturation() -> None:
    limiter = AdminRateLimiter(max_attempts=2, interval_seconds=60.0)
    await limiter.check("alpha")
    await limiter.check("alpha")

    # Inject a stale bucket to ensure cleanup logic runs
    limiter._records["stale"] = deque([0.0])  # type: ignore[attr-defined]

    snapshot: AdminRateLimiterSnapshot = await limiter.snapshot()
    assert snapshot.tracked_identifiers == 1
    assert snapshot.max_utilization == pytest.approx(1.0)
    assert snapshot.saturated_identifiers == ["alpha"]
