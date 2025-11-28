"""Global kill-switch used by safety-critical components.

This module provides enterprise-grade kill switch functionality with:
- Thread-safe state management
- Audit logging for all state changes
- Activation reason tracking
- State persistence for recovery
- Cooldown protection against rapid toggling

Aligned with:
- NIST SP 800-53 SI-17 (Fail-Safe Procedures)
- ISO 27001 A.12.1.4 (Separation of Development, Testing and Operational Environments)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class KillSwitchReason(Enum):
    """Predefined reasons for kill switch activation."""

    MANUAL = "manual_activation"
    CIRCUIT_BREAKER = "circuit_breaker_triggered"
    ENERGY_THRESHOLD = "energy_threshold_exceeded"
    SECURITY_INCIDENT = "security_incident_detected"
    SYSTEM_OVERLOAD = "system_overload_detected"
    DATA_INTEGRITY = "data_integrity_violation"
    EXTERNAL_SIGNAL = "external_signal_received"
    UNKNOWN = "unknown"


@dataclass
class KillSwitchEvent:
    """Record of a kill switch state change event."""

    timestamp: float
    action: str  # "activate" or "deactivate"
    reason: str
    source: str  # caller identification
    success: bool
    previous_state: bool
    new_state: bool

    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat(),
            "action": self.action,
            "reason": self.reason,
            "source": self.source,
            "success": self.success,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
        }


@dataclass
class KillSwitchState:
    """Current state of the kill switch with metadata."""

    active: bool = False
    activation_time: Optional[float] = None
    activation_reason: Optional[str] = None
    activation_source: Optional[str] = None
    deactivation_count: int = 0
    activation_count: int = 0
    last_event_time: Optional[float] = None


class KillSwitchManager:
    """Thread-safe kill switch manager with audit logging and state persistence.

    This class provides a robust kill switch implementation suitable for
    safety-critical trading systems.

    Attributes:
        state: Current kill switch state
        audit_log: List of all state change events
        callbacks: List of callback functions to notify on state changes
    """

    _instance: Optional["KillSwitchManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *, _force_new: bool = False, **kwargs) -> "KillSwitchManager":
        with cls._lock:
            if cls._instance is None or _force_new:
                instance = super().__new__(cls)
                instance._initialized = False
                if not _force_new:
                    cls._instance = instance
                return instance
            return cls._instance

    def __init__(
        self,
        *,
        cooldown_seconds: float = 5.0,
        max_audit_entries: int = 1000,
        persist_path: Optional[Path] = None,
        _force_new: bool = False,
    ) -> None:
        """Initialize the kill switch manager.

        Args:
            cooldown_seconds: Minimum time between state changes to prevent rapid toggling
            max_audit_entries: Maximum number of audit log entries to retain
            persist_path: Path for state persistence file
            _force_new: Internal flag for creating non-singleton instances (testing)
        """
        if getattr(self, "_initialized", False) and not _force_new:
            return

        self._state_lock = threading.RLock()
        self.state = KillSwitchState()
        self.audit_log: List[KillSwitchEvent] = []
        self.callbacks: List[Callable[[bool, str], None]] = []
        self.cooldown_seconds = cooldown_seconds
        self.max_audit_entries = max_audit_entries
        self.persist_path = persist_path

        # Load persisted state if available
        self._load_persisted_state()

        self._initialized = True
        logger.info(
            "KillSwitchManager initialized with cooldown=%ss, persist_path=%s",
            cooldown_seconds,
            persist_path,
        )

    def is_active(self) -> bool:
        """Check if kill switch is currently active.

        Returns:
            True if kill switch is active (either programmatically or via env var)
        """
        with self._state_lock:
            return self.state.active or os.getenv("TRADEPULSE_KILL_SWITCH", "0") == "1"

    def activate(
        self,
        reason: KillSwitchReason | str = KillSwitchReason.MANUAL,
        source: str = "unknown",
        *,
        force: bool = False,
    ) -> bool:
        """Activate the kill switch.

        Args:
            reason: Reason for activation
            source: Identifier of the caller (e.g., module name, user ID)
            force: If True, bypass cooldown protection

        Returns:
            True if activation succeeded, False otherwise
        """
        reason_str = (
            reason.value if isinstance(reason, KillSwitchReason) else str(reason)
        )

        with self._state_lock:
            now = time.time()
            previous_state = self.state.active

            # Check cooldown (unless forced or already active)
            if not force and not self.state.active:
                if (
                    self.state.last_event_time is not None
                    and now - self.state.last_event_time < self.cooldown_seconds
                ):
                    logger.warning(
                        "Kill switch activation blocked by cooldown (%.1fs remaining)",
                        self.cooldown_seconds - (now - self.state.last_event_time),
                    )
                    self._record_event(
                        action="activate",
                        reason=reason_str,
                        source=source,
                        success=False,
                        previous_state=previous_state,
                        new_state=previous_state,
                    )
                    return False

            # Already active - just log
            if self.state.active:
                logger.info(
                    "Kill switch already active (reason: %s)",
                    self.state.activation_reason,
                )
                return True

            # Activate
            self.state.active = True
            self.state.activation_time = now
            self.state.activation_reason = reason_str
            self.state.activation_source = source
            self.state.activation_count += 1
            self.state.last_event_time = now

            self._record_event(
                action="activate",
                reason=reason_str,
                source=source,
                success=True,
                previous_state=previous_state,
                new_state=True,
            )

            logger.warning(
                "KILL SWITCH ACTIVATED - Reason: %s, Source: %s",
                reason_str,
                source,
            )

            # Persist state
            self._persist_state()

            # Notify callbacks
            self._notify_callbacks(True, reason_str)

            return True

    def deactivate(
        self,
        reason: str = "manual_deactivation",
        source: str = "unknown",
        *,
        force: bool = False,
    ) -> bool:
        """Deactivate the kill switch.

        Args:
            reason: Reason for deactivation
            source: Identifier of the caller
            force: If True, bypass cooldown protection

        Returns:
            True if deactivation succeeded, False otherwise
        """
        with self._state_lock:
            now = time.time()
            previous_state = self.state.active

            # Check cooldown (unless forced or already inactive)
            if not force and self.state.active:
                if (
                    self.state.last_event_time is not None
                    and now - self.state.last_event_time < self.cooldown_seconds
                ):
                    logger.warning(
                        "Kill switch deactivation blocked by cooldown (%.1fs remaining)",
                        self.cooldown_seconds - (now - self.state.last_event_time),
                    )
                    self._record_event(
                        action="deactivate",
                        reason=reason,
                        source=source,
                        success=False,
                        previous_state=previous_state,
                        new_state=previous_state,
                    )
                    return False

            # Already inactive
            if not self.state.active:
                logger.info("Kill switch already inactive")
                return True

            # Deactivate
            self.state.active = False
            self.state.deactivation_count += 1
            self.state.last_event_time = now

            self._record_event(
                action="deactivate",
                reason=reason,
                source=source,
                success=True,
                previous_state=previous_state,
                new_state=False,
            )

            logger.info(
                "Kill switch deactivated - Reason: %s, Source: %s, Was active for %.1fs",
                reason,
                source,
                now - (self.state.activation_time or now),
            )

            # Clear activation metadata
            self.state.activation_time = None
            self.state.activation_reason = None
            self.state.activation_source = None

            # Persist state
            self._persist_state()

            # Notify callbacks
            self._notify_callbacks(False, reason)

            return True

    def get_status(self) -> dict:
        """Get comprehensive kill switch status.

        Returns:
            Dictionary with current state and statistics
        """
        with self._state_lock:
            now = time.time()
            return {
                "active": self.is_active(),
                "active_programmatic": self.state.active,
                "active_env": os.getenv("TRADEPULSE_KILL_SWITCH", "0") == "1",
                "activation_time": self.state.activation_time,
                "activation_reason": self.state.activation_reason,
                "activation_source": self.state.activation_source,
                "active_duration_seconds": (
                    now - self.state.activation_time
                    if self.state.activation_time
                    else None
                ),
                "total_activations": self.state.activation_count,
                "total_deactivations": self.state.deactivation_count,
                "last_event_time": self.state.last_event_time,
                "cooldown_seconds": self.cooldown_seconds,
                "audit_log_size": len(self.audit_log),
            }

    def get_audit_log(self, limit: int = 100) -> List[dict]:
        """Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit log entry dictionaries
        """
        with self._state_lock:
            return [event.to_dict() for event in self.audit_log[-limit:]]

    def register_callback(self, callback: Callable[[bool, str], None]) -> None:
        """Register a callback to be notified on state changes.

        Args:
            callback: Function that takes (is_active: bool, reason: str)
        """
        with self._state_lock:
            self.callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[bool, str], None]) -> None:
        """Unregister a previously registered callback.

        Args:
            callback: The callback function to remove
        """
        with self._state_lock:
            if callback in self.callbacks:
                self.callbacks.remove(callback)

    def _record_event(
        self,
        action: str,
        reason: str,
        source: str,
        success: bool,
        previous_state: bool,
        new_state: bool,
    ) -> None:
        """Record a state change event in the audit log."""
        event = KillSwitchEvent(
            timestamp=time.time(),
            action=action,
            reason=reason,
            source=source,
            success=success,
            previous_state=previous_state,
            new_state=new_state,
        )
        self.audit_log.append(event)

        # Trim audit log if needed
        if len(self.audit_log) > self.max_audit_entries:
            self.audit_log = self.audit_log[-self.max_audit_entries :]

    def _notify_callbacks(self, is_active: bool, reason: str) -> None:
        """Notify all registered callbacks of a state change."""
        for callback in self.callbacks:
            try:
                callback(is_active, reason)
            except Exception as e:
                logger.error("Kill switch callback error: %s", e)

    def _persist_state(self) -> None:
        """Persist current state to disk for recovery."""
        if self.persist_path is None:
            return

        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            state_data = {
                "active": self.state.active,
                "activation_time": self.state.activation_time,
                "activation_reason": self.state.activation_reason,
                "activation_source": self.state.activation_source,
                "activation_count": self.state.activation_count,
                "deactivation_count": self.state.deactivation_count,
                "persisted_at": time.time(),
            }
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
        except (OSError, IOError) as e:
            logger.warning("Failed to persist kill switch state: %s", e)

    def _load_persisted_state(self) -> None:
        """Load persisted state from disk."""
        if self.persist_path is None or not self.persist_path.exists():
            return

        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # Only restore if active (safety: fail-safe to inactive)
            if state_data.get("active", False):
                self.state.active = True
                self.state.activation_time = state_data.get("activation_time")
                self.state.activation_reason = state_data.get(
                    "activation_reason", "restored_from_persistence"
                )
                self.state.activation_source = state_data.get(
                    "activation_source", "persistence_restore"
                )
                logger.warning(
                    "Kill switch state restored from persistence - ACTIVE (reason: %s)",
                    self.state.activation_reason,
                )

            self.state.activation_count = state_data.get("activation_count", 0)
            self.state.deactivation_count = state_data.get("deactivation_count", 0)

        except (OSError, IOError, json.JSONDecodeError) as e:
            logger.warning("Failed to load persisted kill switch state: %s", e)

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        global _manager
        with cls._lock:
            cls._instance = None
            _manager = None


# Global manager instance
_manager: Optional[KillSwitchManager] = None


def _get_manager() -> KillSwitchManager:
    """Get or create the global kill switch manager."""
    global _manager
    if _manager is None:
        _manager = KillSwitchManager()
    return _manager


# Legacy API compatibility
_LOCK = threading.Lock()
_ACTIVE = False


def is_kill_switch_active() -> bool:
    """Check if the kill switch is currently active.

    Returns:
        True if kill switch is active
    """
    return _get_manager().is_active()


def activate_kill_switch(
    reason: KillSwitchReason | str = KillSwitchReason.MANUAL,
    source: str = "legacy_api",
) -> None:
    """Activate the kill switch.

    Args:
        reason: Reason for activation
        source: Identifier of the caller
    """
    _get_manager().activate(reason=reason, source=source)


def deactivate_kill_switch(
    reason: str = "manual_deactivation",
    source: str = "legacy_api",
) -> None:
    """Deactivate the kill switch.

    Args:
        reason: Reason for deactivation
        source: Identifier of the caller
    """
    _get_manager().deactivate(reason=reason, source=source)


@contextmanager
def kill_switch_guard(
    reason: KillSwitchReason | str = KillSwitchReason.MANUAL,
    source: str = "guard_context",
):
    """Context manager for temporary kill switch activation.

    Args:
        reason: Reason for activation
        source: Identifier of the caller

    Example:
        with kill_switch_guard(KillSwitchReason.SECURITY_INCIDENT, "incident_handler"):
            # All trading halted during this block
            handle_incident()
    """
    manager = _get_manager()
    manager.activate(reason=reason, source=source, force=True)
    try:
        yield
    finally:
        manager.deactivate(reason="guard_context_exit", source=source, force=True)


def get_kill_switch_status() -> dict:
    """Get comprehensive kill switch status.

    Returns:
        Dictionary with current state and statistics
    """
    return _get_manager().get_status()


def get_kill_switch_audit_log(limit: int = 100) -> List[dict]:
    """Get recent kill switch audit log entries.

    Args:
        limit: Maximum number of entries to return

    Returns:
        List of audit log entry dictionaries
    """
    return _get_manager().get_audit_log(limit=limit)


__all__ = [
    # New API
    "KillSwitchManager",
    "KillSwitchReason",
    "KillSwitchEvent",
    "KillSwitchState",
    "get_kill_switch_status",
    "get_kill_switch_audit_log",
    # Legacy API
    "is_kill_switch_active",
    "activate_kill_switch",
    "deactivate_kill_switch",
    "kill_switch_guard",
]
