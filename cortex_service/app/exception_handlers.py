"""Global exception handlers for the cortex API.

This module provides FastAPI exception handlers that convert exceptions
into consistent JSON error responses.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError

from .errors import CortexError, NotFoundError, ValidationError
from .metrics import ERROR_COUNT
from .middleware import get_request_id

logger = logging.getLogger(__name__)


class ErrorResponse:
    """Structured error response format.
    
    Provides a consistent JSON structure for all error responses.
    """
    
    def __init__(
        self,
        code: str,
        message: str,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an error response.
        
        Args:
            code: Machine-readable error code
            message: Human-readable error message
            request_id: Request identifier for tracing
            details: Optional additional error context
        """
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details or {}
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        
        if self.request_id:
            result["error"]["request_id"] = self.request_id
        
        if self.details:
            result["error"]["details"] = self.details
        
        return result


async def cortex_error_handler(request: Request, exc: CortexError) -> JSONResponse:
    """Handle CortexError exceptions.
    
    Args:
        request: The request that caused the error
        exc: The cortex error
        
    Returns:
        JSON error response
    """
    request_id = get_request_id()
    
    # Determine HTTP status code based on error type
    if isinstance(exc, NotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    # Track error metrics
    ERROR_COUNT.labels(error_code=exc.code, endpoint=request.url.path).inc()
    
    # Log error with context
    logger.error(
        "Cortex error occurred",
        extra={
            "request_id": request_id,
            "error_code": exc.code,
            "error_message": exc.message,
            "endpoint": request.url.path,
            "details": exc.details,
        },
        exc_info=exc,
    )
    
    error_response = ErrorResponse(
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        details=exc.details,
    )
    
    return JSONResponse(
        status_code=status_code,
        content=error_response.to_dict(),
    )


async def validation_error_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors.
    
    Args:
        request: The request that caused the error
        exc: The validation error
        
    Returns:
        JSON error response
    """
    request_id = get_request_id()
    
    # Extract validation errors
    validation_errors = []
    for error in exc.errors():
        validation_errors.append({
            "loc": list(error["loc"]),
            "msg": error["msg"],
            "type": error["type"],
        })
    
    # Track error metrics
    ERROR_COUNT.labels(error_code="ValidationError", endpoint=request.url.path).inc()
    
    # Log error
    logger.warning(
        "Validation error occurred",
        extra={
            "request_id": request_id,
            "endpoint": request.url.path,
            "validation_errors": validation_errors,
        },
    )
    
    error_response = ErrorResponse(
        code="ValidationError",
        message="Request validation failed",
        request_id=request_id,
        details={"validation_errors": validation_errors},
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict(),
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Handle SQLAlchemy database errors.
    
    Args:
        request: The request that caused the error
        exc: The database error
        
    Returns:
        JSON error response
    """
    request_id = get_request_id()
    
    # Track error metrics
    ERROR_COUNT.labels(error_code="DatabaseError", endpoint=request.url.path).inc()
    
    # Log error with context
    logger.error(
        "Database error occurred",
        extra={
            "request_id": request_id,
            "endpoint": request.url.path,
            "error": str(exc),
        },
        exc_info=exc,
    )
    
    error_response = ErrorResponse(
        code="DatabaseError",
        message="A database error occurred",
        request_id=request_id,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors.
    
    This is a catch-all handler for errors not handled by more specific handlers.
    
    Args:
        request: The request that caused the error
        exc: The exception
        
    Returns:
        JSON error response
    """
    request_id = get_request_id()
    
    # Track error metrics
    ERROR_COUNT.labels(error_code="InternalError", endpoint=request.url.path).inc()
    
    # Log error with full context
    logger.exception(
        "Unexpected error occurred",
        extra={
            "request_id": request_id,
            "endpoint": request.url.path,
            "error_type": type(exc).__name__,
        },
    )
    
    error_response = ErrorResponse(
        code="InternalError",
        message="An unexpected error occurred",
        request_id=request_id,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


__all__ = [
    "ErrorResponse",
    "cortex_error_handler",
    "generic_error_handler",
    "sqlalchemy_error_handler",
    "validation_error_handler",
]
