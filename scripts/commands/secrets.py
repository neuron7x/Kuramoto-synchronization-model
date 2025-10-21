"""Secrets automation commands backed by HashiCorp Vault."""

from __future__ import annotations

import json
import logging
import os
from argparse import ArgumentParser, _SubParsersAction
from datetime import timedelta
from pathlib import Path
from typing import Mapping, Sequence

from application.secrets.hashicorp import (
    DynamicCredentialManager,
    JWTOIDCAuthenticator,
    StaticTokenAuthenticator,
    VaultClient,
    VaultClientConfig,
    VaultRequestError,
)
from application.secrets.vault import SecretVaultError
from scripts.commands.base import CommandError, register
from scripts.secret_management import SecretManagementSuite

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "secrets-issue-dynamic",
        help="Issue short-lived credentials from Vault and persist them to disk.",
    )
    _configure_issue_dynamic(parser)

    manage_parser = subparsers.add_parser(
        "secrets-manage",
        help="Run comprehensive secret-management playbooks and governance checks.",
    )
    _configure_manage(manage_parser)


def _configure_issue_dynamic(parser: ArgumentParser) -> None:
    parser.add_argument("--address", required=True, help="Vault base URL (e.g. https://vault.service:8200)")
    parser.add_argument("--namespace", default=None, help="Optional Vault namespace")
    parser.add_argument("--mount", default="database", help="Secret engine mount path (default: database)")
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
    parser.add_argument("--oidc-mount", default="oidc", help="OIDC auth mount path (default: oidc)")
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


def _configure_manage(parser: ArgumentParser) -> None:
    parser.add_argument("--storage-path", type=Path, required=True, help="Path to the encrypted vault data file")
    parser.add_argument("--master-key-path", type=Path, required=True, help="Path to the master key file")
    parser.add_argument("--audit-log-path", type=Path, required=True, help="Destination for append-only audit logs")
    parser.add_argument("--policy-path", type=Path, required=True, help="File used to persist least-privilege policy rules")
    parser.add_argument("--audit-secret", help="Inline audit secret for signing records")
    parser.add_argument("--audit-secret-env", help="Environment variable containing the audit secret")
    parser.add_argument("--actor", default="secops", help="Actor name used for management operations")
    parser.add_argument("--ip-address", default="127.0.0.1", help="IP address recorded for audit events")
    parser.add_argument(
        "--rotation-default-days",
        type=int,
        default=30,
        help="Default rotation grace period in days when unspecified",
    )
    parser.set_defaults(command="secrets-manage", handler=handle_secrets_manage)

    operations = parser.add_subparsers(dest="operation", required=True)

    encrypt = operations.add_parser(
        "encrypt",
        help="Encrypt and persist a secret with optional labels and rotation interval.",
    )
    encrypt.add_argument("--name", required=True, help="Logical secret name (e.g. services/api-token)")
    encrypt.add_argument("--value", help="Inline secret value to persist")
    encrypt.add_argument("--value-file", type=Path, help="Path to a file containing the secret value")
    encrypt.add_argument("--environment", help="Environment label applied to the secret")
    encrypt.add_argument(
        "--rotation-days",
        type=int,
        help="Optional rotation interval in days",
    )
    encrypt.add_argument(
        "--label",
        action="append",
        default=[],
        help="Additional metadata labels in key=value form (can be repeated)",
    )

    rotate = operations.add_parser(
        "rotate",
        help="Rotate a secret on-demand using the built-in generator.",
    )
    rotate.add_argument("--name", required=True, help="Secret name to rotate")
    rotate.add_argument("--length", type=int, default=64, help="Desired length of the generated secret")
    rotate.add_argument("--reason", help="Reason string captured in the audit log")

    policy_rotate = operations.add_parser(
        "rotate-policies",
        help="Evaluate rotation policies and rotate any secrets that are due.",
    )

    audit = operations.add_parser(
        "audit",
        help="Export signed audit events for review.",
    )
    audit.add_argument("--limit", type=int, help="Maximum number of events to output")
    audit.add_argument("--secret", help="Filter audit events to a specific secret")

    history = operations.add_parser(
        "history",
        help="List metadata history for all managed secrets.",
    )
    history.add_argument("--limit", type=int, help="Optional limit for the most recent entries")

    apply_policy = operations.add_parser(
        "apply-policy",
        help="Derive and persist a least-privilege access policy from secret labels.",
    )

    inject = operations.add_parser(
        "inject-runtime",
        help="Materialise secrets for runtime consumption as env or JSON payloads.",
    )
    inject.add_argument("--destination", type=Path, required=True, help="File that will receive the rendered payload")
    inject.add_argument(
        "--format",
        choices=("env", "json"),
        default="env",
        help="Output format for the runtime payload",
    )
    inject.add_argument(
        "--assign",
        action="append",
        required=True,
        help="Runtime assignment in the form NAME=secret/path (repeat per variable)",
    )

    ci = operations.add_parser(
        "ci-check",
        help="Run leak scanning, rotation health, and policy compliance checks for CI.",
    )
    ci.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root for leak scanning")
    ci.add_argument(
        "--rotation-grace-days",
        type=int,
        help="Additional grace period in days before marking a rotation as due soon",
    )
    ci.add_argument("--environment", help="Target environment name for validation")

    scan = operations.add_parser(
        "scan",
        help="Only run repository leak scanning.",
    )
    scan.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root to scan")

    validate_env = operations.add_parser(
        "validate-env",
        help="Validate that stored secrets match the provided environment scope.",
    )
    validate_env.add_argument("--environment", required=True, help="Environment name to validate")

    emergency = operations.add_parser(
        "emergency",
        help="Issue a break-glass credential and optionally persist it securely.",
    )
    emergency.add_argument("--name", required=True, help="Secret name for the emergency credential")
    emergency.add_argument("--length", type=int, default=64, help="Length of the generated secret")
    emergency.add_argument("--rotation-days", type=int, help="Optional rotation interval in days")
    emergency.add_argument(
        "--label",
        action="append",
        default=[],
        help="Additional labels in key=value form",
    )
    emergency.add_argument("--output", type=Path, help="Optional file where the secret value will be written")

    revoke = operations.add_parser(
        "revoke",
        help="Revoke an existing secret and prevent future access.",
    )
    revoke.add_argument("--name", required=True, help="Secret name to revoke")
    revoke.add_argument("--reason", help="Reason recorded for the revocation")

    failure = operations.add_parser(
        "failure-tests",
        help="Run deterministic failure drills to validate guard-rails.",
    )

    recovery = operations.add_parser(
        "recovery",
        help="Summarise recovery readiness from durable vault assets.",
    )

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
    raise CommandError("A JWT must be supplied via --jwt, --jwt-env, or --jwt-path for OIDC auth")


def _load_audit_secret(args: object) -> str:
    secret = getattr(args, "audit_secret", None)
    if secret:
        return str(secret)
    secret_env = getattr(args, "audit_secret_env", None)
    if secret_env:
        value = os.getenv(secret_env)
        if value:
            return value
        raise CommandError(
            f"Environment variable {secret_env} is not set or empty for the audit secret"
        )
    raise CommandError("Provide --audit-secret or --audit-secret-env for secret management")


def _load_secret_value(args: object) -> str:
    value = getattr(args, "value", None)
    if value:
        return str(value)
    value_file: Path | None = getattr(args, "value_file", None)
    if value_file is not None:
        if not value_file.exists():
            raise CommandError(f"Secret value file {value_file} does not exist")
        return value_file.read_text(encoding="utf-8").strip()
    raise CommandError("Provide the secret value via --value or --value-file")


def _parse_key_value_pairs(pairs: Sequence[str] | None) -> dict[str, str]:
    if not pairs:
        return {}
    result: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise CommandError(f"Invalid key=value pair: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise CommandError("Label keys must not be empty")
        result[key] = value
    return result


def _parse_assignments(assignments: Sequence[str]) -> Mapping[str, str]:
    if not assignments:
        raise CommandError("At least one --assign entry is required")
    mapping: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise CommandError(f"Invalid assignment: {assignment}")
        variable, secret_name = assignment.split("=", 1)
        variable = variable.strip()
        secret_name = secret_name.strip()
        if not variable or not secret_name:
            raise CommandError(f"Invalid assignment: {assignment}")
        mapping[variable] = secret_name
    return mapping


def _rotation_interval_from_days(days: int | None) -> timedelta | None:
    if days is None:
        return None
    if days <= 0:
        raise CommandError("Rotation days must be positive")
    return timedelta(days=days)


def _build_suite(args: object) -> SecretManagementSuite:
    try:
        audit_secret = _load_audit_secret(args)
        rotation_default = int(getattr(args, "rotation_default_days"))
        return SecretManagementSuite(
            storage_path=Path(getattr(args, "storage_path")),
            master_key_path=Path(getattr(args, "master_key_path")),
            audit_log_path=Path(getattr(args, "audit_log_path")),
            policy_path=Path(getattr(args, "policy_path")),
            audit_secret=audit_secret,
            actor=str(getattr(args, "actor")),
            ip_address=str(getattr(args, "ip_address")),
            rotation_default_days=rotation_default,
        )
    except ValueError as exc:
        raise CommandError(str(exc)) from exc


def _dump_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


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


@register("secrets-manage")
def handle_secrets_manage(args: object) -> int:
    try:
        suite = _build_suite(args)
        operation = getattr(args, "operation")
        if operation == "encrypt":
            value = _load_secret_value(args)
            labels = _parse_key_value_pairs(getattr(args, "label", []))
            rotation_days = getattr(args, "rotation_days", None)
            metadata = suite.store_secret(
                name=str(getattr(args, "name")),
                value=value,
                environment=getattr(args, "environment", None),
                rotation_interval=_rotation_interval_from_days(rotation_days),
                labels=labels,
            )
            _dump_json({"metadata": metadata.model_dump()})
        elif operation == "rotate":
            metadata = suite.rotate_secret(
                name=str(getattr(args, "name")),
                length=int(getattr(args, "length")),
                reason=getattr(args, "reason", None),
            )
            _dump_json({"metadata": metadata.model_dump()})
        elif operation == "rotate-policies":
            rotated = suite.enforce_rotation_policies()
            _dump_json({"rotated": rotated})
        elif operation == "audit":
            events = suite.audit_events(
                limit=getattr(args, "limit", None),
                secret=getattr(args, "secret", None),
            )
            _dump_json({"events": events})
        elif operation == "history":
            entries = suite.export_history()
            limit = getattr(args, "limit", None)
            if limit is not None:
                entries = entries[-int(limit) :]
            _dump_json({"history": entries})
        elif operation == "apply-policy":
            result = suite.apply_least_privilege_policy()
            _dump_json(result)
        elif operation == "inject-runtime":
            assignments = _parse_assignments(getattr(args, "assign"))
            result = suite.inject_runtime(
                assignments,
                destination=Path(getattr(args, "destination")),
                format=str(getattr(args, "format")),
            )
            _dump_json(result)
        elif operation == "ci-check":
            grace = _rotation_interval_from_days(getattr(args, "rotation_grace_days", None))
            result = suite.run_ci_checks(
                Path(getattr(args, "repo_root")),
                rotation_grace=grace,
                environment=getattr(args, "environment", None),
            )
            _dump_json(result)
            if result.get("status") != "ok":
                return 2
        elif operation == "scan":
            result = suite.scan_repository(Path(getattr(args, "repo_root")))
            _dump_json(result)
            if result.get("total_findings", 0) > 0:
                return 2
        elif operation == "validate-env":
            result = suite.validate_environment(str(getattr(args, "environment")))
            _dump_json(result)
            if result["mismatches"]:
                return 2
        elif operation == "emergency":
            labels = _parse_key_value_pairs(getattr(args, "label", []))
            output_path = getattr(args, "output", None)
            result = suite.issue_emergency_secret(
                name=str(getattr(args, "name")),
                length=int(getattr(args, "length")),
                rotation_days=getattr(args, "rotation_days", None),
                labels=labels,
                output_path=Path(output_path) if output_path else None,
            )
            _dump_json(result)
        elif operation == "revoke":
            result = suite.revoke_secret(
                name=str(getattr(args, "name")),
                reason=getattr(args, "reason", None),
            )
            _dump_json({"metadata": result})
        elif operation == "failure-tests":
            result = suite.run_failure_tests()
            _dump_json(result)
            if not result.get("passed", False):
                return 2
        elif operation == "recovery":
            result = suite.verify_recovery()
            _dump_json(result)
        else:
            raise CommandError(f"Unsupported secret management operation '{operation}'")
        return 0
    except SecretVaultError as exc:
        raise CommandError(str(exc)) from exc

