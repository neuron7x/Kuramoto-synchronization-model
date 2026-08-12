# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage tests for application.api.errors."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from application.api.errors import (
    COMMON_ERROR_RESPONSES,
    DEFAULT_ERROR_CODES,
    HTTP_422_UNPROCESSABLE,
    ApiErrorCode,
    ErrorPayload,
    ErrorResponse,
    _resolve_error_code,
    build_error_envelope,
    register_exception_handlers,
)


class TestResolveErrorCode:
    def test_passthrough_enum(self) -> None:
        assert (
            _resolve_error_code(ApiErrorCode.NOT_FOUND, ApiErrorCode.INTERNAL)
            is ApiErrorCode.NOT_FOUND
        )

    def test_valid_string(self) -> None:
        assert (
            _resolve_error_code("ERR_NOT_FOUND", ApiErrorCode.INTERNAL)
            is ApiErrorCode.NOT_FOUND
        )

    def test_invalid_string_falls_back(self) -> None:
        assert (
            _resolve_error_code("NOT_A_CODE", ApiErrorCode.INTERNAL)
            is ApiErrorCode.INTERNAL
        )

    def test_non_string_non_enum_falls_back(self) -> None:
        assert _resolve_error_code(123, ApiErrorCode.BAD_REQUEST) is ApiErrorCode.BAD_REQUEST
        assert _resolve_error_code(None, ApiErrorCode.BAD_REQUEST) is ApiErrorCode.BAD_REQUEST


class TestModelsAndConstants:
    def test_error_payload_and_response(self) -> None:
        payload = ErrorPayload(
            code=ApiErrorCode.NOT_FOUND,
            message="missing",
            path="/x",
            meta={"a": 1},
        )
        env = ErrorResponse(error=payload)
        dumped = env.model_dump(mode="json")
        assert dumped["error"]["code"] == "ERR_NOT_FOUND"
        assert dumped["error"]["meta"] == {"a": 1}

    def test_error_payload_meta_optional(self) -> None:
        payload = ErrorPayload(code=ApiErrorCode.INTERNAL, message="m", path="/p")
        assert payload.meta is None

    def test_default_error_codes_mapping(self) -> None:
        assert DEFAULT_ERROR_CODES[status.HTTP_404_NOT_FOUND] is ApiErrorCode.NOT_FOUND
        assert DEFAULT_ERROR_CODES[HTTP_422_UNPROCESSABLE] is ApiErrorCode.VALIDATION_FAILED

    def test_common_error_responses_shape(self) -> None:
        assert status.HTTP_400_BAD_REQUEST in COMMON_ERROR_RESPONSES
        assert COMMON_ERROR_RESPONSES[status.HTTP_400_BAD_REQUEST]["model"] is ErrorResponse

    def test_http_422_constant(self) -> None:
        assert HTTP_422_UNPROCESSABLE == 422


class TestBuildErrorEnvelope:
    def test_envelope_json_structure(self) -> None:
        resp = build_error_envelope(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="nope",
            path="/thing",
            meta={"id": "1"},
        )
        assert resp.status_code == 404
        import json

        body = json.loads(resp.body)
        assert body["error"]["code"] == "ERR_NOT_FOUND"
        assert body["error"]["message"] == "nope"
        assert body["error"]["path"] == "/thing"
        assert body["error"]["meta"] == {"id": "1"}

    def test_envelope_default_meta_none(self) -> None:
        resp = build_error_envelope(
            status_code=500,
            code=ApiErrorCode.INTERNAL,
            message="boom",
            path="/x",
        )
        import json

        body = json.loads(resp.body)
        assert body["error"]["meta"] is None


class _Body(BaseModel):
    symbol: str
    count: int


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    # Provide a custom default_codes override to exercise the merge branch.
    register_exception_handlers(
        app, default_codes={status.HTTP_418_IM_A_TEAPOT: ApiErrorCode.BAD_REQUEST}
    )

    @app.post("/validate")
    async def validate(body: _Body) -> dict[str, str]:
        return {"ok": body.symbol}

    @app.get("/http-str")
    async def http_str() -> None:
        raise HTTPException(status_code=404, detail="Resource gone")

    @app.get("/http-dict")
    async def http_dict() -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ERR_FEATURES_EMPTY",
                "message": "no features",
                "meta": {"hint": "add features"},
            },
        )

    @app.get("/http-dict-detailkey")
    async def http_dict_detailkey() -> None:
        raise HTTPException(
            status_code=400,
            detail={"detail": "fallback message via detail key"},
        )

    @app.get("/http-dict-nomessage")
    async def http_dict_nomessage() -> None:
        # dict with no message/detail -> phrase fallback; meta not a dict -> None
        raise HTTPException(status_code=404, detail={"meta": ["not", "a", "dict"]})

    @app.get("/http-nodetail")
    async def http_nodetail() -> None:
        raise HTTPException(status_code=503, detail=None)

    @app.get("/http-list-detail")
    async def http_list_detail() -> None:
        # detail neither dict nor str -> message stays None -> phrase fallback
        # (exercises the 235->237 branch), and _make_json_safe recurses the list.
        raise HTTPException(status_code=400, detail=["a", "b"])

    @app.get("/http-nonserializable-meta")
    async def http_nonserializable_meta() -> None:
        # A value that is not str/int/float/bool/None/Mapping/Sequence forces
        # the _make_json_safe str() fallback (line 202).
        raise HTTPException(
            status_code=400,
            detail={"message": "weird", "meta": {"obj": {1, 2, 3}}},
        )

    @app.get("/http-unknown-status")
    async def http_unknown_status() -> None:
        # status code not in error_codes map -> INTERNAL default.
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="pay")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    return TestClient(app, raise_server_exceptions=False)


class TestExceptionHandlers:
    def test_request_validation_handler(self, client: TestClient) -> None:
        resp = client.post("/validate", json={"count": "not-an-int"})
        assert resp.status_code == HTTP_422_UNPROCESSABLE
        body = resp.json()
        assert body["error"]["code"] == ApiErrorCode.VALIDATION_FAILED.value
        assert body["error"]["message"] == "Invalid request payload."
        assert body["error"]["path"] == "/validate"
        assert isinstance(body["error"]["meta"]["errors"], list)
        # Mirrored detail key present for legacy consumers.
        assert isinstance(body["detail"], list)

    def test_http_exception_string_detail(self, client: TestClient) -> None:
        resp = client.get("/http-str")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == ApiErrorCode.NOT_FOUND.value
        assert body["error"]["message"] == "Resource gone"
        assert body["detail"] == "Resource gone"

    def test_http_exception_dict_detail(self, client: TestClient) -> None:
        resp = client.get("/http-dict")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == ApiErrorCode.FEATURES_EMPTY.value
        assert body["error"]["message"] == "no features"
        assert body["error"]["meta"] == {"hint": "add features"}

    def test_http_exception_dict_detail_key_message(self, client: TestClient) -> None:
        resp = client.get("/http-dict-detailkey")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["message"] == "fallback message via detail key"

    def test_http_exception_dict_no_message_phrase_fallback(self, client: TestClient) -> None:
        resp = client.get("/http-dict-nomessage")
        assert resp.status_code == 404
        body = resp.json()
        # Falls back to HTTPStatus phrase.
        assert body["error"]["message"] == HTTPStatus(404).phrase
        # meta was not a dict -> coerced to None.
        assert body["error"]["meta"] is None

    def test_http_exception_no_detail_phrase(self, client: TestClient) -> None:
        resp = client.get("/http-nodetail")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["message"] == HTTPStatus(503).phrase
        assert body["error"]["code"] == ApiErrorCode.INTERNAL.value
        # Starlette backfills a None detail with the status phrase, so the
        # mirrored detail key carries that phrase.
        assert body["detail"] == HTTPStatus(503).phrase

    def test_http_exception_list_detail_phrase_fallback(self, client: TestClient) -> None:
        resp = client.get("/http-list-detail")
        assert resp.status_code == 400
        body = resp.json()
        # Non-dict/non-str detail: message falls back to the status phrase.
        assert body["error"]["message"] == HTTPStatus(400).phrase
        assert body["detail"] == ["a", "b"]

    def test_http_exception_nonserializable_meta_str_fallback(
        self, client: TestClient
    ) -> None:
        resp = client.get("/http-nonserializable-meta")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["message"] == "weird"
        # The set was coerced to its str() representation.
        assert isinstance(body["detail"]["meta"]["obj"], str)

    def test_http_exception_unknown_status_defaults_internal(self, client: TestClient) -> None:
        resp = client.get("/http-unknown-status")
        assert resp.status_code == 402
        body = resp.json()
        assert body["error"]["code"] == ApiErrorCode.INTERNAL.value

    def test_unhandled_exception_handler(self, client: TestClient) -> None:
        resp = client.get("/boom")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        body = resp.json()
        assert body["error"]["code"] == ApiErrorCode.INTERNAL.value
        assert body["error"]["message"] == "Unexpected server error."
        assert body["error"]["path"] == "/boom"


def test_register_without_default_codes() -> None:
    # Exercise the branch where default_codes is None (falsy).
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/x")
    async def x() -> None:
        raise HTTPException(status_code=401, detail="nope")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/x")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == ApiErrorCode.AUTH_REQUIRED.value
