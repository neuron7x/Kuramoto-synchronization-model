from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import HTTPException, status
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from application.api.service import (
    FeatureRequest,
    MarketBar,
    PayloadGuardMiddleware,
    _filter_feature_frame,
    _filter_feature_values,
    _hash_payload,
    _paginate_frame,
    _resolve_ip,
    _validate_idempotency_key,
)


@pytest.fixture()
def sample_frame() -> pd.DataFrame:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    index = [base + timedelta(minutes=idx) for idx in range(5)]
    data = {
        "macd": [0.1 * idx for idx in range(5)],
        "rsi": [50 + idx for idx in range(5)],
    }
    frame = pd.DataFrame(data, index=index)
    frame.index.name = "timestamp"
    return frame


def test_filter_feature_frame_honours_window(sample_frame: pd.DataFrame) -> None:
    start = sample_frame.index[1]
    end = sample_frame.index[3]
    filtered = _filter_feature_frame(sample_frame, start_at=start, end_at=end)
    assert filtered.index.min() >= start
    assert filtered.index.max() <= end
    assert len(filtered) == 3


def test_paginate_frame_respects_cursor(sample_frame: pd.DataFrame) -> None:
    page, next_cursor = _paginate_frame(sample_frame, limit=2, cursor=None)
    assert len(page) == 2
    assert next_cursor is not None
    assert next_cursor.tzinfo == timezone.utc

    older_cursor = next_cursor - timedelta(minutes=1)
    page2, next_cursor2 = _paginate_frame(sample_frame, limit=2, cursor=older_cursor)
    assert len(page2) <= 2
    if not page2.empty:
        assert page2.index.max() < older_cursor
    assert next_cursor2 is None or next_cursor2 <= older_cursor


def test_filter_feature_values_applies_prefix_and_keys() -> None:
    series = pd.Series(
        {
            "macd": 1.2,
            "macd_signal": 0.8,
            "macd_histogram": -0.2,
            "volume": 1200,
        }
    )
    values = _filter_feature_values(
        series, feature_prefix="macd", feature_keys=("macd", "macd_signal")
    )
    assert set(values.keys()) == {"macd", "macd_signal"}
    assert values["macd"] == pytest.approx(1.2)


def test_hash_payload_includes_extra_context() -> None:
    request = FeatureRequest(
        symbol="BTC-USD",
        bars=[
            MarketBar(
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                open=42000.0,
                high=42100.0,
                low=41900.0,
                close=42050.0,
            )
        ],
    )
    baseline = _hash_payload("feature", request)
    assert baseline.startswith("feature:")

    with_extra = _hash_payload("feature", request, extra={"cursor": "123"})
    assert with_extra != baseline
    again = _hash_payload("feature", request, extra={"cursor": "123"})
    assert again == with_extra


def test_validate_idempotency_key_guards_invalid_inputs() -> None:
    assert _validate_idempotency_key("  valid-key  ") == "valid-key"

    with pytest.raises(HTTPException):
        _validate_idempotency_key("")
    with pytest.raises(HTTPException):
        _validate_idempotency_key(" ")
    with pytest.raises(HTTPException):
        _validate_idempotency_key("a" * 129)
    with pytest.raises(HTTPException):
        _validate_idempotency_key("illegal!*key")


def test_payload_guard_middleware_blocks_suspicious_content() -> None:
    async def ingest(request):  # pragma: no cover - executed via TestClient
        body = await request.json()
        return JSONResponse({"accepted": True, "echo": body})

    app = Starlette(routes=[Route("/ingest", ingest, methods=["POST"])])
    app.add_middleware(
        PayloadGuardMiddleware,
        max_body_bytes=512,
        suspicious_keys={"password", "api_key"},
        suspicious_substrings=("drop table", "<script"),
    )

    client = TestClient(app)

    ok_response = client.post("/ingest", json={"message": "hello"})
    assert ok_response.status_code == status.HTTP_200_OK
    assert ok_response.json()["accepted"] is True

    suspicious_key = client.post("/ingest", json={"password": "secret"})
    assert suspicious_key.status_code == status.HTTP_400_BAD_REQUEST

    suspicious_value = client.post("/ingest", json={"note": "Please DROP TABLE users;"})
    assert suspicious_value.status_code == status.HTTP_400_BAD_REQUEST

    too_large = client.post("/ingest", json={"payload": "x" * 600})
    assert too_large.status_code == status.HTTP_413_CONTENT_TOO_LARGE


def test_payload_guard_middleware_handles_invalid_json() -> None:
    async def handler(request):  # pragma: no cover - executed via TestClient
        body = await request.json()
        return JSONResponse(body)

    app = Starlette(routes=[Route("/test", handler, methods=["POST"])])
    app.add_middleware(
        PayloadGuardMiddleware,
        max_body_bytes=256,
        suspicious_keys=set(),
        suspicious_substrings=(),
    )

    client = TestClient(app)
    response = client.post(
        "/test", content=b"not-json", headers={"content-type": "application/json"}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Malformed JSON payload."


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"x-forwarded-for": "203.0.113.4"}, "203.0.113.4"),
        ({"x-forwarded-for": " 198.51.100.10, 203.0.113.5"}, "198.51.100.10"),
        ({"x-real-ip": "192.0.2.8"}, "192.0.2.8"),
    ],
)
def test_resolve_ip_prefers_forwarded_headers(headers, expected) -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(key.encode(), value.encode()) for key, value in headers.items()],
        "client": ("127.0.0.1", 12345),
    }

    async def receive():  # pragma: no cover - handshake stub
        return {"type": "http.request", "body": b""}

    async def send(message):  # pragma: no cover - handshake stub
        pass

    request = Request(scope, receive=receive)
    assert _resolve_ip(request) == expected


def test_resolve_ip_falls_back_to_client_host() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": ("198.18.0.1", 443),
    }

    async def receive():  # pragma: no cover - handshake stub
        return {"type": "http.request", "body": b""}

    async def send(message):  # pragma: no cover - handshake stub
        pass

    request = Request(scope, receive=receive)
    assert _resolve_ip(request) == "198.18.0.1"
