from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

import httpx
import pytest

from application.secrets.hashicorp import (
    DynamicCredentialManager,
    JWTOIDCAuthenticator,
    StaticTokenAuthenticator,
    VaultClient,
    VaultClientConfig,
    VaultPolicyManager,
    VaultRequestError,
)
from src.audit.audit_logger import AuditLogger


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def advance(self, delta: timedelta) -> None:
        self._current += delta

    def __call__(self) -> datetime:
        return self._current


class _MockVaultAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._kv_store: dict[tuple[str, str], dict[str, Any]] = {}
        self._lease_counter = 0

    def add_kv(self, mount: str, path: str, payload: dict[str, Any]) -> None:
        self._kv_store[(mount, path)] = payload

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.url.path.startswith("/v1/sys/policies/acl"):
            return self._handle_policy(request)
        if request.url.path.startswith("/v1/sys/leases/renew"):
            return httpx.Response(
                200,
                json={
                    "lease_id": json_body(request)["lease_id"],
                    "lease_duration": 120,
                    "renewable": True,
                },
            )
        if request.url.path.startswith("/v1/sys/leases/revoke"):
            return httpx.Response(204)
        if (
            request.url.path.startswith("/v1/database/creds/")
            and request.method == "POST"
        ):
            self._lease_counter += 1
            return httpx.Response(
                200,
                json={
                    "lease_id": "database/creds/tradepulse/123",
                    "lease_duration": 120,
                    "renewable": True,
                    "data": {
                        "username": f"user{self._lease_counter}",
                        "password": f"pass{self._lease_counter}",
                    },
                },
            )
        if request.url.path.startswith("/v1/auth/oidc/login"):
            return httpx.Response(
                200,
                json={
                    "auth": {
                        "client_token": "oidc-token",
                        "lease_duration": 900,
                        "renewable": True,
                        "accessor": "accessor",  # noqa: S105 - fake
                        "policies": ["default"],
                    }
                },
            )
        if request.method == "GET" and request.url.path.startswith("/v1/secret/data/"):
            key = ("secret", request.url.path.split("/v1/secret/data/")[-1])
            if key not in self._kv_store:
                return httpx.Response(404, json={"errors": ["not found"]})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "data": dict(self._kv_store[key]),
                        "metadata": {"version": 1},
                    }
                },
            )
        return httpx.Response(404, json={"errors": ["not found"]})

    def _handle_policy(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        if len(parts) < 6:
            return httpx.Response(404, json={"errors": ["invalid path"]})
        name = parts[-1]
        if request.method == "GET":
            try:
                policy = self._kv_store[("policy", name)]["policy"]
            except KeyError:
                return httpx.Response(404, json={"errors": ["missing"]})
            return httpx.Response(200, json={"policy": policy})
        if request.method == "PUT":
            self._kv_store[("policy", name)] = {"policy": json_body(request)["policy"]}
            return httpx.Response(204)
        if request.method == "DELETE":
            self._kv_store.pop(("policy", name), None)
            return httpx.Response(204)
        if request.method == "GET" and parts[-1] == "acl":
            policies = [name for key, _ in self._kv_store if key == "policy"]
            return httpx.Response(200, json={"policies": policies})
        return httpx.Response(405)


def json_body(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    return httpx.Response(200, content=request.content).json()


def _make_client(
    mock: _MockVaultAPI,
    *,
    clock: Callable[[], datetime] | None = None,
    audit_logger: AuditLogger | None = None,
) -> VaultClient:
    transport = httpx.MockTransport(mock.handler)
    return VaultClient(
        config=VaultClientConfig(address="https://vault.test"),
        authenticator=StaticTokenAuthenticator(token="root-token"),
        session_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
        audit_logger=audit_logger,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


class _AuditStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def log_event(
        self,
        *,
        event_type: str,
        actor: str,
        ip_address: str,
        details: dict | None = None,
    ) -> None:
        self.events.append((event_type, actor))


def test_vault_client_reads_kv_secret() -> None:
    mock = _MockVaultAPI()
    mock.add_kv("secret", "service/api", {"api_key": "value"})
    audit = cast(AuditLogger, _AuditStub())
    client = _make_client(mock, audit_logger=audit)

    secret = client.read_kv_secret(mount="secret", path="service/api")

    assert secret["api_key"] == "value"
    assert ("GET", "/v1/secret/data/service/api") in mock.calls
    assert any(event for event in audit.events if event[0] == "vault.kv.read")


def test_vault_client_raises_on_error() -> None:
    mock = _MockVaultAPI()
    client = _make_client(mock)

    with pytest.raises(VaultRequestError) as exc:
        client.read_kv_secret(mount="secret", path="missing")

    assert exc.value.status_code == 404


def test_dynamic_credential_manager_renews_before_expiry() -> None:
    clock = _MutableClock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    mock = _MockVaultAPI()
    client = _make_client(mock, clock=clock)
    manager = DynamicCredentialManager(
        client,
        mount="database",
        role="tradepulse",
        refresh_margin=15,
        clock=clock,
    )

    initial = manager.get_credentials()
    assert initial["username"] == "user1"

    clock.advance(timedelta(seconds=110))
    refreshed = manager.get_credentials()

    # Renewing the lease should not issue a new credential payload
    assert refreshed["username"] == "user1"
    assert ("POST", "/v1/sys/leases/renew") in mock.calls

    manager.revoke()
    assert ("POST", "/v1/sys/leases/revoke") in mock.calls


def test_vault_policy_manager_updates_policy_when_changed() -> None:
    mock = _MockVaultAPI()
    client = _make_client(mock)
    manager = VaultPolicyManager(client)

    created = manager.ensure_policy(
        "tradepulse", 'path "secret/*" { capabilities = ["read"] }'
    )
    assert created is True
    created_again = manager.ensure_policy(
        "tradepulse", 'path "secret/*" { capabilities = ["read"] }'
    )
    assert created_again is False


def test_oidc_authenticator_fetches_token() -> None:
    mock = _MockVaultAPI()
    transport = httpx.MockTransport(mock.handler)
    authenticator = JWTOIDCAuthenticator(
        mount_path="oidc",
        role="trader",
        jwt_provider=lambda: "jwt-token",
    )
    client = VaultClient(
        config=VaultClientConfig(address="https://vault.test"),
        authenticator=authenticator,
        session_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    mock.add_kv("secret", "svc/config", {"token": "abc"})
    secret = client.read_kv_secret(mount="secret", path="svc/config")

    assert secret["token"] == "abc"
    assert any(call for call in mock.calls if call[1] == "/v1/auth/oidc/login")
