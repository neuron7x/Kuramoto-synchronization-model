"""Shared error-handling primitives for TradePulse APIs."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from enum import Enum
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

LOGGER = logging.getLogger("tradepulse.api.errors")

# Prefer the modern Starlette/FastAPI constant while avoiding deprecated access.
HTTP_422_UNPROCESSABLE = int(
    getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY)
)


class ApiErrorCode(str, Enum):
    """Stable error codes returned by the public HTTP APIs."""

    BAD_REQUEST = "ERR_BAD_REQUEST"
    AUTH_REQUIRED = "ERR_AUTH_REQUIRED"
    FORBIDDEN = "ERR_FORBIDDEN"
    NOT_FOUND = "ERR_NOT_FOUND"
    RATE_LIMIT = "ERR_RATE_LIMIT"
    VALIDATION_FAILED = "ERR_VALIDATION_FAILED"
    UNPROCESSABLE = "ERR_UNPROCESSABLE"
    INTERNAL = "ERR_INTERNAL"
    FEATURES_EMPTY = "ERR_FEATURES_EMPTY"
    FEATURES_MISSING = "ERR_FEATURES_MISSING"
    FEATURES_INVALID = "ERR_FEATURES_INVALID"
    FEATURES_FILTER_MISMATCH = "ERR_FEATURES_FILTER_MISMATCH"
    INVALID_CURSOR = "ERR_INVALID_CURSOR"
    INVALID_CONFIDENCE = "ERR_INVALID_CONFIDENCE"
    PREDICTIONS_FILTER_MISMATCH = "ERR_PREDICTIONS_FILTER_MISMATCH"
    IDEMPOTENCY_CONFLICT = "ERR_IDEMPOTENCY_CONFLICT"
    IDEMPOTENCY_INVALID = "ERR_IDEMPOTENCY_INVALID"


DEFAULT_ERROR_CODES: dict[int, ApiErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ApiErrorCode.BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ApiErrorCode.AUTH_REQUIRED,
    status.HTTP_403_FORBIDDEN: ApiErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ApiErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ApiErrorCode.IDEMPOTENCY_CONFLICT,
    HTTP_422_UNPROCESSABLE: ApiErrorCode.VALIDATION_FAILED,
    status.HTTP_429_TOO_MANY_REQUESTS: ApiErrorCode.RATE_LIMIT,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ApiErrorCode.INTERNAL,
    status.HTTP_503_SERVICE_UNAVAILABLE: ApiErrorCode.INTERNAL,
}


def _resolve_error_code(value: Any, default: ApiErrorCode) -> ApiErrorCode:
    if isinstance(value, ApiErrorCode):
        return value
    if isinstance(value, str):
        try:
            return ApiErrorCode(value)
        except ValueError:
            return default
    return default


class ErrorPayload(BaseModel):
    """Canonical error payload returned by the HTTP APIs."""

    code: ApiErrorCode = Field(..., description="Stable application error code.")
    message: str = Field(..., description="Human-readable description of the error.")
    path: str = Field(..., description="Request path that triggered the error.")
    meta: dict[str, Any] | None = Field(
        default=None,
        description="Optional machine-parsable context for troubleshooting.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "code": ApiErrorCode.VALIDATION_FAILED.value,
                    "message": "Invalid request payload.",
                    "path": "/v1/features",
                    "meta": {
                        "errors": [
                            {
                                "type": "missing",
                                "loc": ["body", "symbol"],
                                "msg": "Field required",
                            }
                        ]
                    },
                }
            ]
        },
    )


class ErrorResponse(BaseModel):
    """Envelope structuring error responses."""

    error: ErrorPayload

    model_config = ConfigDict(populate_by_name=True)


COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorResponse,
        "description": "Request payload failed validation or business rules.",
    },
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication token missing or invalid.",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks sufficient privileges.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Requested resource could not be located.",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Idempotency key conflict detected for the supplied payload.",
    },
    HTTP_422_UNPROCESSABLE: {
        "model": ErrorResponse,
        "description": "Payload schema is syntactically valid but semantically incorrect.",
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "Client exceeded configured rate limits.",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Unexpected server-side failure.",
    },
}


def register_exception_handlers(
    app: FastAPI,
    *,
    default_codes: Mapping[int, ApiErrorCode] | None = None,
) -> None:
    """Install consistent exception handlers on the provided FastAPI app."""

    error_codes = dict(DEFAULT_ERROR_CODES)
    if default_codes:
        error_codes.update(default_codes)

    def _make_json_safe(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Mapping):
            return {key: _make_json_safe(item) for key, item in value.items()}
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return [_make_json_safe(item) for item in value]
        return str(value)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = _make_json_safe(exc.errors())
        error_list = errors if isinstance(errors, list) else [errors]
        payload = ErrorPayload(
            code=ApiErrorCode.VALIDATION_FAILED,
            message="Invalid request payload.",
            path=request.url.path,
            meta={"errors": error_list},
        )
        content = ErrorResponse(error=payload).model_dump(mode="json")
        content["detail"] = error_list
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=content,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        default_code = error_codes.get(exc.status_code, ApiErrorCode.INTERNAL)
        detail = exc.detail
        serializable_detail = _make_json_safe(detail) if detail is not None else None
        message: str | None = None
        meta: Any | None = None
        code = default_code
        if isinstance(detail, dict):
            code = _resolve_error_code(detail.get("code"), default_code)
            message = detail.get("message") or detail.get("detail")
            meta = detail.get("meta")
        elif isinstance(detail, str):
            message = detail
        if not message:
            try:
                message = HTTPStatus(exc.status_code).phrase
            except ValueError:  # pragma: no cover - defensive
                message = "An error occurred"

        meta_payload: dict[str, Any] | None = meta if isinstance(meta, dict) else None
        payload = ErrorPayload(
            code=code,
            message=message,
            path=request.url.path,
            meta=meta_payload,
        )
        content = ErrorResponse(error=payload).model_dump(mode="json")
        if serializable_detail is not None:
            content["detail"] = serializable_detail
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        LOGGER.exception(
            "Unhandled error while processing request",
            extra={"path": request.url.path},
        )
        payload = ErrorPayload(
            code=ApiErrorCode.INTERNAL,
            message="Unexpected server error.",
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=payload).model_dump(mode="json"),
        )


__all__ = [
    "ApiErrorCode",
    "COMMON_ERROR_RESPONSES",
    "DEFAULT_ERROR_CODES",
    "ErrorPayload",
    "ErrorResponse",
    "register_exception_handlers",
]
