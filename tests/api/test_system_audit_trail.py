from __future__ import annotations

import json
import logging

from application.api.system_access import SystemAccess
from observability.audit.trail import AuditTrail
from src.admin.remote_control import AdminIdentity


class _DummySystem:
    connector_names: tuple[str, ...] = ()
    risk_manager = object()


def test_system_access_records_audit_event(tmp_path) -> None:
    audit_trail = AuditTrail(tmp_path / "system.jsonl")
    access = SystemAccess(
        _DummySystem(),
        logger=logging.getLogger("test.system_access"),
        notifier=None,
        audit_trail=audit_trail,
    )
    identity = AdminIdentity(subject="audit-user", roles=("foundation:viewer",))

    access._log(
        "info",
        "system.test.event",
        identity=identity,
        secret_token="value",
        action="update",
    )

    payloads = [
        json.loads(line)
        for line in (tmp_path / "system.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["event"] == "system.test.event"
    assert payload["subject"] == "audit-user"
    assert payload["severity"] == "info"
    assert payload["details"]["action"] == "update"
    assert payload["details"]["secret_token"] == "[REDACTED]"
