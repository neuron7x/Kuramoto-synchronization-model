"""Error taxonomy for the TradePulse Cortex microservice.

This module defines a hierarchy of exception types that represent all
possible error conditions within the cortex service. Using a structured
error taxonomy enables consistent error handling, logging, and API responses.
"""

from __future__ import annotations

from typing import Any


class CortexError(Exception):
    """Base exception for all cortex service errors.
    
    All custom exceptions in the cortex service should inherit from this base
    class to enable unified error handling and consistent API responses.
    
    Attributes:
        message: Human-readable error description
        code: Machine-readable error code for API clients
        details: Optional additional context about the error
    """

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a cortex error.
        
        Args:
            message: Human-readable error description
            code: Machine-readable error code (defaults to class name)
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}


class ConfigurationError(CortexError):
    """Raised when configuration is invalid or cannot be loaded.
    
    This includes missing configuration files, invalid YAML syntax,
    missing required fields, or values that fail validation.
    """


class ValidationError(CortexError):
    """Raised when input validation fails.
    
    This includes invalid request payloads, out-of-range values,
    or data that violates business rules.
    """


class DatabaseError(CortexError):
    """Raised when database operations fail.
    
    This includes connection failures, query execution errors,
    constraint violations, and transient failures.
    """


class RepositoryError(DatabaseError):
    """Raised when repository operations fail.
    
    This is a specialized database error for persistence layer failures.
    """


class NotFoundError(CortexError):
    """Raised when a requested resource does not exist.
    
    This typically results in a 404 response to the client.
    """


class ServiceError(CortexError):
    """Raised when a service-level operation fails.
    
    This includes business logic failures, computation errors,
    and other domain-level exceptions.
    """


class SignalComputationError(ServiceError):
    """Raised when signal computation fails.
    
    This includes empty feature bundles, numerical instability,
    or invalid signal parameters.
    """


class RiskComputationError(ServiceError):
    """Raised when risk computation fails.
    
    This includes invalid exposure data, confidence bounds errors,
    or stress scenario failures.
    """


class RegimeUpdateError(ServiceError):
    """Raised when regime state update fails.
    
    This includes invalid feedback values, confidence calculation errors,
    or regime classification failures.
    """


class ExternalServiceError(CortexError):
    """Raised when communication with external services fails.
    
    This includes timeouts, connection errors, and unexpected responses
    from dependencies.
    """


class RetryExhaustedError(CortexError):
    """Raised when retry attempts are exhausted.
    
    This indicates that an operation failed after multiple retry attempts
    with exponential backoff.
    """


class RateLimitError(CortexError):
    """Raised when rate limits are exceeded.
    
    This indicates that a client has exceeded allowed request rates.
    """


__all__ = [
    "CortexError",
    "ConfigurationError",
    "ValidationError",
    "DatabaseError",
    "RepositoryError",
    "NotFoundError",
    "ServiceError",
    "SignalComputationError",
    "RiskComputationError",
    "RegimeUpdateError",
    "ExternalServiceError",
    "RetryExhaustedError",
    "RateLimitError",
]
