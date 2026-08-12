# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt.algorithms import OKPAlgorithm, RSAAlgorithm
from starlette.requests import Request

os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")
os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://issuer.geosync.test")
os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
os.environ.setdefault("GEOSYNC_OAUTH2_JWKS_URI", "https://issuer.geosync.test/jwks")

from application.api.security import (
    get_api_security_settings,
    require_two_factor,
    verify_request_identity,
)
from application.secrets.manager import SecretManagerError
from application.security.two_factor import generate_totp_code
from application.settings import ApiSecuritySettings
from src.admin.remote_control import AdminIdentity

TWO_FACTOR_HEADER = "X-Admin-OTP"
TWO_FACTOR_SECRET = os.environ["GEOSYNC_TWO_FACTOR_SECRET"]


@dataclass(slots=True)
class OAuthContext:
    mint_token: Callable[..., str]
    settings: ApiSecuritySettings
    kid: str
    jwk_dict: dict[str, Any]
    get_key_calls: Callable[[], int]


@pytest.fixture()
def oauth2_context(monkeypatch: pytest.MonkeyPatch) -> OAuthContext:
    if hasattr(get_api_security_settings, "_instance"):
        delattr(get_api_security_settings, "_instance")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk_dict = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    kid = "unit-test-kid"
    jwk_dict.update({"kid": kid, "alg": "RS256", "use": "sig"})

    settings = ApiSecuritySettings(
        oauth2_issuer="https://issuer.geosync.test",
        oauth2_audience="geosync-api",
        oauth2_jwks_uri="https://issuer.geosync.test/jwks",
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    call_count = 0

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        nonlocal call_count
        call_count += 1
        assert uri == str(settings.oauth2_jwks_uri)
        if request_kid == kid:
            return jwk_dict
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    def mint_token(
        *,
        subject: str = "unit-user",
        audience: str | None = None,
        issuer: str | None = None,
        kid_override: str | None = None,
        include_subject: bool = True,
        lifetime: timedelta = timedelta(minutes=5),
    ) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "iss": issuer or str(settings.oauth2_issuer),
            "aud": audience or settings.oauth2_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + lifetime).timestamp()),
        }
        if include_subject:
            payload["sub"] = subject
        headers: dict[str, Any] = {"alg": "RS256"}
        headers["kid"] = kid_override or kid
        return jwt.encode(payload, private_pem, algorithm="RS256", headers=headers)

    return OAuthContext(
        mint_token=mint_token,
        settings=settings,
        kid=kid,
        jwk_dict=jwk_dict,
        get_key_calls=lambda: call_count,
    )


def _make_request(
    *, headers: dict[str, str] | None = None, scope_cert: dict[str, Any] | None = None
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin",
        "headers": [],
    }
    if headers:
        scope["headers"] = [
            (key.lower().encode("ascii"), value.encode("utf-8")) for key, value in headers.items()
        ]
    if scope_cert is not None:
        scope["client_cert"] = scope_cert

    async def receive() -> dict[str, Any]:  # pragma: no cover - Starlette protocol hook
        return {"type": "http.request"}

    return Request(scope, receive)


@pytest.mark.anyio
async def test_valid_token_populates_identity_context(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(subject="feature-user")
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "feature-user"
    assert request.state.token_claims["sub"] == "feature-user"
    assert not hasattr(request.state, "client_certificate")
    assert oauth2_context.get_key_calls() == 1


@pytest.mark.anyio
async def test_missing_credentials_are_rejected(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity()
    request = _make_request()

    with pytest.raises(HTTPException) as exc:
        await dependency(request, None, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Bearer token required for this endpoint."


@pytest.mark.anyio
async def test_unknown_signing_key_is_rejected(oauth2_context: OAuthContext) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(kid_override="different-key")
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Bearer token signed by unknown key."


@pytest.mark.anyio
async def test_missing_subject_claim_is_rejected(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(subject="")
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Bearer token is missing the subject claim."


@pytest.mark.anyio
async def test_certificate_required_but_missing_is_rejected(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity(require_client_certificate=True)
    token = oauth2_context.mint_token()
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Mutual TLS client certificate required."


@pytest.mark.anyio
async def test_disallowed_algorithm_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if hasattr(get_api_security_settings, "_instance"):
        delattr(get_api_security_settings, "_instance")

    settings = ApiSecuritySettings(
        oauth2_issuer="https://issuer.geosync.test",
        oauth2_audience="geosync-api",
        oauth2_jwks_uri="https://issuer.geosync.test/jwks",
    )

    kid = "oct-key"
    secret = b"shared-secret-value"
    jwk_dict = {
        "kty": "oct",
        "kid": kid,
        "alg": "HS256",
        "use": "sig",
        "k": base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii"),
    }

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(settings.oauth2_jwks_uri)
        if request_kid == kid:
            return jwk_dict
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    now = datetime.now(timezone.utc)
    payload = {
        "iss": str(settings.oauth2_issuer),
        "aud": settings.oauth2_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "sub": "oct-user",
    }

    token = jwt.encode(payload, secret, algorithm="HS256", headers={"kid": kid})
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    dependency = verify_request_identity()

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Unsupported bearer token signing algorithm."


@pytest.mark.anyio
async def test_oct_key_succeeds_when_algorithm_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if hasattr(get_api_security_settings, "_instance"):
        delattr(get_api_security_settings, "_instance")

    settings = ApiSecuritySettings(
        oauth2_algorithms=("HS256",),
        oauth2_issuer="https://issuer.geosync.test",
        oauth2_audience="geosync-api",
        oauth2_jwks_uri="https://issuer.geosync.test/jwks",
    )

    kid = "oct-key"
    secret = b"another-shared-secret"
    jwk_dict = {
        "kty": "oct",
        "kid": kid,
        "alg": "HS256",
        "use": "sig",
        "k": base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii"),
    }

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(settings.oauth2_jwks_uri)
        if request_kid == kid:
            return jwk_dict
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    now = datetime.now(timezone.utc)
    payload = {
        "iss": str(settings.oauth2_issuer),
        "aud": settings.oauth2_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "sub": "oct-enabled-user",
    }

    token = jwt.encode(payload, secret, algorithm="HS256", headers={"kid": kid})
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    dependency = verify_request_identity()

    identity = await dependency(request, credentials, settings)

    assert identity.subject == "oct-enabled-user"
    assert request.state.token_claims["sub"] == "oct-enabled-user"


@pytest.mark.anyio
async def test_eddsa_algorithm_preserves_canonical_casing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if hasattr(get_api_security_settings, "_instance"):
        delattr(get_api_security_settings, "_instance")

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    jwk_dict = OKPAlgorithm.to_jwk(public_key, as_dict=True)
    kid = "eddsa-key"
    jwk_dict.update({"kid": kid, "alg": "EdDSA", "use": "sig"})

    settings = ApiSecuritySettings(
        oauth2_algorithms=("EdDSA",),
        oauth2_issuer="https://issuer.geosync.test",
        oauth2_audience="geosync-api",
        oauth2_jwks_uri="https://issuer.geosync.test/jwks",
    )

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(settings.oauth2_jwks_uri)
        if request_kid == kid:
            return jwk_dict
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    now = datetime.now(timezone.utc)
    payload = {
        "iss": str(settings.oauth2_issuer),
        "aud": settings.oauth2_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "sub": "eddsa-user",
    }

    token = jwt.encode(payload, private_key, algorithm="EdDSA", headers={"kid": kid})
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    dependency = verify_request_identity()

    identity = await dependency(request, credentials, settings)

    assert identity.subject == "eddsa-user"
    assert request.state.token_claims["sub"] == "eddsa-user"


@pytest.mark.anyio
async def test_jwk_algorithm_mismatch_is_rejected(
    oauth2_context: OAuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    mismatched = dict(oauth2_context.jwk_dict)
    mismatched["alg"] = "RS512"

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(oauth2_context.settings.oauth2_jwks_uri)
        if request_kid == oauth2_context.kid:
            return mismatched
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Signing key metadata does not match token algorithm."


@pytest.mark.anyio
async def test_non_signature_key_use_is_rejected(
    oauth2_context: OAuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    non_sig = dict(oauth2_context.jwk_dict)
    non_sig["use"] = "enc"

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(oauth2_context.settings.oauth2_jwks_uri)
        if request_kid == oauth2_context.kid:
            return non_sig
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Signing key is not authorised for signature validation."


@pytest.mark.anyio
async def test_key_type_mismatch_is_rejected(
    oauth2_context: OAuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    wrong_type = dict(oauth2_context.jwk_dict)
    wrong_type["kty"] = "oct"

    async def fake_get_key(uri: str, request_kid: str) -> dict[str, Any] | None:
        assert uri == str(oauth2_context.settings.oauth2_jwks_uri)
        if request_kid == oauth2_context.kid:
            return wrong_type
        return None

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Signing key type is incompatible with bearer token algorithm."


@pytest.mark.anyio
async def test_certificate_from_header_is_accepted(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity(require_client_certificate=True)
    token = oauth2_context.mint_token(subject="admin-user")
    request = _make_request(headers={"X-Client-Cert": "client-cert"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "admin-user"
    assert request.state.client_certificate == {"pem": "client-cert"}


@pytest.mark.anyio
async def test_certificate_from_scope_is_accepted(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity(require_client_certificate=True)
    token = oauth2_context.mint_token(subject="scope-user")
    request = _make_request(scope_cert={"serial": "01"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "scope-user"
    assert request.state.client_certificate == {"serial": "01"}


@pytest.mark.anyio
async def test_preexisting_state_certificate_is_preserved(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity(require_client_certificate=True)
    token = oauth2_context.mint_token(subject="state-user")
    request = _make_request()
    request.state.client_certificate = {"thumbprint": "abc123"}
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "state-user"
    assert request.state.client_certificate == {"thumbprint": "abc123"}


@pytest.mark.anyio
async def test_certificate_scope_takes_precedence_over_header(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity(require_client_certificate=True)
    token = oauth2_context.mint_token(subject="priority-user")
    request = _make_request(
        headers={"X-Client-Cert": "header-cert"},
        scope_cert={"serial": "scope-cert"},
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "priority-user"
    assert request.state.client_certificate == {"serial": "scope-cert"}


@pytest.mark.anyio
async def test_certificate_is_recorded_when_not_required(
    oauth2_context: OAuthContext,
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(subject="optional-cert-user")
    request = _make_request(headers={"X-Client-Cert": "header-cert"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = await dependency(request, credentials, oauth2_context.settings)

    assert identity.subject == "optional-cert-user"
    assert request.state.client_certificate == {"pem": "header-cert"}


@pytest.mark.anyio
async def test_missing_kid_in_header_is_rejected(
    oauth2_context: OAuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()
    original = jwt.get_unverified_header

    def fake_get_unverified_header(token_value: str) -> dict[str, Any]:
        header = original(token_value)
        header.pop("kid", None)
        return header

    monkeypatch.setattr(
        "application.api.security.jwt.get_unverified_header", fake_get_unverified_header
    )
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token."


@pytest.mark.anyio
async def test_tampered_signature_is_rejected(oauth2_context: OAuthContext) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()
    header, payload, signature = token.split(".")
    tampered_signature = (
        (signature[:-2] + "AA") if signature.endswith("==") else ("A" * len(signature))
    )
    tampered_token = ".".join([header, payload, tampered_signature])
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered_token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token."


@pytest.mark.anyio
async def test_expired_token_is_rejected(oauth2_context: OAuthContext) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(lifetime=timedelta(minutes=-5))
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token."


@pytest.mark.anyio
async def test_incorrect_audience_is_rejected(oauth2_context: OAuthContext) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(audience="different-audience")
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token."


@pytest.mark.anyio
async def test_incorrect_issuer_is_rejected(oauth2_context: OAuthContext) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token(issuer="https://issuer.invalid")
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token."


@pytest.mark.anyio
async def test_unsupported_signing_key_type_is_rejected(
    oauth2_context: OAuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = verify_request_identity()
    token = oauth2_context.mint_token()

    async def fake_get_key(uri: str, kid: str) -> dict[str, Any] | None:
        return {"kid": kid, "kty": "unsupported"}

    monkeypatch.setattr("application.api.security._jwks_resolver.get_key", fake_get_key)
    request = _make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        await dependency(request, credentials, oauth2_context.settings)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Signing key type is incompatible with bearer token algorithm."


@pytest.mark.anyio
async def test_two_factor_dependency_accepts_valid_code() -> None:
    fixed_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    dependency = require_two_factor(
        secret_provider=lambda: TWO_FACTOR_SECRET,
        header_name=TWO_FACTOR_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        clock=lambda: fixed_time,
    )
    code = generate_totp_code(TWO_FACTOR_SECRET, timestamp=fixed_time)
    request = _make_request(headers={TWO_FACTOR_HEADER: code})
    identity = AdminIdentity(subject="alice")

    resolved = await dependency(request, identity)

    assert resolved is identity


@pytest.mark.anyio
async def test_two_factor_dependency_rejects_missing_code() -> None:
    dependency = require_two_factor(
        secret_provider=lambda: TWO_FACTOR_SECRET,
        header_name=TWO_FACTOR_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    request = _make_request()
    identity = AdminIdentity(subject="alice")

    with pytest.raises(HTTPException) as exc:
        await dependency(request, identity)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Two-factor authentication code required for this endpoint."


@pytest.mark.anyio
async def test_two_factor_dependency_rejects_invalid_code() -> None:
    fixed_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    dependency = require_two_factor(
        secret_provider=lambda: TWO_FACTOR_SECRET,
        header_name=TWO_FACTOR_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        clock=lambda: fixed_time,
    )
    valid_code = generate_totp_code(TWO_FACTOR_SECRET, timestamp=fixed_time)
    replacement_digit = "0" if valid_code[0] != "0" else "1"
    invalid_code = replacement_digit + valid_code[1:]
    request = _make_request(headers={TWO_FACTOR_HEADER: invalid_code})
    identity = AdminIdentity(subject="alice")

    with pytest.raises(HTTPException) as exc:
        await dependency(request, identity)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired two-factor authentication code."


@pytest.mark.anyio
async def test_two_factor_dependency_handles_secret_errors() -> None:
    def failing_provider() -> str:
        raise SecretManagerError("offline")

    dependency = require_two_factor(
        secret_provider=failing_provider,
        header_name=TWO_FACTOR_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    code = generate_totp_code(
        TWO_FACTOR_SECRET, timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    request = _make_request(headers={TWO_FACTOR_HEADER: code})
    identity = AdminIdentity(subject="alice")

    with pytest.raises(HTTPException) as exc:
        await dependency(request, identity)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Two-factor authentication secret is unavailable."


def test_manual_override_survives_loader_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for attribute in ("_instance", "_loader", "_manual_override"):
        if hasattr(get_api_security_settings, attribute):
            delattr(get_api_security_settings, attribute)

    manual_settings = ApiSecuritySettings(
        oauth2_issuer="https://override.geosync.test",
        oauth2_audience="override-api",
        oauth2_jwks_uri="https://override.geosync.test/jwks",
    )

    setattr(get_api_security_settings, "_instance", manual_settings)
    setattr(get_api_security_settings, "_manual_override", True)

    assert get_api_security_settings() is manual_settings

    def replacement_loader() -> ApiSecuritySettings:
        return ApiSecuritySettings(
            oauth2_issuer="https://replacement.geosync.test",
            oauth2_audience="replacement-api",
            oauth2_jwks_uri="https://replacement.geosync.test/jwks",
        )

    monkeypatch.setattr(
        "application.api.security._default_settings_loader",
        replacement_loader,
    )

    try:
        assert get_api_security_settings() is manual_settings
    finally:
        for attribute in ("_instance", "_loader", "_manual_override"):
            if hasattr(get_api_security_settings, attribute):
                delattr(get_api_security_settings, attribute)
