# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Kill-switch and safe-mode safety controls.

This module implements the global safety state management including:
- Kill-switch: Emergency halt of all trading activity
- Safe-mode: Reduced risk operation (paper trading, reduced positions)
- Operator and programmatic control interfaces
- State persistence and audit logging
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping

__all__ = [
    "SafetyState",
    "SafetyMode",
    "SafetyController",
    "get_safety_controller",
    "KillSwitchTriggeredError",
]

LOGGER = logging.getLogger(__name__)

# Maximum number of audit log entries to retain
MAX_AUDIT_LOG_ENTRIES = 1000


class KillSwitchTriggeredError(RuntimeError):
    """Raised when an operation is blocked by the kill-switch."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Kill-switch is active: {reason}")
        self.reason = reason


class SafetyMode(str, Enum):
    """Safety modes for the trading system.

    Attributes:
        NORMAL: Normal operation with all features enabled.
        SAFE: Reduced risk mode with position limits and paper fallback.
        HALTED: All trading halted (kill-switch engaged).
    """

    NORMAL = "normal"
    SAFE = "safe"
    HALTED = "halted"


@dataclass(slots=True)
class SafetyState:
    """Current state of the safety system.

    Attributes:
        mode: Current safety mode.
        kill_switch_active: Whether the kill-switch is engaged.
        kill_switch_reason: Reason for kill-switch activation.
        kill_switch_timestamp: When the kill-switch was activated.
        safe_mode_active: Whether safe mode is enabled.
        safe_mode_reason: Reason for safe mode activation.
        position_multiplier: Current position size multiplier.
        force_paper_trading: Whether to force paper trading mode.
    """

    mode: SafetyMode = SafetyMode.NORMAL
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    kill_switch_timestamp: datetime | None = None
    safe_mode_active: bool = False
    safe_mode_reason: str = ""
    position_multiplier: float = 1.0
    force_paper_trading: bool = False

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the state.
        """
        return {
            "mode": self.mode.value,
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_reason": self.kill_switch_reason,
            "kill_switch_timestamp": (
                self.kill_switch_timestamp.isoformat()
                if self.kill_switch_timestamp
                else None
            ),
            "safe_mode_active": self.safe_mode_active,
            "safe_mode_reason": self.safe_mode_reason,
            "position_multiplier": self.position_multiplier,
            "force_paper_trading": self.force_paper_trading,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SafetyState":
        """Create from dictionary.

        Args:
            data: Dictionary representation.

        Returns:
            SafetyState instance.
        """
        timestamp = data.get("kill_switch_timestamp")
        parsed_timestamp: datetime | None = None
        if timestamp:
            if isinstance(timestamp, datetime):
                parsed_timestamp = timestamp
            elif isinstance(timestamp, str):
                parsed_timestamp = datetime.fromisoformat(timestamp)

        return cls(
            mode=SafetyMode(str(data.get("mode", "normal"))),
            kill_switch_active=bool(data.get("kill_switch_active", False)),
            kill_switch_reason=str(data.get("kill_switch_reason", "")),
            kill_switch_timestamp=parsed_timestamp,
            safe_mode_active=bool(data.get("safe_mode_active", False)),
            safe_mode_reason=str(data.get("safe_mode_reason", "")),
            position_multiplier=float(data.get("position_multiplier", 1.0)),
            force_paper_trading=bool(data.get("force_paper_trading", False)),
        )


@dataclass(slots=True)
class _AuditEntry:
    """Audit log entry for safety state changes."""

    timestamp: datetime
    action: str
    source: str
    reason: str
    previous_state: SafetyState
    new_state: SafetyState


class SafetyController:
    """Controller for global safety state management.

    This controller manages the kill-switch and safe-mode mechanisms,
    providing both programmatic and operator control interfaces.
    """

    def __init__(
        self,
        *,
        persist_path: Path | str | None = None,
        safe_mode_position_multiplier: float = 0.5,
        auto_persist: bool = True,
    ) -> None:
        """Initialize the safety controller.

        Args:
            persist_path: Path to persist state to disk.
            safe_mode_position_multiplier: Position multiplier for safe mode.
            auto_persist: Whether to auto-persist state changes.
        """
        self._lock = threading.RLock()
        self._state = SafetyState()
        self._persist_path = Path(persist_path) if persist_path else None
        self._safe_mode_multiplier = max(0.0, min(1.0, safe_mode_position_multiplier))
        self._auto_persist = auto_persist
        self._audit_log: list[_AuditEntry] = []
        self._callbacks: list[Callable[[SafetyState], None]] = []

        # Load persisted state if available
        if self._persist_path and self._persist_path.exists():
            self._load_state()

    @property
    def state(self) -> SafetyState:
        """Get the current safety state."""
        with self._lock:
            return SafetyState(
                mode=self._state.mode,
                kill_switch_active=self._state.kill_switch_active,
                kill_switch_reason=self._state.kill_switch_reason,
                kill_switch_timestamp=self._state.kill_switch_timestamp,
                safe_mode_active=self._state.safe_mode_active,
                safe_mode_reason=self._state.safe_mode_reason,
                position_multiplier=self._state.position_multiplier,
                force_paper_trading=self._state.force_paper_trading,
            )

    def is_kill_switch_active(self) -> bool:
        """Check if the kill-switch is currently active.

        Returns:
            True if kill-switch is engaged.
        """
        with self._lock:
            return self._state.kill_switch_active

    def is_safe_mode_active(self) -> bool:
        """Check if safe mode is currently active.

        Returns:
            True if safe mode is engaged.
        """
        with self._lock:
            return self._state.safe_mode_active

    def get_position_multiplier(self) -> float:
        """Get the current position size multiplier.

        Returns:
            Position multiplier (1.0 = normal, <1.0 = reduced).
        """
        with self._lock:
            return self._state.position_multiplier

    def should_force_paper_trading(self) -> bool:
        """Check if paper trading should be forced.

        Returns:
            True if paper trading should be forced.
        """
        with self._lock:
            return self._state.force_paper_trading or self._state.kill_switch_active

    def activate_kill_switch(
        self,
        reason: str,
        *,
        source: str = "programmatic",
    ) -> None:
        """Activate the global kill-switch.

        Args:
            reason: Reason for activation.
            source: Source of the activation (e.g., "risk_engine", "operator").
        """
        with self._lock:
            if self._state.kill_switch_active:
                LOGGER.info(
                    "Kill-switch already active",
                    extra={
                        "event": "safety.kill_switch_already_active",
                        "current_reason": self._state.kill_switch_reason,
                        "new_reason": reason,
                    },
                )
                return

            previous_state = self.state
            self._state.kill_switch_active = True
            self._state.kill_switch_reason = reason
            self._state.kill_switch_timestamp = datetime.now(timezone.utc)
            self._state.mode = SafetyMode.HALTED
            self._state.force_paper_trading = True

            self._record_audit("kill_switch_activated", source, reason, previous_state)
            self._persist()
            self._notify_callbacks()

            LOGGER.critical(
                "Kill-switch activated",
                extra={
                    "event": "safety.kill_switch_activated",
                    "reason": reason,
                    "source": source,
                },
            )

    def deactivate_kill_switch(
        self,
        *,
        source: str = "operator",
        reason: str = "manual_reset",
    ) -> None:
        """Deactivate the kill-switch (requires operator action).

        Args:
            source: Source of the deactivation.
            reason: Reason for deactivation.
        """
        with self._lock:
            if not self._state.kill_switch_active:
                return

            previous_state = self.state
            self._state.kill_switch_active = False
            self._state.kill_switch_reason = ""
            self._state.kill_switch_timestamp = None
            self._state.mode = (
                SafetyMode.SAFE if self._state.safe_mode_active else SafetyMode.NORMAL
            )
            self._state.force_paper_trading = self._state.safe_mode_active

            self._record_audit(
                "kill_switch_deactivated", source, reason, previous_state
            )
            self._persist()
            self._notify_callbacks()

            LOGGER.warning(
                "Kill-switch deactivated",
                extra={
                    "event": "safety.kill_switch_deactivated",
                    "reason": reason,
                    "source": source,
                },
            )

    def activate_safe_mode(
        self,
        reason: str,
        *,
        source: str = "programmatic",
        position_multiplier: float | None = None,
        force_paper: bool = True,
    ) -> None:
        """Activate safe mode with reduced risk parameters.

        Args:
            reason: Reason for activation.
            source: Source of the activation.
            position_multiplier: Override position multiplier (default from config).
            force_paper: Whether to force paper trading.
        """
        with self._lock:
            previous_state = self.state
            self._state.safe_mode_active = True
            self._state.safe_mode_reason = reason
            self._state.position_multiplier = (
                position_multiplier
                if position_multiplier is not None
                else self._safe_mode_multiplier
            )
            self._state.force_paper_trading = force_paper
            if not self._state.kill_switch_active:
                self._state.mode = SafetyMode.SAFE

            self._record_audit("safe_mode_activated", source, reason, previous_state)
            self._persist()
            self._notify_callbacks()

            LOGGER.warning(
                "Safe mode activated",
                extra={
                    "event": "safety.safe_mode_activated",
                    "reason": reason,
                    "source": source,
                    "position_multiplier": self._state.position_multiplier,
                    "force_paper": force_paper,
                },
            )

    def deactivate_safe_mode(
        self,
        *,
        source: str = "operator",
        reason: str = "manual_reset",
    ) -> None:
        """Deactivate safe mode and restore normal operation.

        Args:
            source: Source of the deactivation.
            reason: Reason for deactivation.
        """
        with self._lock:
            if not self._state.safe_mode_active:
                return

            previous_state = self.state
            self._state.safe_mode_active = False
            self._state.safe_mode_reason = ""
            self._state.position_multiplier = 1.0
            if not self._state.kill_switch_active:
                self._state.force_paper_trading = False
                self._state.mode = SafetyMode.NORMAL

            self._record_audit("safe_mode_deactivated", source, reason, previous_state)
            self._persist()
            self._notify_callbacks()

            LOGGER.info(
                "Safe mode deactivated",
                extra={
                    "event": "safety.safe_mode_deactivated",
                    "reason": reason,
                    "source": source,
                },
            )

    def guard_order(self) -> None:
        """Check if orders can be placed, raising if blocked.

        Raises:
            KillSwitchTriggeredError: If kill-switch is active.
        """
        with self._lock:
            if self._state.kill_switch_active:
                raise KillSwitchTriggeredError(self._state.kill_switch_reason)

    def register_callback(self, callback: Callable[[SafetyState], None]) -> None:
        """Register a callback for state changes.

        Args:
            callback: Function to call when state changes.
        """
        with self._lock:
            self._callbacks.append(callback)

    def get_audit_log(self, *, limit: int | None = None) -> list[dict[str, object]]:
        """Get the audit log of state changes.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of audit log entries.
        """
        with self._lock:
            entries = self._audit_log[-limit:] if limit else self._audit_log
            return [
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "action": entry.action,
                    "source": entry.source,
                    "reason": entry.reason,
                    "previous_state": entry.previous_state.to_dict(),
                    "new_state": entry.new_state.to_dict(),
                }
                for entry in entries
            ]

    def _record_audit(
        self,
        action: str,
        source: str,
        reason: str,
        previous_state: SafetyState,
    ) -> None:
        """Record an audit log entry."""
        entry = _AuditEntry(
            timestamp=datetime.now(timezone.utc),
            action=action,
            source=source,
            reason=reason,
            previous_state=previous_state,
            new_state=self.state,
        )
        self._audit_log.append(entry)

        # Keep audit log bounded
        if len(self._audit_log) > MAX_AUDIT_LOG_ENTRIES:
            self._audit_log = self._audit_log[-MAX_AUDIT_LOG_ENTRIES:]

    def _persist(self) -> None:
        """Persist state to disk if configured."""
        if not self._auto_persist or not self._persist_path:
            return

        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = self._state.to_dict()
            data["persisted_at"] = datetime.now(timezone.utc).isoformat()
            tmp_path = self._persist_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp_path.replace(self._persist_path)
        except Exception as exc:
            LOGGER.warning(
                "Failed to persist safety state",
                extra={
                    "event": "safety.persist_failed",
                    "error": str(exc),
                },
            )

    def _load_state(self) -> None:
        """Load state from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._state = SafetyState.from_dict(data)
            LOGGER.info(
                "Loaded persisted safety state",
                extra={
                    "event": "safety.state_loaded",
                    "state": self._state.to_dict(),
                },
            )
        except Exception as exc:
            LOGGER.warning(
                "Failed to load safety state",
                extra={
                    "event": "safety.load_failed",
                    "error": str(exc),
                },
            )

    def _notify_callbacks(self) -> None:
        """Notify registered callbacks of state change."""
        state = self.state
        for callback in self._callbacks:
            try:
                callback(state)
            except Exception as exc:
                LOGGER.exception(
                    "Safety callback failed",
                    extra={
                        "event": "safety.callback_error",
                        "error": str(exc),
                    },
                )


# Global singleton instance
_controller_lock = threading.Lock()
_global_controller: SafetyController | None = None


def get_safety_controller(
    *,
    persist_path: Path | str | None = None,
    safe_mode_position_multiplier: float = 0.5,
) -> SafetyController:
    """Get or create the global safety controller.

    Args:
        persist_path: Path to persist state (only used on first call).
        safe_mode_position_multiplier: Position multiplier for safe mode.

    Returns:
        The global SafetyController instance.
    """
    global _global_controller
    with _controller_lock:
        if _global_controller is None:
            _global_controller = SafetyController(
                persist_path=persist_path,
                safe_mode_position_multiplier=safe_mode_position_multiplier,
            )
        return _global_controller
