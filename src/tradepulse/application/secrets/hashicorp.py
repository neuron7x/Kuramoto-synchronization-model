"""HashiCorp Vault integration primitives.

This module provides a battle-tested interface for interacting with
HashiCorp Vault using short-lived credentials, audited access, and
policy management utilities.  The implementation focuses on security
controls that are critical for TradePulse where compromised secrets can
impact market-facing infrastructure.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping, Protocol

import httpx

from src.audit.audit_logger import AuditLogger

__all__ = [
    "DynamicCredentialManager",
    "DynamicSecretLease",
    "LeaseRenewal",
    "JWTOIDCAuthenticator",
    "StaticTokenAuthenticator",
    "VaultAuthenticator",
    "VaultClient",
    "VaultClientConfig",
    "VaultPolicyManager",
    "VaultRequestError",
    "VaultToken",
]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VaultRequestError(RuntimeError):
    """Raised when Vault returns a non-successful response."""

    def __init__(self, message: str, *, status_code: int, payload: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = dict(payload or {})


@dataclass(slots=True)
class VaultToken:
    """Representation of a Vault token with expiry handling."""

    value: str
    lease_duration: int | None
    renewable: bool
    accessor: str | None = None
    policies: tuple[str, ...] = tuple()
    issued_at: datetime = field(default_factory=_utc_now)

    def expires_at(self) -> datetime | None:
        if self.lease_duration is None:
            return None
        return self.issued_at + timedelta(seconds=self.lease_duration)

    def is_expired(self, *, now: datetime | None = None, margin: int = 30) -> bool:
        expires = self.expires_at()
        if expires is None:
            return False
        effective_now = _ensure_utc(now or _utc_now())
        return effective_now + timedelta(seconds=margin) >= expires


class VaultAuthenticator(Protocol):
    """Authenticate a client session and return a Vault token."""

    def authenticate(
        self,
        *,
        session: httpx.Client,
        config: "VaultClientConfig",
        clock: Callable[[], datetime],
    ) -> VaultToken:
        """Return a token to be used for subsequent requests."""


@dataclass(slots=True)
class StaticTokenAuthenticator:
    """Authenticator that returns a pre-provisioned Vault token."""

    token: str

    def authenticate(
        self,
        *,
        session: httpx.Client,  # noqa: ARG002 - part of the authenticator protocol
        config: "VaultClientConfig",  # noqa: ARG002 - part of the authenticator protocol
        clock: Callable[[], datetime],
    ) -> VaultToken:
        if not self.token:
            raise VaultRequestError("Static token cannot be empty", status_code=401)
        return VaultToken(self.token, lease_duration=None, renewable=False)


@dataclass(slots=True)
class JWTOIDCAuthenticator:
    """Authenticate to Vault using the JWT/OIDC auth method."""

    mount_path: str
    role: str
    jwt_provider: Callable[[], str]

    def authenticate(
        self,
        *,
        session: httpx.Client,
        config: "VaultClientConfig",
        clock: Callable[[], datetime],
    ) -> VaultToken:
        jwt = self.jwt_provider()
        if not jwt:
            raise VaultRequestError("JWT provider returned empty token", status_code=401)
        path = f"/v1/auth/{self.mount_path.strip('/')}/login"
        headers: MutableMapping[str, str] | None = None
        if config.namespace:
            headers = {"X-Vault-Namespace": config.namespace}
        response = session.post(path, json={"role": self.role, "jwt": jwt}, headers=headers)
        if response.status_code >= 400:
            payload = _safe_json(response)
            raise VaultRequestError(
                f"Vault authentication failed for role '{self.role}'",
                status_code=response.status_code,
                payload=payload,
            )
        body = response.json()
        auth = body.get("auth", {})
        token = auth.get("client_token")
        if not token:
            raise VaultRequestError(
                "Vault response did not include a client token",
                status_code=response.status_code,
                payload=body,
            )
        lease_duration = auth.get("lease_duration")
        renewable = bool(auth.get("renewable", False))
        accessor = auth.get("accessor")
        policies = tuple(auth.get("policies", ()))
        return VaultToken(
            token,
            lease_duration=int(lease_duration) if lease_duration else None,
            renewable=renewable,
            accessor=accessor,
            policies=policies,
            issued_at=_ensure_utc(clock()),
        )


def _safe_json(response: httpx.Response) -> Mapping[str, Any]:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"raw": response.text}


@dataclass(slots=True)
class VaultClientConfig:
    """Static configuration parameters for a Vault client."""

    address: str
    namespace: str | None = None
    verify: bool | str = True
    timeout: float = 5.0
    audit_actor: str = "vault-client"
    audit_ip: str = "127.0.0.1"


@dataclass(slots=True)
class LeaseRenewal:
    """Metadata returned when renewing a lease."""

    lease_id: str
    lease_duration: int
    renewable: bool


@dataclass(slots=True)
class DynamicSecretLease:
    """Representation of a dynamic secret lease issued by Vault."""

    lease_id: str
    data: Mapping[str, Any]
    lease_duration: int
    renewable: bool
    accessor: str | None = None
    request_id: str | None = None
    warnings: tuple[str, ...] = tuple()
    wrap_info: Mapping[str, Any] | None = None
    issued_at: datetime = field(default_factory=_utc_now)

    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.lease_duration)

    def is_expired(self, *, now: datetime | None = None, margin: int = 60) -> bool:
        current = _ensure_utc(now or _utc_now())
        return current + timedelta(seconds=margin) >= self.expires_at()

    def renewed(self, renewal: LeaseRenewal, *, issued_at: datetime) -> "DynamicSecretLease":
        return DynamicSecretLease(
            lease_id=self.lease_id,
            data=dict(self.data),
            lease_duration=renewal.lease_duration,
            renewable=renewal.renewable,
            accessor=self.accessor,
            request_id=self.request_id,
            warnings=self.warnings,
            wrap_info=dict(self.wrap_info) if self.wrap_info is not None else None,
            issued_at=_ensure_utc(issued_at),
        )


class VaultClient:
    """Thin wrapper around the Vault HTTP API with automatic auditing."""

    def __init__(
        self,
        *,
        config: VaultClientConfig,
        authenticator: VaultAuthenticator,
        session_factory: Callable[..., httpx.Client] | None = None,
        audit_logger: AuditLogger | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not config.address:
            raise ValueError("Vault address must be provided")
        self._config = config
        self._authenticator = authenticator
        self._audit_logger = audit_logger
        self._clock = clock
        factory = session_factory or httpx.Client
        self._session = factory(
            base_url=config.address,
            timeout=config.timeout,
            verify=config.verify,
        )
        self._token: VaultToken | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._session.close()

    def read_kv_secret(
        self,
        *,
        mount: str,
        path: str,
        version: int = 2,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> Mapping[str, Any]:
        payload = self._request(
            "GET",
            self._kv_path(mount, path, version=version, operation="data"),
        )
        data = payload.get("data", {})
        if version == 2:
            data = data.get("data", {})
        self._audit("vault.kv.read", actor=actor, ip_address=ip_address, details={"mount": mount, "path": path})
        return MappingProxyType(dict(data))

    def write_kv_secret(
        self,
        *,
        mount: str,
        path: str,
        secret: Mapping[str, Any],
        version: int = 2,
        cas: int | None = None,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        if version == 2:
            body: MutableMapping[str, Any] = {"data": dict(secret)}
            if cas is not None:
                body["options"] = {"cas": cas}
        else:
            body = dict(secret)
        self._request(
            "POST",
            self._kv_path(mount, path, version=version, operation="data"),
            json=body,
        )
        self._audit(
            "vault.kv.write",
            actor=actor,
            ip_address=ip_address,
            details={"mount": mount, "path": path, "version": version},
        )

    def delete_kv_secret(
        self,
        *,
        mount: str,
        path: str,
        version: int = 2,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self._request(
            "DELETE",
            self._kv_path(mount, path, version=version, operation="data"),
        )
        self._audit(
            "vault.kv.delete",
            actor=actor,
            ip_address=ip_address,
            details={"mount": mount, "path": path, "version": version},
        )

    def generate_dynamic_credentials(
        self,
        *,
        mount: str,
        role: str,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> DynamicSecretLease:
        payload = self._request("POST", f"/v1/{mount.strip('/')}/creds/{role}")
        lease = DynamicSecretLease(
            lease_id=payload["lease_id"],
            data=dict(payload.get("data", {})),
            lease_duration=int(payload.get("lease_duration", 0)),
            renewable=bool(payload.get("renewable", False)),
            accessor=payload.get("lease_id"),
            request_id=payload.get("request_id"),
            warnings=tuple(payload.get("warnings", []) or []),
            wrap_info=payload.get("wrap_info"),
            issued_at=_ensure_utc(self._clock()),
        )
        self._audit(
            "vault.dynamic.issue",
            actor=actor,
            ip_address=ip_address,
            details={"mount": mount, "role": role, "lease_id": lease.lease_id},
        )
        return lease

    def renew_lease(
        self,
        lease_id: str,
        *,
        increment: int | None = None,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> LeaseRenewal:
        body: MutableMapping[str, Any] = {"lease_id": lease_id}
        if increment is not None:
            body["increment"] = increment
        payload = self._request("POST", "/v1/sys/leases/renew", json=body)
        renewal = LeaseRenewal(
            lease_id=payload.get("lease_id", lease_id),
            lease_duration=int(payload.get("lease_duration", 0)),
            renewable=bool(payload.get("renewable", False)),
        )
        self._audit(
            "vault.lease.renew",
            actor=actor,
            ip_address=ip_address,
            details={"lease_id": lease_id, "increment": increment},
        )
        return renewal

    def revoke_lease(
        self,
        lease_id: str,
        *,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self._request("POST", "/v1/sys/leases/revoke", json={"lease_id": lease_id})
        self._audit(
            "vault.lease.revoke",
            actor=actor,
            ip_address=ip_address,
            details={"lease_id": lease_id},
        )

    def create_policy(self, name: str, policy: str) -> None:
        self._request(
            "PUT",
            f"/v1/sys/policies/acl/{name}",
            json={"policy": policy},
        )

    def get_policy(self, name: str) -> str | None:
        try:
            payload = self._request("GET", f"/v1/sys/policies/acl/{name}")
        except VaultRequestError as exc:
            if exc.status_code == 404:
                return None
            raise
        return payload.get("policy")

    def delete_policy(self, name: str) -> None:
        self._request("DELETE", f"/v1/sys/policies/acl/{name}")

    def list_policies(self) -> tuple[str, ...]:
        payload = self._request("GET", "/v1/sys/policies/acl")
        return tuple(payload.get("policies", []))

    def enable_audit_device(self, name: str, *, path: str, options: Mapping[str, Any] | None = None) -> None:
        body: MutableMapping[str, Any] = {"type": name, "options": dict(options or {})}
        self._request("POST", f"/v1/sys/audit/{path}", json=body)

    def issue_token(
        self,
        *,
        display_name: str,
        policies: tuple[str, ...] = tuple(),
        ttl: int | None = None,
        renewable: bool = True,
        num_uses: int | None = None,
        meta: Mapping[str, str] | None = None,
    ) -> VaultToken:
        body: MutableMapping[str, Any] = {
            "display_name": display_name,
            "renewable": renewable,
        }
        if policies:
            body["policies"] = list(policies)
        if ttl is not None:
            body["ttl"] = ttl
        if num_uses is not None:
            body["num_uses"] = num_uses
        if meta is not None:
            body["meta"] = dict(meta)
        payload = self._request("POST", "/v1/auth/token/create", json=body)
        auth = payload.get("auth", {})
        token = auth.get("client_token")
        if not token:
            raise VaultRequestError("Vault did not return a client token", status_code=500, payload=payload)
        lease_duration = auth.get("lease_duration")
        return VaultToken(
            token,
            lease_duration=int(lease_duration) if lease_duration else None,
            renewable=bool(auth.get("renewable", renewable)),
            accessor=auth.get("accessor"),
            policies=tuple(auth.get("policies", policies)),
            issued_at=_ensure_utc(self._clock()),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _kv_path(self, mount: str, path: str, *, version: int, operation: str) -> str:
        mount_clean = mount.strip("/")
        path_clean = path.strip("/")
        if version == 2:
            return f"/v1/{mount_clean}/{operation}/{path_clean}"
        return f"/v1/{mount_clean}/{path_clean}"

    def _audit(
        self,
        event_type: str,
        *,
        actor: str | None,
        ip_address: str | None,
        details: Mapping[str, Any],
    ) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log_event(
                event_type=event_type,
                actor=actor or self._config.audit_actor,
                ip_address=ip_address or self._config.audit_ip,
                details=details,
            )
        except Exception:
            # The audit logger already records failures internally; never block the caller.
            pass

    def _request(self, method: str, path: str, **kwargs: Any) -> Mapping[str, Any]:
        with self._lock:
            if self._token is None or self._token.is_expired(now=self._clock()):
                self._token = self._authenticator.authenticate(
                    session=self._session, config=self._config, clock=self._clock
                )
        headers = kwargs.pop("headers", {})
        headers = {"X-Vault-Token": self._token.value, **headers}
        if self._config.namespace:
            headers.setdefault("X-Vault-Namespace", self._config.namespace)
        response = self._session.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            payload = _safe_json(response)
            raise VaultRequestError(
                f"Vault request to {path} failed with status {response.status_code}",
                status_code=response.status_code,
                payload=payload,
            )
        return _safe_json(response)


class VaultPolicyManager:
    """High-level helper for managing Vault ACL policies idempotently."""

    def __init__(self, client: VaultClient) -> None:
        self._client = client

    def ensure_policy(self, name: str, policy: str) -> bool:
        existing = self._client.get_policy(name)
        if existing == policy:
            return False
        self._client.create_policy(name, policy)
        return True

    def delete_policy(self, name: str) -> None:
        self._client.delete_policy(name)


class DynamicCredentialManager:
    """Fetch and renew Vault dynamic credentials for application use."""

    def __init__(
        self,
        client: VaultClient,
        *,
        mount: str,
        role: str,
        refresh_margin: int = 60,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if refresh_margin < 0:
            raise ValueError("refresh_margin must be non-negative")
        self._client = client
        self._mount = mount
        self._role = role
        self._refresh_margin = refresh_margin
        self._clock = clock
        self._lock = threading.RLock()
        self._lease: DynamicSecretLease | None = None

    def get_credentials(self) -> Mapping[str, Any]:
        with self._lock:
            now = self._clock()
            if self._lease is None:
                self._lease = self._client.generate_dynamic_credentials(
                    mount=self._mount,
                    role=self._role,
                )
            elif self._lease.is_expired(now=now, margin=self._refresh_margin):
                if not self._lease.renewable:
                    self._lease = self._client.generate_dynamic_credentials(
                        mount=self._mount,
                        role=self._role,
                    )
                else:
                    renewal = self._client.renew_lease(self._lease.lease_id)
                    self._lease = self._lease.renewed(renewal, issued_at=now)
            return MappingProxyType(dict(self._lease.data))

    def revoke(self) -> None:
        with self._lock:
            if self._lease is None:
                return
            self._client.revoke_lease(self._lease.lease_id)
            self._lease = None

    def describe(self) -> DynamicSecretLease | None:
        with self._lock:
            if self._lease is None:
                return None
            return replace(
                self._lease,
                data=MappingProxyType(dict(self._lease.data)),
            )
