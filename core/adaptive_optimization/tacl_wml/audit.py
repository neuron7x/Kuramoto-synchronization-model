"""Audit logging for WML decisions."""

from typing import Dict, Any, List
from datetime import datetime, timezone


class AuditLogger:
    """Simple audit logger for WML events."""

    def __init__(self) -> None:
        """Initialize audit logger."""
        self._log: List[Dict[str, Any]] = []

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """Log an event with associated data.

        Args:
            event: Event name (e.g., "WML_APPLY", "WML_REJECTED", "WML_FROZEN")
            data: Event data dictionary
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": data,
        }
        self._log.append(entry)

    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all logged events.

        Returns:
            List of log entries
        """
        return self._log.copy()

    def clear(self) -> None:
        """Clear all logs."""
        self._log.clear()
