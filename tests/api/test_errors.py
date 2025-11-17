from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from application.api.errors import (
    ApiErrorCode,
    ErrorResponse,
    register_exception_handlers,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/custom")
    async def custom_error() -> None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": ApiErrorCode.FEATURES_INVALID,
                "message": "Feature payload invalid.",
                "meta": {"field": "features"},
            },
        )

    @app.get("/default")
    async def default_error() -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return app


def test_exception_handler_preserves_custom_payload() -> None:
    client = TestClient(_build_app())

    response = client.get("/custom")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    payload = ErrorResponse.model_validate(response.json())
    assert payload.error.code is ApiErrorCode.FEATURES_INVALID
    assert payload.error.message == "Feature payload invalid."
    assert payload.error.meta == {"field": "features"}
    assert payload.error.path == "/custom"


def test_exception_handler_uses_default_mapping() -> None:
    client = TestClient(_build_app())

    response = client.get("/default")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    payload = ErrorResponse.model_validate(response.json())
    assert payload.error.code is ApiErrorCode.NOT_FOUND
    assert payload.error.message == HTTPStatus(status.HTTP_404_NOT_FOUND).phrase
    assert payload.error.meta is None
    assert payload.error.path == "/default"


@pytest.mark.parametrize(
    "detail",
    [
        pytest.param({"code": "ERR_UNKNOWN", "message": "oops"}, id="unknown-code"),
        pytest.param("explicit-message", id="string-detail"),
        pytest.param({}, id="empty-dict"),
    ],
)
def test_exception_handler_gracefully_handles_unexpected_details(detail: Any) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:  # pragma: no cover - invoked via test client
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    client = TestClient(app)
    response = client.get("/boom")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = ErrorResponse.model_validate(response.json())
    assert payload.error.code is ApiErrorCode.BAD_REQUEST
    assert payload.error.path == "/boom"
    assert payload.error.message
