# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Secure error handling utilities to prevent information leakage.

This module provides error handling utilities that prevent sensitive
information from being exposed in error messages and logs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_LOGGER = logging.getLogger(__name__)


class SecureError(Exception):
    """Base class for secure errors that hide implementation details.

    This error class provides a public message for users and a detailed
    message for logging, ensuring sensitive information isn't exposed.
    """

    def __init__(
        self,
        public_message: str,
        detail_message: Optional[str] = None,
        error_code: Optional[str] = None,
        **context: Any,
    ):
        """Initialize a secure error.

        Args:
            public_message: Safe message to show to users/external systems
            detail_message: Detailed message for internal logging only
            error_code: Optional error code for tracking
            **context: Additional context for logging (will be sanitized)
        """
        super().__init__(public_message)
        self.public_message = public_message
        self.detail_message = detail_message or public_message
        self.error_code = error_code
        self.context = self._sanitize_context(context)

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from context."""
        sanitized = {}
        sensitive_keys = {
            "password",
            "passwd",
            "pwd",
            "secret",
            "api_key",
            "apikey",
            "token",
            "auth",
            "authorization",
            "private_key",
            "credit_card",
        }

        for key, value in context.items():
            key_lower = key.lower()
            # Check if key contains sensitive words
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized

    def to_dict(self, include_details: bool = False) -> Dict[str, Any]:
        """Convert error to dictionary format.

        Args:
            include_details: If True, includes detailed information (for internal use)

        Returns:
            Dictionary representation of the error
        """
        result = {
            "error": self.public_message,
        }

        if self.error_code:
            result["error_code"] = self.error_code

        if include_details:
            result["detail"] = self.detail_message
            if self.context:
                result["context"] = self.context

        return result

    def log(self, level: int = logging.ERROR) -> None:
        """Log the error with full details."""
        _LOGGER.log(
            level,
            "Error occurred: %s | Detail: %s | Code: %s | Context: %s",
            self.public_message,
            self.detail_message,
            self.error_code or "N/A",
            self.context or {},
        )


class TradingError(SecureError):
    """Error related to trading operations."""

    pass


class DataValidationError(SecureError):
    """Error related to data validation."""

    pass


class AuthenticationError(SecureError):
    """Error related to authentication."""

    def __init__(self, detail_message: Optional[str] = None, **context: Any):
        """Initialize an authentication error.

        Note: The public message is always generic to prevent user enumeration.
        """
        super().__init__(
            public_message="Authentication failed",
            detail_message=detail_message,
            error_code="AUTH_FAILED",
            **context,
        )


class AuthorizationError(SecureError):
    """Error related to authorization/permissions."""

    def __init__(self, resource: Optional[str] = None, **context: Any):
        """Initialize an authorization error."""
        public_msg = "Access denied"
        detail_msg = (
            f"Access denied to resource: {resource}" if resource else "Access denied"
        )

        super().__init__(
            public_message=public_msg,
            detail_message=detail_msg,
            error_code="ACCESS_DENIED",
            **context,
        )


class RateLimitError(SecureError):
    """Error when rate limit is exceeded."""

    def __init__(
        self,
        retry_after: Optional[int] = None,
        detail_message: Optional[str] = None,
        **context: Any,
    ):
        """Initialize a rate limit error."""
        public_msg = "Rate limit exceeded"
        if retry_after:
            public_msg += f". Retry after {retry_after} seconds"

        super().__init__(
            public_message=public_msg,
            detail_message=detail_message or public_msg,
            error_code="RATE_LIMIT_EXCEEDED",
            retry_after=retry_after,
            **context,
        )


def sanitize_error_message(error: Exception, include_type: bool = True) -> str:
    """Sanitize an error message for safe display.

    Args:
        error: The exception to sanitize
        include_type: Whether to include the error type

    Returns:
        Sanitized error message

    Examples:
        >>> sanitize_error_message(ValueError("Invalid API key: sk_live_123"))
        'ValueError: Invalid API key: ***'
    """
    if isinstance(error, SecureError):
        return error.public_message

    error_msg = str(error)

    # Patterns to redact
    patterns = [
        (r"password[=:]\s*\S+", "password=***"),
        (r"api[_-]?key[=:]\s*\S+", "api_key=***"),
        (r"token[=:]\s*\S+", "token=***"),
        (r"secret[=:]\s*\S+", "secret=***"),
        (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "***@***.***",
        ),  # emails
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "***.***.***.***"),  # IP addresses
    ]

    import re

    sanitized = error_msg
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    if include_type:
        return f"{type(error).__name__}: {sanitized}"
    return sanitized


def handle_exception(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    log_traceback: bool = True,
) -> SecureError:
    """Handle an exception and convert it to a SecureError.

    Args:
        error: The exception to handle
        context: Additional context for logging
        log_traceback: Whether to log the full traceback

    Returns:
        A SecureError with sanitized information
    """
    if isinstance(error, SecureError):
        error.log()
        return error

    # Determine public message based on error type
    if isinstance(error, ValueError):
        public_message = "Invalid input provided"
    elif isinstance(error, KeyError):
        public_message = "Required field missing"
    elif isinstance(error, FileNotFoundError):
        public_message = "Resource not found"
    elif isinstance(error, PermissionError):
        public_message = "Access denied"
    elif isinstance(error, TimeoutError):
        public_message = "Operation timed out"
    else:
        public_message = "An error occurred while processing your request"

    # Create detailed message for logging
    detail_message = sanitize_error_message(error)

    if log_traceback:
        _LOGGER.error(
            "Exception caught: %s",
            detail_message,
            exc_info=True,
            extra={"context": context or {}},
        )

    secure_error = SecureError(
        public_message=public_message,
        detail_message=detail_message,
        **(context or {}),
    )

    return secure_error


def safe_str(obj: Any, max_length: int = 100) -> str:
    """Safely convert an object to string with length limit.

    Args:
        obj: Object to convert
        max_length: Maximum string length

    Returns:
        Safe string representation
    """
    try:
        s = str(obj)
        if len(s) > max_length:
            s = s[: max_length - 3] + "..."
        return s
    except Exception:
        return f"<{type(obj).__name__} object>"


__all__ = [
    "SecureError",
    "TradingError",
    "DataValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "sanitize_error_message",
    "handle_exception",
    "safe_str",
]
