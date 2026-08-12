"""Security audit logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    """Simple JSON audit logger."""

    def __init__(self, log_path: str | Path = "/var/log/tradepulse/audit.log") -> None:
        self.logger = logging.getLogger("security.audit")
        target = Path(log_path)
        self.logger.handlers.clear()
        self.logger.addHandler(self._build_handler(target))
        self.logger.setLevel(logging.INFO)

    def _build_handler(self, log_path: Path) -> logging.Handler:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = logging.FileHandler(log_path)
        except (OSError, PermissionError):
            handler = logging.NullHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def log(
        self,
        event: str,
        user: str,
        resource: str,
        action: str,
        result: str,
        **kwargs: Any,
    ) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "user": user,
            "resource": resource,
            "action": action,
            "result": result,
            **kwargs,
        }
        self.logger.info(json.dumps(entry))


audit = AuditLogger()
