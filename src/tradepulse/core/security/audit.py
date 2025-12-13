"""Security audit logging helpers."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    """Simple JSON audit logger."""

    def __init__(self, log_path: str | Path = "/var/log/tradepulse/audit.log") -> None:
        self.logger = logging.getLogger("security.audit")
        handler = self._build_handler(Path(log_path))
        if not self.logger.handlers or all(
            isinstance(existing, logging.NullHandler) for existing in self.logger.handlers
        ):
            self.logger.addHandler(handler)
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
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "user": user,
            "resource": resource,
            "action": action,
            "result": result,
            **kwargs,
        }
        self.logger.info(json.dumps(entry))

    def flush(self) -> None:
        """Flush all handlers to ensure data is written to disk.
        
        This is particularly important in testing scenarios where
        immediate verification of log output is required.
        """
        for handler in self.logger.handlers:
            handler.flush()
            # Ensure data is physically written to disk (not just OS buffer)
            if hasattr(handler, 'stream') and hasattr(handler.stream, 'fileno'):
                try:
                    os.fsync(handler.stream.fileno())
                except (OSError, AttributeError):
                    # NullHandler or other handlers without file descriptor
                    pass


audit = AuditLogger()
