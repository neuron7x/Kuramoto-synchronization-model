"""Dual approval infrastructure for systemic thermodynamic actions.

This module provides enterprise-grade dual approval mechanisms for
safety-critical operations in the TACL system.

Features:
- JWT-based token validation with expiration
- Comprehensive audit logging
- Configurable approval requirements per action type
- Rate limiting and cooldown protection

Aligned with:
- NIST SP 800-53 AC-3 (Access Enforcement)
- ISO 27001 A.9.4.1 (Information Access Restriction)
- SOC 2 CC6.1 (Logical and Physical Access Controls)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

import jwt

logger = logging.getLogger(__name__)


class ApprovalAction(Enum):
    """Predefined actions requiring dual approval."""

    TOPOLOGY_MUTATION = "topology_mutation"
    PROTOCOL_ACTIVATION = "protocol_activation"
    CIRCUIT_BREAKER_OVERRIDE = "circuit_breaker_override"
    KILL_SWITCH_DEACTIVATE = "kill_switch_deactivate"
    CONFIG_CHANGE = "config_change"
    EMERGENCY_OVERRIDE = "emergency_override"


class ApprovalResult(Enum):
    """Result of approval validation."""

    APPROVED = "approved"
    REJECTED_INVALID_TOKEN = "rejected_invalid_token"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_ACTION_MISMATCH = "rejected_action_mismatch"
    REJECTED_COOLDOWN = "rejected_cooldown"
    REJECTED_SECRET_MISSING = "rejected_secret_missing"
    REJECTED_TOKEN_MISSING = "rejected_token_missing"


@dataclass(slots=True)
class ApprovalRecord:
    """Record of a successful approval."""

    timestamp: float
    action_id: str
    approver: Optional[str] = None
    expires_at: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat(),
            "action_id": self.action_id,
            "approver": self.approver,
            "expires_at": self.expires_at,
            "expires_at_iso": (
                datetime.fromtimestamp(self.expires_at, tz=timezone.utc).isoformat()
                if self.expires_at
                else None
            ),
        }


@dataclass
class ApprovalAuditEntry:
    """Audit log entry for approval attempts."""

    timestamp: float
    action_id: str
    result: ApprovalResult
    source: str
    reason: Optional[str] = None
    token_claims: Optional[Dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat(),
            "action_id": self.action_id,
            "result": self.result.value,
            "source": self.source,
            "reason": self.reason,
            "token_claims": self.token_claims,
        }


_DUAL_APPROVAL_MODULES = {"thermo_controller"}


class DualApprovalManager:
    """Enterprise-grade dual approval manager with audit logging.

    This class implements a robust dual approval system for safety-critical
    operations, with full audit trail and configurable policies.

    Attributes:
        secret: JWT signing secret
        algorithm: JWT algorithm (default: HS256)
        cooldown_seconds: Minimum time between approvals for same action
        token_expiration_seconds: Token validity duration
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
        algorithm: str = "HS256",
        cooldown_seconds: float = 3600.0,
        token_expiration_seconds: float = 300.0,
        max_audit_entries: int = 1000,
        audit_log_path: Optional[Path] = None,
    ) -> None:
        """Initialize the dual approval manager.

        Args:
            secret: JWT signing secret (falls back to THERMO_DUAL_SECRET env var)
            algorithm: JWT algorithm to use
            cooldown_seconds: Minimum time between approvals for same action
            token_expiration_seconds: Token validity duration in seconds
            max_audit_entries: Maximum audit log entries to retain in memory
            audit_log_path: Path for persistent audit log file
        """
        self.secret = secret or os.getenv("THERMO_DUAL_SECRET")
        self.algorithm = algorithm
        self.cooldown_seconds = cooldown_seconds
        self.token_expiration_seconds = token_expiration_seconds
        self.max_audit_entries = max_audit_entries
        self.audit_log_path = audit_log_path

        self._approvals: Dict[str, ApprovalRecord] = {}
        self._audit_log: List[ApprovalAuditEntry] = []
        self._callbacks: List[Callable[[str, ApprovalResult], None]] = []

        logger.info(
            "DualApprovalManager initialized with cooldown=%ss, token_expiration=%ss",
            cooldown_seconds,
            token_expiration_seconds,
        )

    def validate(
        self,
        *,
        action_id: str,
        token: str,
        source: str = "unknown",
    ) -> ApprovalResult:
        """Validate a dual approval token.

        Args:
            action_id: Action identifier that requires approval
            token: JWT token for approval
            source: Identifier of the requesting entity

        Returns:
            ApprovalResult indicating success or failure reason

        Raises:
            ValueError: If validation fails (for backwards compatibility)
        """
        now = time.time()

        # Check for missing secret
        if not self.secret:
            result = ApprovalResult.REJECTED_SECRET_MISSING
            self._record_audit(action_id, result, source, "Secret not configured")
            raise ValueError("dual_approval_secret_missing")

        # Check for missing token
        if not token:
            result = ApprovalResult.REJECTED_TOKEN_MISSING
            self._record_audit(action_id, result, source, "Token not provided")
            raise ValueError("dual_approval_token_missing")

        # Decode and validate token
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            result = ApprovalResult.REJECTED_EXPIRED
            self._record_audit(action_id, result, source, "Token expired")
            raise ValueError("dual_approval_token_expired") from None
        except jwt.exceptions.PyJWTError as exc:
            result = ApprovalResult.REJECTED_INVALID_TOKEN
            self._record_audit(action_id, result, source, f"Invalid token: {exc}")
            raise ValueError("dual_approval_token_invalid") from exc

        # Check action_id match
        payload_action = str(payload.get("action_id", ""))
        if payload_action != action_id:
            result = ApprovalResult.REJECTED_ACTION_MISMATCH
            self._record_audit(
                action_id,
                result,
                source,
                f"Action mismatch: expected {action_id}, got {payload_action}",
                token_claims=payload,
            )
            raise ValueError("dual_approval_action_mismatch")

        # Check cooldown
        record = self._approvals.get(action_id)
        if record and now - record.timestamp < self.cooldown_seconds:
            remaining = self.cooldown_seconds - (now - record.timestamp)
            result = ApprovalResult.REJECTED_COOLDOWN
            self._record_audit(
                action_id,
                result,
                source,
                f"Cooldown active: {remaining:.1f}s remaining",
                token_claims=payload,
            )
            raise ValueError("dual_approval_cooldown")

        # Success - record approval
        approver = payload.get("sub") or payload.get("approver")
        exp_claim = payload.get("exp")
        token_expires_at = (
            float(exp_claim)
            if isinstance(exp_claim, (int, float))
            else now + float(self.token_expiration_seconds)
        )
        approval_expires_at = min(token_expires_at, now + self.cooldown_seconds)

        self._approvals[action_id] = ApprovalRecord(
            timestamp=now,
            action_id=action_id,
            approver=approver,
            expires_at=approval_expires_at,
        )

        result = ApprovalResult.APPROVED
        self._record_audit(
            action_id,
            result,
            source,
            "Approval granted",
            token_claims=payload,
        )

        logger.info(
            "Dual approval granted for action '%s' by %s",
            action_id,
            approver or "unknown",
        )

        # Notify callbacks
        self._notify_callbacks(action_id, result)

        return result

    def issue_service_token(
        self,
        *,
        action_id: str,
        subject: str = "service_account",
        additional_claims: Optional[Dict] = None,
    ) -> str:
        """Issue a service token for automated approval.

        Args:
            action_id: Action identifier
            subject: Token subject (approver identity)
            additional_claims: Optional additional JWT claims

        Returns:
            Encoded JWT token

        Raises:
            ValueError: If secret is not configured
        """
        if not self.secret:
            raise ValueError("dual_approval_secret_missing")

        now = int(time.time())
        payload = {
            "action_id": action_id,
            "sub": subject,
            "iat": now,
            "exp": now + int(self.token_expiration_seconds),
            "nbf": now,
        }

        if additional_claims:
            payload.update(additional_claims)

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)

        logger.info(
            "Service token issued for action '%s', expires in %ss",
            action_id,
            self.token_expiration_seconds,
        )

        return token

    def is_action_approved(self, action_id: str) -> bool:
        """Check if an action has a valid, non-expired approval.

        Args:
            action_id: Action identifier to check

        Returns:
            True if action has valid approval
        """
        record = self._approvals.get(action_id)
        if record is None:
            return False

        now = time.time()
        if record.expires_at and now > record.expires_at:
            return False

        return True

    def revoke_approval(
        self, action_id: str, reason: str = "manual_revocation"
    ) -> bool:
        """Revoke an existing approval.

        Args:
            action_id: Action identifier to revoke
            reason: Reason for revocation

        Returns:
            True if approval was revoked, False if not found
        """
        if action_id in self._approvals:
            del self._approvals[action_id]
            logger.info("Approval revoked for action '%s': %s", action_id, reason)
            return True
        return False

    def get_pending_approvals(self) -> List[dict]:
        """Get list of currently valid approvals.

        Returns:
            List of approval record dictionaries
        """
        now = time.time()
        return [
            record.to_dict()
            for record in self._approvals.values()
            if record.expires_at is None or record.expires_at > now
        ]

    def get_audit_log(self, limit: int = 100) -> List[dict]:
        """Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit log entry dictionaries
        """
        return [entry.to_dict() for entry in self._audit_log[-limit:]]

    def register_callback(
        self, callback: Callable[[str, ApprovalResult], None]
    ) -> None:
        """Register a callback for approval events.

        Args:
            callback: Function taking (action_id, result)
        """
        self._callbacks.append(callback)

    def _record_audit(
        self,
        action_id: str,
        result: ApprovalResult,
        source: str,
        reason: Optional[str] = None,
        token_claims: Optional[Dict] = None,
    ) -> None:
        """Record an audit log entry."""
        entry = ApprovalAuditEntry(
            timestamp=time.time(),
            action_id=action_id,
            result=result,
            source=source,
            reason=reason,
            token_claims=token_claims,
        )
        self._audit_log.append(entry)

        # Trim audit log if needed
        if len(self._audit_log) > self.max_audit_entries:
            self._audit_log = self._audit_log[-self.max_audit_entries :]

        # Persist to file if configured
        self._persist_audit_entry(entry)

    def _persist_audit_entry(self, entry: ApprovalAuditEntry) -> None:
        """Persist audit entry to file."""
        if self.audit_log_path is None:
            return

        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except (OSError, IOError) as e:
            logger.warning("Failed to persist audit entry: %s", e)

    def _notify_callbacks(self, action_id: str, result: ApprovalResult) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(action_id, result)
            except Exception as e:
                logger.error("Dual approval callback error: %s", e)


def requires_dual_approval(module_name: str) -> bool:
    """Check if a module requires dual approval for operations.

    Args:
        module_name: Name of the module to check

    Returns:
        True if module requires dual approval
    """
    return module_name in _DUAL_APPROVAL_MODULES


def get_required_approval_actions() -> List[str]:
    """Get list of all action types requiring dual approval.

    Returns:
        List of action type values
    """
    return [action.value for action in ApprovalAction]


__all__ = [
    "DualApprovalManager",
    "ApprovalAction",
    "ApprovalResult",
    "ApprovalRecord",
    "ApprovalAuditEntry",
    "requires_dual_approval",
    "get_required_approval_actions",
]
