# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Structured JSON logging utilities for TradePulse.

This module provides structured logging with JSON formatting, correlation IDs,
and performance tracking capabilities.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

try:  # pragma: no cover - tracing is optional
    from opentelemetry.trace import get_current_span

    _TRACE_LOG_CORRELATION = True
except Exception:  # pragma: no cover - optional dependency not installed
    get_current_span = None  # type: ignore[assignment]
    _TRACE_LOG_CORRELATION = False
from uuid import uuid4

try:  # pragma: no cover - optional dependency
    from core.tracing.distributed import (
        current_correlation_id,
        generate_correlation_id,
    )
except Exception:  # pragma: no cover - tracing helpers optional

    def current_correlation_id(_: Optional[str] = None) -> Optional[str]:
        return None

    def generate_correlation_id() -> str:
        return str(uuid4())


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if _TRACE_LOG_CORRELATION and get_current_span is not None:
            span = get_current_span()
            try:
                context = span.get_span_context()
            except AttributeError:  # pragma: no cover - defensive guard
                context = None
            if context:
                is_valid_attr = getattr(context, "is_valid", None)
                is_valid = (
                    bool(is_valid_attr())
                    if callable(is_valid_attr)
                    else bool(is_valid_attr)
                )
                if is_valid:
                    trace_id = getattr(context, "trace_id", 0)
                    span_id = getattr(context, "span_id", 0)
                    if trace_id:
                        log_data["trace_id"] = f"{trace_id:032x}"
                    if span_id:
                        log_data["span_id"] = f"{span_id:016x}"

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        # Add custom fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def _resolve_level(level: int | str) -> int:
    """Resolve a logging level from either a string name or numeric value."""

    if isinstance(level, bool):
        # ``bool`` is a subclass of ``int`` but treating it as a valid logging
        # level leads to confusing behaviour (e.g. ``True`` maps to level 1).
        # Reject boolean inputs explicitly so callers provide an actual level
        # name/number.
        raise ValueError("Invalid log level: True" if level else "Invalid log level: False")

    if isinstance(level, str):
        normalized = level.strip()
        if not normalized:
            raise ValueError("Unknown log level: ''")

        # First try to interpret the string as a standard logging name in a
        # case-insensitive manner (e.g., "info", "WARNING").  ``getLevelName``
        # returns an ``int`` when it recognises the name and a descriptive
        # string otherwise.
        numeric_level = logging.getLevelName(normalized.upper())
        if isinstance(numeric_level, int):
            return int(numeric_level)

        # Fall back to accepting numeric strings so callers can pass values
        # read from configuration files without manual casting.
        try:
            return int(normalized)
        except ValueError:
            raise ValueError(f"Unknown log level: {level}")

    try:
        return int(level)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid log level: {level}")


class StructuredLogger:
    """Wrapper around standard logger with structured logging capabilities."""

    def __init__(self, name: str, correlation_id: Optional[str] = None):
        self.logger = logging.getLogger(name)
        resolved = correlation_id or current_correlation_id()
        self.correlation_id = resolved or generate_correlation_id()

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        """Internal logging method with structured fields.

        Parameters mirror :meth:`logging.Logger.log` so callers can supply
        ``exc_info``/``stack_info`` while keeping structured extras.  The
        previous implementation treated every keyword argument as an
        ``extra`` field which meant ``exc_info`` ended up as a raw exception
        object in the JSON payload.  The JSON formatter cannot serialise
        exceptions which caused the log record to be dropped entirely – the
        behaviour observed in ``merge_streams`` tests when a stream raised.
        """

        exc_info = kwargs.pop("exc_info", None)
        stack_info = kwargs.pop("stack_info", False)
        stacklevel = kwargs.pop("stacklevel", 1)

        if exc_info:
            if exc_info is True:
                exc_info = sys.exc_info()
            elif isinstance(exc_info, BaseException):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
            elif not isinstance(exc_info, tuple):
                # Defensive normalisation for unexpected types
                exc_info = sys.exc_info()

        try:
            resolved_stacklevel = max(int(stacklevel), 1) + 1
        except Exception:
            resolved_stacklevel = 2

        extra_fields = kwargs
        extra_data: Dict[str, Any] = {"correlation_id": self.correlation_id}
        if extra_fields:
            extra_data["extra_fields"] = extra_fields

        self.logger.log(
            level,
            msg,
            extra=extra_data,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=resolved_stacklevel,
        )

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message with structured fields."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with structured fields."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with structured fields."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with structured fields."""
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        """Log critical message with structured fields."""
        self._log(logging.CRITICAL, msg, **kwargs)

    @contextmanager
    def operation(
        self,
        operation_name: str,
        *,
        level: int = logging.INFO,
        success_level: int | None = None,
        failure_level: int = logging.ERROR,
        emit_start: bool = True,
        emit_success: bool = True,
        **context: Any,
    ) -> Iterator[Dict[str, Any]]:
        """Context manager for tracking operation timing and status.

        Args:
            operation_name: Name of the operation being tracked
            level: Logging level for the start message (defaults to ``INFO``)
            success_level: Optional explicit logging level for the success message.
                When omitted the ``level`` argument is reused.
            failure_level: Logging level for failure messages (defaults to ``ERROR``)
            emit_start: Whether to emit the "Starting operation" log entry.
            emit_success: Whether to emit the "Completed operation" log entry.
            **context: Additional context fields to log

        Yields:
            Dictionary to store operation results

        Example:
            >>> logger = StructuredLogger("myapp")
            >>> with logger.operation("compute_indicator", indicator="RSI") as op:
            ...     result = compute_rsi(prices)
            ...     op["result_value"] = result
        """
        start_time = time.perf_counter()
        op_context: Dict[str, Any] = {"operation": operation_name, **context}

        if emit_start and self.logger.isEnabledFor(level):
            self._log(level, f"Starting operation: {operation_name}", **op_context)

        try:
            yield op_context
        except Exception as e:
            duration = time.perf_counter() - start_time
            if self.logger.isEnabledFor(failure_level):
                self._log(
                    failure_level,
                    f"Failed operation: {operation_name}",
                    duration_seconds=duration,
                    status="failure",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    **op_context,
                )
            raise
        else:
            duration = time.perf_counter() - start_time
            if emit_success:
                resolved_success_level = (
                    success_level if success_level is not None else level
                )
                if self.logger.isEnabledFor(resolved_success_level):
                    self._log(
                        resolved_success_level,
                        f"Completed operation: {operation_name}",
                        duration_seconds=duration,
                        status="success",
                        **op_context,
                    )


def configure_logging(
    level: int | str = logging.INFO, use_json: bool = True, stream: Any = None
) -> None:
    """Configure application-wide logging.

    Args:
        level: Logging level as an integer or name
        use_json: Whether to use JSON formatting
        stream: Output stream (defaults to sys.stdout)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(_resolve_level(level))

    # Remove handlers previously attached by TradePulse without disturbing
    # external handlers such as pytest's log capture fixtures.
    managed: list[logging.Handler] = []
    for handler in list(root_logger.handlers):
        if getattr(handler, "_tradepulse_managed", False):
            managed.append(handler)
            root_logger.removeHandler(handler)
    for handler in managed:
        try:
            handler.close()
        except Exception:  # pragma: no cover - defensive cleanup
            pass

    # Create handler
    handler = logging.StreamHandler(stream or sys.stdout)

    # Set formatter
    if use_json:
        json_formatter: logging.Formatter = JSONFormatter()
        handler.setFormatter(json_formatter)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
    handler._tradepulse_managed = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)


def get_logger(name: str, correlation_id: Optional[str] = None) -> StructuredLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)
        correlation_id: Optional correlation ID for request tracking

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name, correlation_id)


__all__ = [
    "JSONFormatter",
    "StructuredLogger",
    "configure_logging",
    "get_logger",
]
