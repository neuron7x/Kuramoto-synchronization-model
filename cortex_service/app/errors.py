"""Unified error taxonomy for the cortex service."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class CortexError(Exception):
    """Base exception for all cortex service errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the error with structured context.

        Args:
            message: Human-readable error description
            code: Machine-readable error code for client handling
            status_code: HTTP status code to return
            details: Optional additional context
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ConfigurationError(CortexError):
    """Raised when configuration is invalid or cannot be loaded."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize configuration error."""
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=details,
        )


class ValidationError(CortexError):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize validation error."""
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class NotFoundError(CortexError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize not found error."""
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class DatabaseError(CortexError):
    """Raised when a database operation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize database error."""
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=details,
        )


class ComputationError(CortexError):
    """Raised when a computation fails due to invalid input or state."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize computation error."""
        super().__init__(
            message=message,
            code="COMPUTATION_ERROR",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details=details,
        )


__all__ = [
    "CortexError",
    "ConfigurationError",
    "ValidationError",
    "NotFoundError",
    "DatabaseError",
    "ComputationError",
]
