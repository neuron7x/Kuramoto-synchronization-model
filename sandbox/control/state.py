# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Control plane state management for the sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Mapping

import httpx

from ..audit import InMemoryAuditLog
from ..models import AuditEvent, KillSwitchState


@dataclass
class HealthCheckTarget:
    name: str
    url: str


class ControlState:
    def __init__(self, *, health_targets: Mapping[str, str]) -> None:
        self._kill_switch = KillSwitchState(engaged=False)
        self._lock = Lock()
        self._audit = InMemoryAuditLog()
        self._targets = [HealthCheckTarget(name, url) for name, url in health_targets.items()]

    def engage(self, reason: str) -> KillSwitchState:
        with self._lock:
            self._kill_switch = KillSwitchState(
                engaged=True,
                reason=reason,
                engaged_at=datetime.now(timezone.utc),
            )
            self._audit.emit(
                source="control-api",
                category="kill-switch",
                message="engaged",
                payload={"reason": reason},
            )
            return self._kill_switch

    def reset(self) -> KillSwitchState:
        with self._lock:
            self._kill_switch = KillSwitchState(engaged=False, reason=None, engaged_at=None)
            self._audit.emit(
                source="control-api",
                category="kill-switch",
                message="reset",
                payload={},
            )
            return self._kill_switch

    def state(self) -> KillSwitchState:
        with self._lock:
            return self._kill_switch

    def audit_log(self) -> InMemoryAuditLog:
        return self._audit

    async def health(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=4.0) as client:
            for target in self._targets:
                try:
                    response = await client.get(target.url)
                    response.raise_for_status()
                    results[target.name] = {"status": "ok", "details": response.json()}
                except Exception as error:  # pragma: no cover - network failure path
                    results[target.name] = {"status": "error", "details": str(error)}
        results["control-api"] = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc),
        }
        return results

    def ingest_audit_event(self, event: AuditEvent) -> None:
        self._audit.record(event)
