"""Dual approval infrastructure for systemic thermodynamic actions."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict

import jwt

_DUAL_APPROVAL_MODULES = {"thermo_controller"}


@dataclass(slots=True)
class ApprovalRecord:
    timestamp: float
    action_id: str


class DualApprovalManager:
    def __init__(
        self,
        *,
        secret: str | None = None,
        algorithm: str = "HS256",
        cooldown_seconds: float = 3600.0,
    ) -> None:
        self.secret = secret or os.getenv("THERMO_DUAL_SECRET")
        self.algorithm = algorithm
        self.cooldown_seconds = cooldown_seconds
        self._approvals: Dict[str, ApprovalRecord] = {}

    def validate(self, *, action_id: str, token: str) -> None:
        if not self.secret:
            raise ValueError("dual_approval_secret_missing")
        if not token:
            raise ValueError("dual_approval_token_missing")

        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.exceptions.PyJWTError as exc:
            raise ValueError("dual_approval_token_invalid") from exc
        payload_action = str(payload.get("action_id", ""))
        if payload_action != action_id:
            raise ValueError("dual_approval_action_mismatch")

        now = time.time()
        record = self._approvals.get(action_id)
        if record and now - record.timestamp < self.cooldown_seconds:
            raise ValueError("dual_approval_cooldown")

        self._approvals[action_id] = ApprovalRecord(timestamp=now, action_id=action_id)

    def issue_service_token(self, *, action_id: str) -> str:
        if not self.secret:
            raise ValueError("dual_approval_secret_missing")
        payload = {"action_id": action_id, "iat": int(time.time())}
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)


def requires_dual_approval(module_name: str) -> bool:
    return module_name in _DUAL_APPROVAL_MODULES


__all__ = ["DualApprovalManager", "requires_dual_approval", "ApprovalRecord"]
