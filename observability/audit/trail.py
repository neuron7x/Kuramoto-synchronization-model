"""Audit trail helpers for MiFID II compliant logging."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable, Mapping, MutableSequence

__all__ = [
    "AuditTrail",
    "AuditTrailError",
    "get_access_audit_trail",
    "get_system_audit_trail",
]


class AuditTrailError(RuntimeError):
    """Raised when persisting an audit event fails."""


_SENSITIVE_KEYWORDS = ("token", "secret", "password", "key", "credential")


def _redact_sensitive_values(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deep copy of *payload* with sensitive keys redacted."""

    def _is_sensitive(key: str) -> bool:
        lowered = key.lower()
        return any(keyword in lowered for keyword in _SENSITIVE_KEYWORDS)

    def _transform(value: object, *, parent_key: str | None = None) -> object:
        if isinstance(value, Mapping):
            return {
                inner_key: _transform(inner_value, parent_key=inner_key)
                for inner_key, inner_value in value.items()
            }
        if isinstance(value, list):
            return [_transform(item, parent_key=parent_key) for item in value]
        if parent_key is not None and _is_sensitive(parent_key):
            return "[REDACTED]"
        return value

    return _transform(dict(payload))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditTrail:
    """Append-only JSONL audit trail with optional subscribers."""

    def __init__(
        self,
        path: Path | str,
        *,
        logger: logging.Logger | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._logger = logger or logging.getLogger("tradepulse.audit.trail")
        self._clock = clock or _utc_now
        self._lock = RLock()
        self._listeners: MutableSequence[Callable[[dict[str, object]], None]] = []

    @property
    def path(self) -> Path:
        return self._path

    def register_listener(self, listener: Callable[[dict[str, object]], None]) -> None:
        """Subscribe *listener* to be notified whenever a new event is recorded."""

        with self._lock:
            self._listeners.append(listener)

    def record(
        self,
        event: str,
        *,
        severity: str = "info",
        subject: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Persist a structured audit event."""

        payload: dict[str, object] = {
            "timestamp": self._clock().isoformat(),
            "event": event,
            "severity": severity.lower(),
        }
        if subject:
            payload["subject"] = subject
        if ip_address:
            payload["ip_address"] = ip_address
        if request_id:
            payload["request_id"] = request_id
        if details:
            payload["details"] = _redact_sensitive_values(details)
        try:
            serialized = json.dumps(payload, sort_keys=True)
            with self._lock:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(serialized + "\n")
                listeners: Iterable[Callable[[dict[str, object]], None]] = tuple(
                    self._listeners
                )
        except OSError as exc:  # pragma: no cover - filesystem errors are rare
            self._logger.error(
                "audit.trail.write_failed",
                extra={"event": event, "path": str(self._path)},
                exc_info=exc,
            )
            raise AuditTrailError("Failed to persist audit trail event") from exc

        for listener in listeners:
            listener(dict(payload))
        return payload


_ACCESS_AUDIT_PATH = Path("observability/audit/access.jsonl")
_SYSTEM_AUDIT_PATH = Path("observability/audit/system.jsonl")
_access_trail: AuditTrail | None = None
_system_trail: AuditTrail | None = None


def get_access_audit_trail(path: Path | str | None = None) -> AuditTrail:
    """Return a process-wide audit trail for access logs."""

    global _access_trail
    if path is not None:
        _access_trail = AuditTrail(path)
    elif _access_trail is None:
        _access_trail = AuditTrail(_ACCESS_AUDIT_PATH)
    return _access_trail


def get_system_audit_trail(path: Path | str | None = None) -> AuditTrail:
    """Return a process-wide audit trail for system operations."""

    global _system_trail
    if path is not None:
        _system_trail = AuditTrail(path)
    elif _system_trail is None:
        _system_trail = AuditTrail(_SYSTEM_AUDIT_PATH)
    return _system_trail
