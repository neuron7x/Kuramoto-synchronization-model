# SPDX-License-Identifier: MIT
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
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator, Optional

try:  # pragma: no cover - tracing is optional
    from opentelemetry.trace import get_current_span

    _TRACE_LOG_CORRELATION = True
except Exception:  # pragma: no cover - optional dependency not installed
    get_current_span = None  # type: ignore[assignment]
_TRACE_LOG_CORRELATION = False
from uuid import uuid4


_CORRELATION_ID_VAR: ContextVar[Optional[str]] = ContextVar(
    "tradepulse_correlation_id", default=None
)


def get_correlation_id(default: Optional[str] = None) -> Optional[str]:
    """Return the correlation identifier for the current execution context.

    Args:
        default: Value to return when no correlation ID has been bound.

    Returns:
        The currently bound correlation identifier or the provided ``default``.
    """

    correlation_id = _CORRELATION_ID_VAR.get()
    if correlation_id is None:
        return default
    return correlation_id


def set_correlation_id(correlation_id: Optional[str]) -> None:
    """Bind a correlation identifier to the current context."""

    _CORRELATION_ID_VAR.set(correlation_id)


def clear_correlation_id() -> None:
    """Clear any correlation identifier bound to the current context."""

    _CORRELATION_ID_VAR.set(None)


@contextmanager
def correlation_id_context(
    correlation_id: Optional[str],
) -> Iterator[Optional[str]]:
    """Temporarily bind a correlation identifier within the enclosed context."""

    token: Token[Optional[str]] = _CORRELATION_ID_VAR.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _CORRELATION_ID_VAR.reset(token)


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
                context = span.get_span_context()  # type: ignore[assignment]
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


class StructuredLogger:
    """Wrapper around standard logger with structured logging capabilities."""

    def __init__(self, name: str, correlation_id: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self._explicit_correlation_id = correlation_id

    def _resolve_correlation_id(self) -> str:
        """Determine the correlation identifier for the current log record."""

        context_id = get_correlation_id()
        if context_id:
            return context_id

        if self._explicit_correlation_id:
            return self._explicit_correlation_id

        self._explicit_correlation_id = str(uuid4())
        return self._explicit_correlation_id

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        """Internal logging method with structured fields."""
        extra_data: Dict[str, Any] = {"correlation_id": self._resolve_correlation_id()}
        if kwargs:
            extra_data["extra_fields"] = kwargs
        self.logger.log(level, msg, extra=extra_data)

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
        self, operation_name: str, **context: Any
    ) -> Iterator[Dict[str, Any]]:
        """Context manager for tracking operation timing and status.

        Args:
            operation_name: Name of the operation being tracked
            **context: Additional context fields to log

        Yields:
            Dictionary to store operation results

        Example:
            >>> logger = StructuredLogger("myapp")
            >>> with logger.operation("compute_indicator", indicator="RSI") as op:
            ...     result = compute_rsi(prices)
            ...     op["result_value"] = result
        """
        start_time = time.time()
        op_context: Dict[str, Any] = {"operation": operation_name, **context}

        self.info(f"Starting operation: {operation_name}", **op_context)

        try:
            yield op_context
            duration = time.time() - start_time
            self.info(
                f"Completed operation: {operation_name}",
                duration_seconds=duration,
                status="success",
                **op_context,
            )
        except Exception as e:
            duration = time.time() - start_time
            self.error(
                f"Failed operation: {operation_name}",
                duration_seconds=duration,
                status="failure",
                error_type=type(e).__name__,
                error_message=str(e),
                **op_context,
            )
            raise


def configure_logging(
    level: str = "INFO", use_json: bool = True, stream: Any = None
) -> None:
    """Configure application-wide logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Whether to use JSON formatting
        stream: Output stream (defaults to sys.stdout)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

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
    "clear_correlation_id",
    "configure_logging",
    "correlation_id_context",
    "get_correlation_id",
    "get_logger",
    "set_correlation_id",
]
