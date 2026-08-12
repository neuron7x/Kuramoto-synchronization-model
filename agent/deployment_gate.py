"""Deployment gate with hard no-override policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.self_audit import SelfAuditingModule


@dataclass(frozen=True)
class DeploymentCertificate:
    timestamp_utc: str
    checks_passed: int
    code_hash: str


class DeploymentDenied(RuntimeError):
    pass


class DeploymentGate:
    def __init__(self) -> None:
        self._auditor = SelfAuditingModule()

    def can_deploy(self) -> bool:
        cert = self._auditor.compliance_certificate
        return bool(
            cert["determinism_verified"] and cert["invariants_checked"] == cert["invariants_passed"]
        )

    def deploy(self) -> DeploymentCertificate:
        if not self.can_deploy():
            raise DeploymentDenied("Safety checks failed")
        payload = json.dumps(self._auditor.compliance_certificate, sort_keys=True)
        return DeploymentCertificate(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            checks_passed=self._auditor.compliance_certificate["invariants_passed"],
            code_hash=hashlib.sha256(payload.encode()).hexdigest(),
        )
