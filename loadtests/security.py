# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Security utilities for performance test harnesses."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from application.settings import ApiSecuritySettings

LOADTEST_OAUTH_ISSUER = os.getenv("LOADTEST_OAUTH_ISSUER", "https://perf.geosync.test")
LOADTEST_OAUTH_AUDIENCE = os.getenv("LOADTEST_OAUTH_AUDIENCE", "geosync-api")
LOADTEST_JWKS_PATH = os.getenv("LOADTEST_JWKS_PATH", "/.well-known/jwks.json")
LOADTEST_KID = os.getenv("LOADTEST_KEY_ID", "loadtest-perf-key")


def _private_key() -> rsa.RSAPrivateKey:
    return _key_pair()[0]


def _public_key() -> rsa.RSAPublicKey:
    return _key_pair()[1]


@lru_cache(maxsize=1)
def _key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Load or generate an RSA key pair for load testing."""

    pem = os.getenv("LOADTEST_PRIVATE_KEY_PEM")
    if pem:
        private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
        return private_key, private_key.public_key()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def configure_security_overrides() -> ApiSecuritySettings:
    """Patch API security to use deterministic RSA credentials for load tests."""

    from application.api import security as security_module

    settings = ApiSecuritySettings(
        oauth2_issuer=LOADTEST_OAUTH_ISSUER,
        oauth2_audience=LOADTEST_OAUTH_AUDIENCE,
        oauth2_jwks_uri=f"{LOADTEST_OAUTH_ISSUER}{LOADTEST_JWKS_PATH}",
        trusted_hosts=("127.0.0.1", "localhost"),
    )

    # Ensure FastAPI dependency injection reuses our explicit settings instance.
    def _settings_loader() -> ApiSecuritySettings:
        return settings

    security_module._default_settings_loader = _settings_loader  # type: ignore[attr-defined]
    setattr(security_module.get_api_security_settings, "_instance", settings)
    setattr(security_module.get_api_security_settings, "_loader", _settings_loader)
    setattr(security_module.get_api_security_settings, "_manual_override", True)

    public_key = _public_key()
    jwk_dict = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk_dict.update({"kid": LOADTEST_KID, "alg": "RS256", "use": "sig"})

    async def fake_get_key(jwks_uri: str, request_kid: str) -> dict[str, str] | None:
        if jwks_uri == str(settings.oauth2_jwks_uri) and request_kid == LOADTEST_KID:
            return jwk_dict
        return None

    security_module._jwks_resolver.get_key = fake_get_key  # type: ignore[assignment]
    return settings


def mint_loadtest_token(
    *,
    subject: str = "loadtest-user",
    lifetime: timedelta = timedelta(minutes=5),
    audience: str | None = None,
    issuer: str | None = None,
) -> str:
    """Generate a signed bearer token compatible with the load-test settings."""

    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer or LOADTEST_OAUTH_ISSUER,
        "aud": audience or LOADTEST_OAUTH_AUDIENCE,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "roles": ["loadtest", "system"],
    }
    headers = {"kid": LOADTEST_KID, "alg": "RS256", "typ": "JWT"}
    private_key = _private_key()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    token = jwt.encode(payload, pem, algorithm="RS256", headers=headers)
    return token
