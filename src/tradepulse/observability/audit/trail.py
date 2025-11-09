"""Audit trail helpers for MiFID II compliant logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import stat
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
    """Append-only JSONL audit trail with optional subscribers and WORM mode support.
    
    WORM (Write Once Read Many) mode ensures immutability by:
    - Setting file permissions to 0444 (read-only) after writing
    - Supporting rotation for long-term storage (>7 years)
    - Optional HMAC signing for event integrity
    """

    def __init__(
        self,
        path: Path | str,
        *,
        logger: logging.Logger | None = None,
        clock: Callable[[], datetime] | None = None,
        worm_mode: bool = False,
        hmac_key: bytes | None = None,
        max_size_mb: float = 100.0,
        retention_years: int = 7,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._logger = logger or logging.getLogger("tradepulse.audit.trail")
        self._clock = clock or _utc_now
        self._lock = RLock()
        self._listeners: MutableSequence[Callable[[dict[str, object]], None]] = []
        self._worm_mode = worm_mode
        self._hmac_key = hmac_key
        self._max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._retention_years = retention_years

    @property
    def path(self) -> Path:
        return self._path

    def register_listener(
        self, listener: Callable[[dict[str, object]], None]
    ) -> None:
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
        """Persist a structured audit event with optional HMAC signing and WORM mode."""

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
        
        # Add HMAC signature if key is provided
        if self._hmac_key:
            message = json.dumps(payload, sort_keys=True).encode("utf-8")
            signature = hmac.new(self._hmac_key, message, hashlib.sha256).hexdigest()
            payload["hmac_signature"] = signature
        
        try:
            serialized = json.dumps(payload, sort_keys=True)
            with self._lock:
                # Check if rotation is needed
                if self._path.exists() and self._path.stat().st_size > self._max_size_bytes:
                    self._rotate_audit_log()
                
                # Temporarily make file writable if in WORM mode
                if self._worm_mode and self._path.exists():
                    os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
                
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(serialized + "\n")
                
                # Apply WORM mode: make file read-only (0444)
                if self._worm_mode:
                    os.chmod(self._path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                
                listeners: Iterable[
                    Callable[[dict[str, object]], None]
                ] = tuple(self._listeners)
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
    
    def _rotate_audit_log(self) -> None:
        """Rotate audit log file when size limit is reached."""
        if not self._path.exists():
            return
        
        # Generate rotation filename with timestamp
        timestamp = self._clock().strftime("%Y%m%d_%H%M%S")
        rotated_path = self._path.parent / f"{self._path.stem}_{timestamp}{self._path.suffix}"
        
        # Temporarily make writable to rename
        if self._worm_mode:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        
        self._path.rename(rotated_path)
        
        # Make rotated file read-only
        if self._worm_mode:
            os.chmod(rotated_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        
        self._logger.info(
            "audit.trail.rotated",
            extra={"old_path": str(self._path), "new_path": str(rotated_path)},
        )


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
