from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

import httpx
import jwt
import pytest

pytest.importorskip("strawberry")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "test-audit-secret")
os.environ.setdefault("TRADEPULSE_OAUTH2_ISSUER", "https://issuer.tradepulse.test")
os.environ.setdefault("TRADEPULSE_OAUTH2_AUDIENCE", "tradepulse-api")
os.environ.setdefault(
    "TRADEPULSE_OAUTH2_JWKS_URI", "https://issuer.tradepulse.test/jwks"
)
os.environ.setdefault("TRADEPULSE_RBAC_AUDIT_SECRET", "test-rbac-secret")

from application.api import security as security_module
from application.api import service as service_module
from application.api.rate_limit import (
    InMemorySlidingWindowBackend,
    SlidingWindowRateLimiter,
)
from application.api.service import DependencyProbeResult, create_app
from application.security.two_factor import generate_totp_code
from application.settings import (
    AdminApiSettings,
    ApiRateLimitSettings,
    ApiSecuritySettings,
    KillSwitchPostgresSettings,
    RateLimitPolicy,
)
from core.config.cli_models import PostgresTLSConfig

API_V1_PREFIX = "/api/v1"
TWO_FACTOR_HEADER = "X-Admin-OTP"
TWO_FACTOR_SECRET = os.environ["TRADEPULSE_TWO_FACTOR_SECRET"]


def _api_v1(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


@pytest.fixture()
def security_context(monkeypatch: pytest.MonkeyPatch) -> Callable[..., str]:
    if hasattr(security_module.get_api_security_settings, "_instance"):
        delattr(security_module.get_api_security_settings, "_instance")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk_dict = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    kid = "unit-test-key"
    jwk_dict.update({"kid": kid, "alg": "RS256", "use": "sig"})

    settings = ApiSecuritySettings(
        oauth2_issuer="https://issuer.tradepulse.test",
        oauth2_audience="tradepulse-api",
        oauth2_jwks_uri="https://issuer.tradepulse.test/jwks",
        trusted_hosts=["testserver", "localhost"],
    )

    monkeypatch.setattr(security_module, "_default_settings_loader", lambda: settings)

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, str] | None:
        assert uri == str(settings.oauth2_jwks_uri)
        if request_kid == kid:
            return jwk_dict
        return None

    monkeypatch.setattr(security_module._jwks_resolver, "get_key", fake_get_key)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def mint_token(
        *,
        subject: str = "unit-user",
        audience: str | None = None,
        issuer: str | None = None,
        lifetime: timedelta = timedelta(minutes=5),
        roles: Sequence[str] | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer or str(settings.oauth2_issuer),
            "aud": audience or settings.oauth2_audience,
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + lifetime).timestamp()),
        }
        if roles:
            payload["roles"] = list(roles)
        return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})

    return mint_token


@pytest.fixture()
def configured_app(
    monkeypatch: pytest.MonkeyPatch,
    security_context: Callable[..., str],
    tmp_path: Path,
) -> FastAPI:
    monkeypatch.delenv("TRADEPULSE_AUDIT_SECRET", raising=False)
    settings = AdminApiSettings(
        audit_secret="unit-audit-secret",
        kill_switch_store_path=tmp_path / "kill_switch.sqlite",
    )
    return create_app(settings=settings)


class _InstrumentedMetricsCollector:
    """Minimal metrics collector capturing health probe observations."""

    def __init__(self) -> None:
        self.enabled = True
        self.latency_samples: list[tuple[str, float]] = []
        self.status_flags: dict[str, bool] = {}

    def observe_health_check_latency(self, name: str, duration: float) -> None:
        self.latency_samples.append((name, duration))

    def set_health_check_status(self, name: str, healthy: bool) -> None:
        self.status_flags[name] = healthy


def test_create_app_requires_secrets(
    monkeypatch: pytest.MonkeyPatch, security_context: Callable[..., str]
) -> None:
    monkeypatch.delenv("TRADEPULSE_AUDIT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="TRADEPULSE_AUDIT_SECRET"):
        create_app()


def test_create_app_uses_postgres_store(
    monkeypatch: pytest.MonkeyPatch,
    security_context: Callable[..., str],
    tmp_path: Path,
) -> None:
    invoked: dict[str, object] = {}

    class DummyStore:
        def __init__(
            self, *args: object, **kwargs: object
        ) -> None:  # pragma: no cover - simple stub
            invoked["kwargs"] = kwargs

        def load(self) -> None:
            return None

    monkeypatch.setattr(service_module, "PostgresKillSwitchStateStore", DummyStore)

    tls_dir = tmp_path / "tls"
    tls_dir.mkdir()
    ca = tls_dir / "ca.pem"
    cert = tls_dir / "client.pem"
    key = tls_dir / "client.key"
    for material in (ca, cert, key):
        material.write_text("dummy", encoding="utf-8")

    settings = AdminApiSettings(
        audit_secret="unit-audit-secret",
        kill_switch_postgres=KillSwitchPostgresSettings(
            dsn="postgresql://user:pass@db/prod?sslmode=verify-full",
            tls=PostgresTLSConfig(ca_file=ca, cert_file=cert, key_file=key),
            min_pool_size=0,
        ),
    )

    app = create_app(settings=settings)

    kill_switch = app.state.risk_manager.kill_switch
    assert isinstance(kill_switch._store, DummyStore)  # type: ignore[attr-defined]
    assert invoked["kwargs"]["pool_min_size"] == 0


def _build_payload() -> dict[str, object]:
    base = datetime(2024, 12, 1, 12, 0, tzinfo=timezone.utc)
    bars = []
    price = 100.0
    for idx in range(60):
        ts = base + timedelta(minutes=idx)
        price += 0.1 if idx % 2 == 0 else -0.05
        bars.append(
            {
                "timestamp": ts.isoformat(),
                "open": price - 0.2,
                "high": price + 0.3,
                "low": price - 0.4,
                "close": price,
                "volume": 1000 + idx * 2,
                "bidVolume": 500 + idx,
                "askVolume": 480 + idx,
                "signedVolume": (-1) ** idx * 20.0,
            }
        )
    return {"symbol": "TEST-USD", "bars": bars}


def _auth_headers(
    token: str,
    *,
    client_cert: bool = False,
    two_factor_code: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if client_cert:
        headers["X-Client-Cert"] = "test-cert"
    if two_factor_code is not None:
        headers[TWO_FACTOR_HEADER] = two_factor_code
    return headers


def _admin_headers(token: str) -> dict[str, str]:
    return _auth_headers(
        token,
        client_cert=True,
        two_factor_code=generate_totp_code(TWO_FACTOR_SECRET),
    )


def test_feature_endpoint_rejects_missing_token(configured_app: FastAPI) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    response = client.post("/features", json=payload)
    assert response.status_code == 401


def test_feature_endpoint_computes_latest_vector(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    app = configured_app
    client = TestClient(app, raise_server_exceptions=False)

    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)

    response = client.post("/features", json=payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TEST-USD"
    features = body["features"]
    for column in [
        "macd",
        "macd_signal",
        "macd_histogram",
        "macd_ema_fast",
        "macd_ema_slow",
    ]:
        assert column in features, f"Expected {column} in feature payload"
        assert features[column] is not None
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["features"] == features
    assert "timestamp" in items[0]
    pagination = body["pagination"]
    assert pagination["limit"] == 1
    assert pagination["returned"] == 1
    assert pagination["cursor"] is None
    assert isinstance(pagination["next_cursor"], str)
    filters = body["filters"]
    assert filters["feature_prefix"] is None
    assert filters["feature_keys"] == []
    assert response.headers["X-Cache-Status"] == "miss"
    assert response.headers["Cache-Control"] == "private, max-age=30"
    assert "Accept" in response.headers.get("Vary", "")

    cached_response = client.post("/features", json=payload, headers=headers)
    assert cached_response.headers["X-Cache-Status"] == "hit"
    assert cached_response.json() == body


def test_versioned_feature_endpoint_supports_idempotency(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)
    headers["Idempotency-Key"] = "feature-idempotency"

    first = client.post(_api_v1("/features"), json=payload, headers=headers)
    assert first.status_code == 200
    assert first.headers["Idempotency-Key"] == "feature-idempotency"
    assert first.headers["X-Cache-Status"] == "miss"
    assert "X-Idempotent-Replay" not in first.headers

    replay = client.post(_api_v1("/features"), json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.headers["Idempotency-Key"] == "feature-idempotency"
    assert replay.headers["X-Idempotent-Replay"] == "true"
    assert replay.headers["ETag"] == first.headers["ETag"]


def test_legacy_feature_endpoint_remains_available(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)

    response = client.post("/v1/features", json=payload, headers=headers)
    assert response.status_code == 200


def test_feature_idempotency_conflict_is_detected(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)
    headers["Idempotency-Key"] = "conflict-key"

    first = client.post(_api_v1("/features"), json=payload, headers=headers)
    assert first.status_code == 200

    mutated = _build_payload()
    mutated["bars"][0]["close"] += 1.0
    conflict = client.post(_api_v1("/features"), json=mutated, headers=headers)
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "ERR_IDEMPOTENCY_CONFLICT"
    assert error["path"] == _api_v1("/features")


def test_prediction_endpoint_returns_signal(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    app = configured_app
    client = TestClient(app, raise_server_exceptions=False)

    payload = _build_payload()
    payload["horizon_seconds"] = 900
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)

    response = client.post("/predictions", json=payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TEST-USD"
    assert body["horizon_seconds"] == 900
    signal = body["signal"]
    assert signal["symbol"] == "TEST-USD"
    assert 0.0 <= signal["confidence"] <= 1.0
    assert "score" in signal["metadata"]
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["signal"]["symbol"] == "TEST-USD"
    assert items[0]["score"] == pytest.approx(body["score"], rel=1e-6)
    pagination = body["pagination"]
    assert pagination["limit"] == 1
    assert pagination["returned"] == 1
    assert isinstance(pagination["next_cursor"], str)
    filters = body["filters"]
    assert filters["actions"] == []
    assert filters["min_confidence"] is None
    assert response.headers["X-Cache-Status"] == "miss"
    assert response.headers["Cache-Control"] == "private, max-age=30"
    assert "Accept" in response.headers.get("Vary", "")

    cached = client.post("/predictions", json=payload, headers=headers)
    assert cached.headers["X-Cache-Status"] == "hit"
    assert cached.json() == body


def test_graphql_interface_exposes_latest_data(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="graphql-user")
    headers = _auth_headers(token)

    feature_payload = _build_payload()
    feature_response = client.post(
        _api_v1("/features"), json=feature_payload, headers=headers
    )
    assert feature_response.status_code == 200

    prediction_payload = _build_payload()
    prediction_payload["horizon_seconds"] = 900
    prediction_response = client.post(
        _api_v1("/predictions"), json=prediction_payload, headers=headers
    )
    assert prediction_response.status_code == 200

    query = """
    query($symbol: String!) {
        latestFeature(symbol: $symbol) {
            symbol
            generatedAt
            features
            snapshots { timestamp }
        }
        latestSignal(symbol: $symbol) {
            symbol
            horizonSeconds
            signal
        }
        recentSignals(limit: 1) {
            symbol
            signal
        }
    }
    """
    graphql_response = client.post(
        "/graphql",
        json={"query": query, "variables": {"symbol": "TEST-USD"}},
        headers=headers,
    )
    assert graphql_response.status_code == 200
    payload = graphql_response.json()["data"]

    latest_feature = payload["latestFeature"]
    assert latest_feature["symbol"] == "TEST-USD"
    assert isinstance(latest_feature["features"], dict)
    assert latest_feature["snapshots"]

    latest_signal = payload["latestSignal"]
    assert latest_signal["symbol"] == "TEST-USD"
    assert latest_signal["horizonSeconds"] == 900
    assert latest_signal["signal"]["symbol"] == "TEST-USD"

    recent_signals = payload["recentSignals"]
    assert len(recent_signals) >= 1
    assert recent_signals[0]["symbol"] == "TEST-USD"


def test_graphql_interface_handles_missing_records(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="graphql-user")
    headers = _auth_headers(token)

    query = """
    query($symbol: String!) {
        latestFeature(symbol: $symbol) { symbol }
        latestSignal(symbol: $symbol) { symbol }
        recentFeatures(limit: 5) { symbol }
    }
    """

    response = client.post(
        "/graphql",
        json={"query": query, "variables": {"symbol": "MISSING"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["latestFeature"] is None
    assert payload["latestSignal"] is None
    assert payload["recentFeatures"] == []


def test_websocket_stream_broadcasts_updates(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="stream-user")
    headers = _auth_headers(token)

    with client.websocket_connect("/ws/stream", headers=headers) as websocket:
        initial = websocket.receive_json()
        assert initial["type"] == "snapshot"
        assert initial["features"] == []
        assert initial["signals"] == []

        feature_payload = _build_payload()
        feature_response = client.post(
            _api_v1("/features"), json=feature_payload, headers=headers
        )
        assert feature_response.status_code == 200
        feature_event = websocket.receive_json()
        assert feature_event["type"] == "feature"
        assert feature_event["symbol"] == "TEST-USD"
        assert "features" in feature_event

        prediction_payload = _build_payload()
        prediction_payload["horizon_seconds"] = 600
        prediction_response = client.post(
            _api_v1("/predictions"), json=prediction_payload, headers=headers
        )
        assert prediction_response.status_code == 200
        signal_event = websocket.receive_json()
        assert signal_event["type"] == "signal"
        assert signal_event["symbol"] == "TEST-USD"
        assert "signal" in signal_event


def test_internal_errors_return_structured_payload(configured_app: FastAPI) -> None:
    app = configured_app

    @app.get("/boom")
    async def boom() -> None:  # pragma: no cover - used in test only
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    payload = response.json()["error"]
    assert payload["code"] == "ERR_INTERNAL"
    assert payload["path"] == "/boom"
    assert payload["message"] == "Unexpected server error."


def test_prediction_endpoint_honours_idempotency(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    payload["horizon_seconds"] = 300
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)
    headers["Idempotency-Key"] = "prediction-key"

    first = client.post(_api_v1("/predictions"), json=payload, headers=headers)
    assert first.status_code == 200
    replay = client.post(_api_v1("/predictions"), json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.headers["X-Idempotent-Replay"] == "true"
    assert replay.json() == first.json()


def test_legacy_prediction_endpoint_remains_available(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    payload["horizon_seconds"] = 300
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)

    response = client.post("/v1/predictions", json=payload, headers=headers)
    assert response.status_code == 200


def test_feature_endpoint_supports_pagination_and_filters(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)

    first_page = client.post(
        "/features?limit=3&featurePrefix=macd", json=payload, headers=headers
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert first_body["pagination"]["limit"] == 3
    for item in first_body["items"]:
        assert all(key.startswith("macd") for key in item["features"])

    cursor = first_body["pagination"]["next_cursor"]
    assert cursor

    second_page = client.post(
        f"/features?limit=3&cursor={cursor}&featurePrefix=macd",
        json=payload,
        headers=headers,
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert second_body["pagination"]["cursor"] == cursor
    assert 0 < second_body["pagination"]["returned"] <= 3
    for item in second_body["items"]:
        assert all(key.startswith("macd") for key in item["features"])


def test_feature_filter_returns_404_for_unknown_prefix(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="feature-user")
    headers = _auth_headers(token)

    response = client.post(
        "/features?featurePrefix=does-not-exist", json=payload, headers=headers
    )
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ERR_FEATURES_FILTER_MISMATCH"


def test_prediction_endpoint_filters_by_action_and_confidence(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)

    baseline = client.post("/predictions?limit=5", json=payload, headers=headers)
    assert baseline.status_code == 200
    baseline_body = baseline.json()
    assert baseline_body["pagination"]["limit"] == 5
    sample_action = baseline_body["items"][0]["signal"]["action"]
    confidence_threshold = max(
        0.0, baseline_body["items"][0]["signal"]["confidence"] - 0.05
    )

    filtered = client.post(
        f"/predictions?limit=5&action={sample_action}&minConfidence={confidence_threshold}",
        json=payload,
        headers=headers,
    )
    assert filtered.status_code == 200
    filtered_body = filtered.json()
    assert filtered_body["filters"]["actions"] == [sample_action]
    assert filtered_body["filters"]["min_confidence"] == pytest.approx(
        confidence_threshold
    )
    for item in filtered_body["items"]:
        assert item["signal"]["action"] == sample_action
        assert item["signal"]["confidence"] >= confidence_threshold


def test_prediction_endpoint_returns_404_when_no_predictions_match(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)

    response = client.post("/predictions?action=exit", json=payload, headers=headers)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ERR_PREDICTIONS_FILTER_MISMATCH"


def test_prediction_endpoint_rejects_invalid_confidence_filter(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    token = security_context(subject="prediction-user")
    headers = _auth_headers(token)

    response = client.post(
        "/predictions?minConfidence=2.5", json=payload, headers=headers
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ERR_INVALID_CONFIDENCE"
    assert error["path"] == "/predictions"


def test_invalid_token_is_rejected(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    payload = _build_payload()
    invalid_headers = _auth_headers("malformed-token")
    response = client.post("/features", json=payload, headers=invalid_headers)
    assert response.status_code == 401


def test_admin_endpoints_require_client_certificate(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="admin-user", roles=("risk:officer",))
    headers = _auth_headers(token)
    response = client.get("/admin/kill-switch", headers=headers)
    assert response.status_code == 401


def test_admin_endpoints_accept_jwt_and_certificate(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="admin-user", roles=("risk:officer",))
    headers = _admin_headers(token)

    response = client.get("/admin/kill-switch", headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    vary_header = response.headers.get("Vary", "")
    assert "Authorization" in vary_header
    assert "Accept" in vary_header

    payload = {"reason": "manual intervention"}
    response = client.post("/admin/kill-switch", headers=headers, json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["kill_switch_engaged"] is True
    assert body["already_engaged"] is False


def test_admin_endpoints_enforce_rbac(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="admin-user")
    headers = _admin_headers(token)
    response = client.post(
        "/admin/kill-switch",
        headers=headers,
        json={"reason": "manual intervention"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "ERR_FORBIDDEN"
    assert body["error"]["path"] == "/admin/kill-switch"
    assert "Insufficient privileges" in body["error"]["message"]


def test_admin_endpoints_require_two_factor(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    token = security_context(subject="admin-user", roles=("risk:officer",))
    payload = {"reason": "manual intervention"}

    missing_headers = _auth_headers(token, client_cert=True)
    response = client.post("/admin/kill-switch", headers=missing_headers, json=payload)
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "ERR_AUTH_REQUIRED"
    assert body["error"]["path"] == "/admin/kill-switch"

    valid_code = generate_totp_code(TWO_FACTOR_SECRET)
    replacement_digit = "0" if valid_code[0] != "0" else "1"
    invalid_code = replacement_digit + valid_code[1:]
    invalid_headers = _auth_headers(
        token, client_cert=True, two_factor_code=invalid_code
    )
    response = client.post("/admin/kill-switch", headers=invalid_headers, json=payload)
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "ERR_AUTH_REQUIRED"
    assert body["error"]["path"] == "/admin/kill-switch"

    success_headers = _admin_headers(token)
    response = client.post("/admin/kill-switch", headers=success_headers, json=payload)
    assert response.status_code == 200


def test_admin_endpoint_rejects_wrong_audience(
    configured_app: FastAPI, security_context: Callable[..., str]
) -> None:
    client = TestClient(configured_app)
    bad_token = security_context(audience="different-audience", roles=("risk:officer",))
    headers = _auth_headers(bad_token, client_cert=True)
    response = client.get("/admin/kill-switch", headers=headers)
    assert response.status_code == 401


def test_client_rate_limit_is_enforced(security_context: Callable[..., str]) -> None:
    rate_settings = ApiRateLimitSettings(
        default_policy=RateLimitPolicy(max_requests=5, window_seconds=60),
        client_policies={
            "feature-user": RateLimitPolicy(max_requests=1, window_seconds=60)
        },
    )
    limiter = SlidingWindowRateLimiter(InMemorySlidingWindowBackend(), rate_settings)
    app = create_app(
        settings=AdminApiSettings(audit_secret="unit-audit-secret"),
        rate_limiter=limiter,
        rate_limit_settings=rate_settings,
    )
    client = TestClient(app)

    payload = _build_payload()
    token = security_context(subject="feature-user")
    response_ok = client.post("/features", json=payload, headers=_auth_headers(token))
    assert response_ok.status_code == 200

    response_limited = client.post(
        "/features", json=payload, headers=_auth_headers(token)
    )
    assert response_limited.status_code == 429

    other_token = security_context(subject="different-user")
    recovery = client.post(
        "/features", json=payload, headers=_auth_headers(other_token)
    )
    assert recovery.status_code == 200


def test_health_probe_reports_ready_state(configured_app: FastAPI) -> None:
    client = TestClient(configured_app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    risk_component = body["components"]["risk_manager"]
    assert risk_component["healthy"] is True
    assert risk_component["status"] == "operational"
    assert "inference_cache" in body["components"]
    assert "client_rate_limiter" in body["components"]


def test_health_probe_emits_metrics_when_collector_present(
    configured_app: FastAPI,
) -> None:
    collector = _InstrumentedMetricsCollector()
    configured_app.state.metrics = collector

    client = TestClient(configured_app)
    response = client.get("/health")

    assert response.status_code == 200
    assert collector.latency_samples, "Health probe should record latency metrics"
    latency_name, duration = collector.latency_samples[-1]
    assert latency_name == "api.overall"
    assert duration >= 0

    assert collector.status_flags.get("api.overall") is True
    component_keys = {
        name for name in collector.status_flags if name.startswith("component.")
    }
    assert component_keys, "Component health metrics should be recorded"


def test_prometheus_metrics_include_api_counters(configured_app: FastAPI) -> None:
    client = TestClient(configured_app)
    response = client.get("/health")
    assert response.status_code == 200

    configured_app.state.metrics.set_process_resource_usage(
        "inference_api", cpu_percent=0.0, memory_bytes=0.0, memory_percent=0.0
    )

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert "tradepulse_api_requests_total" in body
    assert 'route="/health"' in body
    assert "tradepulse_api_request_latency_seconds_count" in body


def test_health_probe_reflects_kill_switch(configured_app: FastAPI) -> None:
    app = configured_app
    app.state.risk_manager.kill_switch.trigger("scheduled maintenance")
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "failed"
    risk = body["components"]["risk_manager"]
    assert risk["healthy"] is False
    assert risk["status"] == "failed"
    assert risk["detail"] == "scheduled maintenance"


def test_health_probe_flags_dependency_failure() -> None:
    probes = {
        "postgres": lambda: DependencyProbeResult(
            healthy=False, detail="connection refused"
        ),
    }
    app = create_app(
        settings=AdminApiSettings(audit_secret="unit-audit-secret"),
        dependency_probes=probes,
    )
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "failed"
    dependency = body["components"]["dependency:postgres"]
    assert dependency["healthy"] is False
    assert dependency["status"] == "failed"
    assert dependency["detail"] == "connection refused"


def test_trusted_host_middleware_blocks_unlisted_hosts(
    monkeypatch: pytest.MonkeyPatch, security_context: Callable[..., str]
) -> None:
    restricted_settings = ApiSecuritySettings(
        oauth2_issuer="https://issuer.tradepulse.test",
        oauth2_audience="tradepulse-api",
        oauth2_jwks_uri="https://issuer.tradepulse.test/jwks",
        trusted_hosts=["api.tradepulse.test"],
    )
    monkeypatch.setattr(
        security_module, "_default_settings_loader", lambda: restricted_settings
    )
    if hasattr(security_module.get_api_security_settings, "_instance"):
        delattr(security_module.get_api_security_settings, "_instance")

    app = create_app(settings=AdminApiSettings(audit_secret="unit-audit-secret"))
    client = TestClient(app)
    payload = _build_payload()
    token = security_context(subject="feature-user")

    bad_host_headers = {**_auth_headers(token), "Host": "attacker.example"}
    denied = client.post("/features", json=payload, headers=bad_host_headers)
    assert denied.status_code == 400

    good_host_headers = {**_auth_headers(token), "Host": "api.tradepulse.test"}
    permitted = client.post("/features", json=payload, headers=good_host_headers)
    assert permitted.status_code == 200


def test_payload_guard_rejects_large_and_suspicious_bodies(
    monkeypatch: pytest.MonkeyPatch, security_context: Callable[..., str]
) -> None:
    tuned_settings = ApiSecuritySettings(
        oauth2_issuer="https://issuer.tradepulse.test",
        oauth2_audience="tradepulse-api",
        oauth2_jwks_uri="https://issuer.tradepulse.test/jwks",
        trusted_hosts=["testserver"],
        max_request_bytes=512,
    )
    monkeypatch.setattr(
        security_module, "_default_settings_loader", lambda: tuned_settings
    )
    if hasattr(security_module.get_api_security_settings, "_instance"):
        delattr(security_module.get_api_security_settings, "_instance")

    app = create_app(settings=AdminApiSettings(audit_secret="unit-audit-secret"))
    client = TestClient(app)
    token = security_context(subject="feature-user")

    oversized_payload = _build_payload()
    oversized_payload["bars"] *= 20
    response_large = client.post(
        "/features",
        json=oversized_payload,
        headers=_auth_headers(token),
    )
    assert response_large.status_code == 413

    suspicious_payload = _build_payload()
    suspicious_payload["symbol"] = "<script>alert(1)</script>"
    suspicious_payload["bars"] = suspicious_payload["bars"][:1]
    response_suspicious = client.post(
        "/features",
        json=suspicious_payload,
        headers=_auth_headers(token),
    )
    assert response_suspicious.status_code == 400


class _DummyWebSocket:
    def __init__(self) -> None:
        self.closed_codes: list[int] = []

    def __hash__(self) -> int:
        return id(self)

    async def close(self, *, code: int) -> None:
        self.closed_codes.append(code)


@pytest.mark.asyncio
async def test_shutdown_hook_marks_app_unhealthy_and_closes_streams() -> None:
    app = create_app(settings=AdminApiSettings(audit_secret="unit-audit-secret"))
    await app.router.startup()
    shutdown_executed = False
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        ready_response = await client.get("/health")
        assert ready_response.status_code == 200

        stream_manager = app.state.stream_manager
        dummy_socket = _DummyWebSocket()
        async with stream_manager._lock:  # type: ignore[attr-defined]
            stream_manager._connections.add(dummy_socket)  # type: ignore[attr-defined]

        try:
            await app.router.shutdown()
            shutdown_executed = True
        finally:
            if not shutdown_executed:
                await app.router.shutdown()

        assert getattr(app.state, "shutting_down", False) is True
        assert dummy_socket.closed_codes == [status.WS_1012_SERVICE_RESTART]
        assert not stream_manager._connections  # type: ignore[attr-defined]

        health_server = app.state.health_server
        if health_server is not None:
            snapshot = health_server.snapshot()
            assert snapshot["ready"] is False
            assert snapshot["live"] is False

        shutdown_response = await client.get("/health")
        assert shutdown_response.status_code == 503
        payload = shutdown_response.json()
        assert payload["status"] == "failed"
        assert payload["components"]["lifecycle"]["status"] == "failed"
