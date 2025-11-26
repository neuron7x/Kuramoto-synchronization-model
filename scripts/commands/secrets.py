"""Secrets automation commands backed by HashiCorp Vault."""

from __future__ import annotations

import json
import logging
import os
from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path

from application.secrets.hashicorp import (
    DynamicCredentialManager,
    JWTOIDCAuthenticator,
    StaticTokenAuthenticator,
    VaultClient,
    VaultClientConfig,
    VaultRequestError,
)
from scripts.commands.base import CommandError, register

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "secrets-issue-dynamic",
        help="Issue short-lived credentials from Vault and persist them to disk.",
    )
    _configure_issue_dynamic(parser)


def _configure_issue_dynamic(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--address",
        required=True,
        help="Vault base URL (e.g. https://vault.service:8200)",
    )
    parser.add_argument("--namespace", default=None, help="Optional Vault namespace")
    parser.add_argument(
        "--mount",
        default="database",
        help="Secret engine mount path (default: database)",
    )
    parser.add_argument("--role", required=True, help="Dynamic credential role name")
    parser.add_argument(
        "--auth-method",
        choices=("static-token", "oidc"),
        default="static-token",
        help="Authentication strategy for Vault",
    )
    parser.add_argument("--token", help="Static token used for authentication")
    parser.add_argument(
        "--token-env",
        help="Environment variable containing a static Vault token",
    )
    parser.add_argument(
        "--oidc-mount", default="oidc", help="OIDC auth mount path (default: oidc)"
    )
    parser.add_argument(
        "--oidc-role",
        help="OIDC auth role name (defaults to the dynamic credential role)",
    )
    parser.add_argument("--jwt", help="Inline JWT for the OIDC login flow")
    parser.add_argument(
        "--jwt-env",
        help="Environment variable containing a JWT for OIDC login",
    )
    parser.add_argument(
        "--jwt-path",
        type=Path,
        help="Path to a file containing the JWT used for OIDC login",
    )
    parser.add_argument(
        "--ca-bundle",
        type=Path,
        help="Optional CA bundle used to verify the Vault TLS endpoint",
    )
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        help="Disable TLS verification (strongly discouraged outside development)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination file that will receive the credential JSON payload",
    )
    parser.add_argument(
        "--refresh-margin",
        type=int,
        default=60,
        help="Seconds before expiry when leases should be renewed (default: 60)",
    )
    parser.set_defaults(command="secrets-issue-dynamic", handler=handle_issue_dynamic)


def _load_static_token(args: object) -> str:
    token = getattr(args, "token", None)
    if token:
        return str(token)
    token_env = getattr(args, "token_env", None)
    if token_env:
        value = os.getenv(token_env)
        if value:
            return value
    raise CommandError("A Vault token must be provided via --token or --token-env")


def _load_jwt(args: object) -> str:
    jwt_value = getattr(args, "jwt", None)
    if jwt_value:
        return str(jwt_value)
    jwt_env = getattr(args, "jwt_env", None)
    if jwt_env:
        value = os.getenv(jwt_env)
        if value:
            return value
    jwt_path: Path | None = getattr(args, "jwt_path", None)
    if jwt_path is not None:
        if not jwt_path.exists():
            raise CommandError(f"JWT file {jwt_path} does not exist")
        return jwt_path.read_text(encoding="utf-8").strip()
    raise CommandError(
        "A JWT must be supplied via --jwt, --jwt-env, or --jwt-path for OIDC auth"
    )


@register("secrets-issue-dynamic")
def handle_issue_dynamic(args: object) -> int:
    client: VaultClient | None = None
    try:
        verify: bool | str
        ca_bundle: Path | None = getattr(args, "ca_bundle", None)
        if getattr(args, "insecure_skip_verify", False):
            verify = False
        elif ca_bundle is not None:
            if not ca_bundle.exists():
                raise CommandError(f"CA bundle {ca_bundle} does not exist")
            verify = str(ca_bundle)
        else:
            verify = True

        auth_method = getattr(args, "auth_method")
        if auth_method == "static-token":
            authenticator = StaticTokenAuthenticator(token=_load_static_token(args))
        else:
            jwt_value = _load_jwt(args)
            authenticator = JWTOIDCAuthenticator(
                mount_path=str(getattr(args, "oidc_mount")),
                role=str(getattr(args, "oidc_role") or getattr(args, "role")),
                jwt_provider=lambda jwt=jwt_value: jwt,
            )

        config = VaultClientConfig(
            address=str(getattr(args, "address")),
            namespace=getattr(args, "namespace", None),
            verify=verify,
        )
        client = VaultClient(config=config, authenticator=authenticator)
        refresh_margin = int(getattr(args, "refresh_margin"))
        if refresh_margin < 0:
            raise CommandError("--refresh-margin must be zero or positive")
        manager = DynamicCredentialManager(
            client,
            mount=str(getattr(args, "mount")),
            role=str(getattr(args, "role")),
            refresh_margin=refresh_margin,
        )
        credentials = manager.get_credentials()
        lease = manager.describe()
        output_path: Path = getattr(args, "output")
        payload = {
            "credentials": dict(credentials),
            "lease_id": lease.lease_id if lease else None,
            "lease_duration": lease.lease_duration if lease else None,
            "renewable": lease.renewable if lease else None,
            "issued_at": lease.issued_at.isoformat() if lease else None,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.info("Wrote dynamic credentials to %s", output_path)
        return 0
    except VaultRequestError as exc:
        LOGGER.error("Vault request failed: %s", exc)
        raise CommandError("Vault API call failed") from exc
    finally:
        if client is not None:
            client.close()
