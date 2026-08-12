# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Execution-layer audit logging utilities."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable, Mapping, MutableSequence, Optional

__all__ = [
    "ExecutionAuditLogger",
    "get_execution_audit_logger",
]


class ExecutionAuditLogger:
    """Append-only audit logger for execution decisions."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._listeners: MutableSequence[Callable[[dict], None]] = []
        self._lock = RLock()

    @property
    def path(self) -> Path:
        """Return the audit file path."""

        return self._path

    def register_listener(self, listener: Callable[[dict], None]) -> None:
        """Register a callback invoked whenever a new entry is written."""

        with self._lock:
            self._listeners.append(listener)

    def emit(self, payload: Mapping[str, object]) -> None:
        """Append an audit event and notify listeners."""

        # Route through ``default_clock()`` so the execution audit shares
        # a single time source with the rest of the stack — replay tests
        # depend on the two trails staying in lock-step.
        from geosync.core.compat import default_clock, safe_isoformat

        record = dict(payload)
        record.setdefault("timestamp", safe_isoformat(default_clock().now()))
        serialized = json.dumps(record, sort_keys=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
            listeners: Iterable[Callable[[dict], None]] = tuple(self._listeners)
        for listener in listeners:
            listener(dict(record))


_DEFAULT_AUDIT_PATH = Path("observability/audit/execution.jsonl")
_audit_logger: Optional[ExecutionAuditLogger] = None


def get_execution_audit_logger(path: Path | None = None) -> ExecutionAuditLogger:
    """Return the process-wide execution audit logger."""

    global _audit_logger
    if _audit_logger is None:
        audit_path = path or _DEFAULT_AUDIT_PATH
        _audit_logger = ExecutionAuditLogger(audit_path)
    elif path is not None and _audit_logger.path != Path(path):
        # Allow tests to override the destination by resetting the singleton.
        _audit_logger = ExecutionAuditLogger(path)
    return _audit_logger
