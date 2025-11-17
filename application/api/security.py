"""Security dependencies for validating TradePulse API requests."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.secrets.manager import SecretManagerError
from application.security.two_factor import verify_totp_code
from application.settings import ApiSecuritySettings
from src.admin.remote_control import AdminIdentity

__all__ = [
    "verify_request_identity",
    "verify_optional_request_identity",
    "get_api_security_settings",
    "require_two_factor",
]


_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="OAuth2Bearer")


@dataclass(slots=True)
class _JWKSCacheEntry:
    expires_at: datetime
    keys: dict[str, dict[str, Any]]


class _JWKSResolver:
    """Fetch and cache JWKS responses for validating JWTs."""

    def __init__(self, *, ttl: timedelta = timedelta(minutes=10)) -> None:
        self._ttl = ttl
        self._entries: dict[str, _JWKSCacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get_key(self, jwks_uri: str, kid: str) -> dict[str, Any] | None:
        """Return the JWK matching *kid* for the supplied *jwks_uri*."""

        keys = await self._ensure_keys(jwks_uri)
        key = keys.get(kid)
        if key is not None:
            return key

        # Refresh once in case the key rotated.
        keys = await self._refresh(jwks_uri)
        return keys.get(kid)

    async def _ensure_keys(self, jwks_uri: str) -> dict[str, dict[str, Any]]:
        async with self._lock:
            entry = self._entries.get(jwks_uri)
            now = datetime.now(timezone.utc)
            if entry is None or entry.expires_at <= now:
                keys = await self._fetch(jwks_uri)
                self._entries[jwks_uri] = _JWKSCacheEntry(
                    expires_at=now + self._ttl, keys=keys
                )
                return keys
            return entry.keys

    async def _refresh(self, jwks_uri: str) -> dict[str, dict[str, Any]]:
        async with self._lock:
            keys = await self._fetch(jwks_uri)
            self._entries[jwks_uri] = _JWKSCacheEntry(
                expires_at=datetime.now(timezone.utc) + self._ttl,
                keys=keys,
            )
            return keys

    async def _fetch(self, jwks_uri: str) -> dict[str, dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_uri)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network failure guard
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to load JWKS for bearer token validation.",
            ) from exc

        data = response.json()
        keys = data.get("keys")
        if not isinstance(keys, list):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWKS document is malformed.",
            )

        keyed: dict[str, dict[str, Any]] = {}
        for entry in keys:
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            keyed[kid] = entry
        if not keyed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWKS document does not contain usable signing keys.",
            )
        return keyed


_jwks_resolver = _JWKSResolver()


_RSA_ALGORITHMS = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512"}
_EC_ALGORITHMS = {"ES256", "ES256K", "ES384", "ES512", "ES521"}
_HMAC_ALGORITHMS = {"HS256", "HS384", "HS512"}


def _jwk_to_key(jwk_data: dict[str, Any], *, algorithm: str) -> Any:
    """Materialise the appropriate public key from a JWK entry."""

    normalised_algorithm = algorithm.upper()
    kty = jwk_data.get("kty")
    jwk_json = json.dumps(jwk_data)
    if normalised_algorithm in _RSA_ALGORITHMS:
        if kty != "RSA":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key type is incompatible with bearer token algorithm.",
            )
        return jwt.algorithms.RSAAlgorithm.from_jwk(jwk_json)
    if normalised_algorithm in _EC_ALGORITHMS:
        if kty != "EC":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key type is incompatible with bearer token algorithm.",
            )
        return jwt.algorithms.ECAlgorithm.from_jwk(jwk_json)
    if normalised_algorithm == "EDDSA":
        if kty != "OKP":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key type is incompatible with bearer token algorithm.",
            )
        return jwt.algorithms.OKPAlgorithm.from_jwk(jwk_json)
    if normalised_algorithm in _HMAC_ALGORITHMS:
        if kty != "oct":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key type is incompatible with bearer token algorithm.",
            )
        key_value = jwk_data.get("k")
        if not isinstance(key_value, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            )
        padding = "=" * ((4 - len(key_value) % 4) % 4)
        try:
            return base64.urlsafe_b64decode(key_value + padding)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unsupported bearer token signing algorithm.",
    )


def _extract_client_certificate(request: Request) -> dict[str, Any] | None:
    """Obtain mutual TLS metadata attached to the ASGI request."""

    if hasattr(request.state, "client_certificate"):
        certificate = getattr(request.state, "client_certificate")
        if certificate is not None:
            return certificate  # pragma: no cover - state is usually unset in tests

    scope_certificate = request.scope.get("client_cert")
    if isinstance(scope_certificate, dict):
        return scope_certificate

    header_certificate = request.headers.get("x-client-cert")
    if header_certificate:
        return {"pem": header_certificate}

    return None


def _store_identity_context(
    request: Request, *, claims: dict[str, Any], certificate: dict[str, Any] | None
) -> None:
    request.state.token_claims = claims
    if certificate is not None:
        request.state.client_certificate = certificate


def _require_subject(claims: dict[str, Any]) -> str:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is missing the subject claim.",
        )
    return subject


def _normalise_role(value: str) -> str | None:
    candidate = value.strip().lower()
    return candidate or None


def _extract_roles(claims: Mapping[str, Any]) -> tuple[str, ...]:
    """Return normalised roles discovered within *claims*."""

    roles: set[str] = set()

    def _ingest(candidate: Any) -> None:
        if isinstance(candidate, str):
            for part in candidate.replace(",", " ").split():
                normalised = _normalise_role(part)
                if normalised:
                    roles.add(normalised)
            return
        if isinstance(candidate, (list, tuple, set, frozenset)):
            for entry in candidate:
                _ingest(entry)
            return
        if isinstance(candidate, Mapping):
            for entry in candidate.values():
                _ingest(entry)

    for key in ("roles", "permissions", "scope"):
        raw = claims.get(key)
        if raw:
            _ingest(raw)

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, Mapping):
        _ingest(realm_access.get("roles"))

    resource_access = claims.get("resource_access")
    if isinstance(resource_access, Mapping):
        for entry in resource_access.values():
            _ingest(entry)

    return tuple(sorted(roles))


def _default_settings_loader() -> ApiSecuritySettings:
    return ApiSecuritySettings()


def get_api_security_settings() -> ApiSecuritySettings:
    """Return cached security settings for dependency injection."""

    loader = _default_settings_loader
    manual_override = getattr(get_api_security_settings, "_manual_override", False)

    if manual_override:
        if hasattr(get_api_security_settings, "_instance"):
            return getattr(get_api_security_settings, "_instance")
        if hasattr(get_api_security_settings, "_manual_override"):
            delattr(get_api_security_settings, "_manual_override")
        if hasattr(get_api_security_settings, "_loader"):
            delattr(get_api_security_settings, "_loader")

    cached_loader = getattr(get_api_security_settings, "_loader", None)

    if cached_loader is None and hasattr(get_api_security_settings, "_instance"):
        settings = getattr(get_api_security_settings, "_instance")
        setattr(get_api_security_settings, "_loader", loader)
        return settings

    if cached_loader is not loader:
        settings = loader()
        setattr(get_api_security_settings, "_instance", settings)
        setattr(get_api_security_settings, "_loader", loader)
        if hasattr(get_api_security_settings, "_manual_override"):
            delattr(get_api_security_settings, "_manual_override")
        return settings

    if not hasattr(get_api_security_settings, "_instance"):
        settings = loader()
        setattr(get_api_security_settings, "_instance", settings)
        setattr(get_api_security_settings, "_loader", loader)
        if hasattr(get_api_security_settings, "_manual_override"):
            delattr(get_api_security_settings, "_manual_override")
        return settings

    return getattr(get_api_security_settings, "_instance")


def verify_request_identity(*, require_client_certificate: bool = False) -> Callable[
    [Request, HTTPAuthorizationCredentials | None, ApiSecuritySettings],
    Awaitable[AdminIdentity],
]:
    """Return a dependency that authenticates requests via OAuth2 bearer tokens."""

    async def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
        settings: ApiSecuritySettings = Depends(get_api_security_settings),
    ) -> AdminIdentity:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required for this endpoint.",
            )

        token = credentials.credentials
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            ) from exc

        kid = header.get("kid")
        algorithm = header.get("alg")
        if not isinstance(kid, str) or not kid or not isinstance(algorithm, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            )

        normalised_algorithm = algorithm.strip().upper()
        allowed_algorithms = settings.oauth2_algorithms
        algorithm_lookup = {value.upper(): value for value in allowed_algorithms}
        canonical_algorithm = algorithm_lookup.get(normalised_algorithm)
        if canonical_algorithm is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unsupported bearer token signing algorithm.",
            )

        jwk_entry = await _jwks_resolver.get_key(str(settings.oauth2_jwks_uri), kid)
        if jwk_entry is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token signed by unknown key.",
            )

        jwk_algorithm = jwk_entry.get("alg")
        if isinstance(jwk_algorithm, str) and jwk_algorithm.strip():
            if jwk_algorithm.strip().upper() != normalised_algorithm:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Signing key metadata does not match token algorithm.",
                )

        jwk_use = jwk_entry.get("use")
        if isinstance(jwk_use, str) and jwk_use.strip():
            if jwk_use.strip().lower() != "sig":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Signing key is not authorised for signature validation.",
                )

        public_key = _jwk_to_key(jwk_entry, algorithm=canonical_algorithm)

        try:
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=list(algorithm_lookup.values()),
                audience=settings.oauth2_audience,
                issuer=str(settings.oauth2_issuer),
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            ) from exc

        certificate = _extract_client_certificate(request)
        if require_client_certificate and certificate is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mutual TLS client certificate required.",
            )

        _store_identity_context(request, claims=claims, certificate=certificate)
        subject = _require_subject(claims)
        roles = _extract_roles(claims)
        return AdminIdentity(subject=subject, roles=roles)

    return dependency


def require_two_factor(
    *,
    secret_provider: Callable[[], str],
    header_name: str,
    digits: int,
    period_seconds: int,
    drift_windows: int,
    algorithm: str,
    identity_dependency: Callable[..., Awaitable[AdminIdentity]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Callable[[Request, AdminIdentity], Awaitable[AdminIdentity]]:
    """Return a dependency that enforces TOTP-based two-factor authentication."""

    if digits <= 0:
        raise ValueError("digits must be positive")
    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")
    if drift_windows < 0:
        raise ValueError("drift_windows must be non-negative")
    dependency = identity_dependency or verify_request_identity()

    async def _dependency(
        request: Request,
        identity: AdminIdentity = Depends(dependency),
    ) -> AdminIdentity:
        code = request.headers.get(header_name)
        if code is None or not code.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Two-factor authentication code required for this endpoint.",
            )
        try:
            secret = secret_provider()
        except SecretManagerError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Two-factor authentication secret is unavailable.",
            ) from exc
        moment = clock() if clock is not None else datetime.now(timezone.utc)
        if not verify_totp_code(
            secret,
            code,
            timestamp=moment,
            period_seconds=period_seconds,
            digits=digits,
            drift_windows=drift_windows,
            algorithm=algorithm,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired two-factor authentication code.",
            )
        return identity

    return _dependency


def verify_optional_request_identity(
    *, require_client_certificate: bool = False
) -> Callable[
    [Request, HTTPAuthorizationCredentials | None, ApiSecuritySettings],
    Awaitable[AdminIdentity | None],
]:
    """Return a dependency that authenticates requests when credentials are supplied."""

    required_dependency = verify_request_identity(
        require_client_certificate=require_client_certificate
    )

    async def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
        settings: ApiSecuritySettings = Depends(get_api_security_settings),
    ) -> AdminIdentity | None:
        if credentials is None or not credentials.credentials:
            return None
        return await required_dependency(request, credentials, settings)

    return dependency
