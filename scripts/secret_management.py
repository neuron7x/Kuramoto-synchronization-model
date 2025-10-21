"""Operational automation helpers for TradePulse secret management."""
from __future__ import annotations

import json
import os
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from application.secrets.rotation import SecretRotator, SecretRotationPolicy
from application.secrets.vault import (
    SecretAccessPolicy,
    SecretMetadata,
    SecretVault,
    SecretVaultError,
)
from core.utils.security import SecretDetector
from src.audit.audit_logger import AuditLogger
from src.audit.stores import JsonLinesAuditStore

_DEFAULT_ACTOR = "secops"
_DEFAULT_IP = "127.0.0.1"
_DEFAULT_ROTATION_DAYS = 30
_DEFAULT_SECRET_LENGTH = 64
_BREAKGLASS_LABEL = "breakglass"
_GLOBAL_ENVIRONMENT = "global"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _generate_secret(length: int = _DEFAULT_SECRET_LENGTH) -> str:
    if length < 16:
        raise ValueError("Secret length must be at least 16 characters")
    alphabet = string.ascii_letters + string.digits + "-_."
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _timedelta_from_days(days: int | None) -> timedelta | None:
    if days is None:
        return None
    if days <= 0:
        raise ValueError("Rotation interval must be positive")
    return timedelta(days=days)


def _serialize_metadata(metadata: SecretMetadata) -> dict[str, Any]:
    payload = metadata.model_dump()
    payload["labels"] = dict(metadata.labels)
    return payload


def _safe_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort on systems without POSIX permissions.
        pass


@dataclass
class SecretManagementSuite:
    """Bundle recurring secret-management workflows for ops and CI automation."""

    storage_path: Path
    master_key_path: Path
    audit_log_path: Path
    policy_path: Path
    audit_secret: str
    actor: str = _DEFAULT_ACTOR
    ip_address: str = _DEFAULT_IP
    rotation_default_days: int = _DEFAULT_ROTATION_DAYS

    _vault: SecretVault = field(init=False, repr=False)
    _audit_logger: AuditLogger = field(init=False, repr=False)
    _audit_store: JsonLinesAuditStore = field(init=False, repr=False)
    _policy_data: dict[str, dict[str, list[str]]] = field(init=False, repr=False)
    _master_key: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.storage_path = Path(self.storage_path)
        self.master_key_path = Path(self.master_key_path)
        self.audit_log_path = Path(self.audit_log_path)
        self.policy_path = Path(self.policy_path)
        if not self.audit_secret:
            raise ValueError("audit_secret must be provided")
        self._audit_store = JsonLinesAuditStore(self.audit_log_path)
        self._audit_logger = AuditLogger(secret=self.audit_secret, store=self._audit_store)
        self._master_key = self._load_or_create_master_key()
        self._policy_data = self._load_policy()
        self._vault = SecretVault(
            storage_path=self.storage_path,
            master_key=self._master_key,
            access_policy=SecretAccessPolicy(self._policy_data),
            audit_logger=self._audit_logger,
        )

    @property
    def vault(self) -> SecretVault:
        """Return the underlying :class:`SecretVault` instance."""

        return self._vault

    # ------------------------------------------------------------------
    # Provisioning helpers
    # ------------------------------------------------------------------
    def store_secret(
        self,
        name: str,
        value: str,
        *,
        environment: str | None = None,
        rotation_interval: timedelta | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> SecretMetadata:
        """Encrypt *value* and persist it in the vault with metadata."""

        effective_labels: dict[str, str] = dict(labels or {})
        if environment:
            effective_labels.setdefault("environment", environment)
        metadata = self._vault.put_secret(
            name,
            value,
            actor=self.actor,
            ip_address=self.ip_address,
            labels=effective_labels,
            rotation_interval=rotation_interval,
        )
        return metadata

    def rotate_secret(
        self,
        name: str,
        *,
        length: int = _DEFAULT_SECRET_LENGTH,
        reason: str | None = None,
    ) -> SecretMetadata:
        """Rotate *name* using a cryptographically strong generator."""

        generator = lambda: _generate_secret(length)
        return self._vault.rotate_secret(
            name,
            generator=generator,
            actor=self.actor,
            ip_address=self.ip_address,
            reason=reason or "scheduled_rotation",
        )

    def enforce_rotation_policies(self) -> list[dict[str, Any]]:
        """Evaluate rotation policies derived from stored metadata."""

        policies: list[SecretRotationPolicy] = []
        for metadata in self._vault.list_metadata():
            labels = metadata.labels or {}
            status = (labels.get("status") or "").lower()
            if status == "revoked":
                continue
            revoked_flag = labels.get("revoked")
            if isinstance(revoked_flag, str):
                if revoked_flag.lower() in {"true", "1", "yes"}:
                    continue
            elif revoked_flag:
                continue
            interval = metadata.rotation_interval
            if interval is None:
                continue
            policies.append(
                SecretRotationPolicy(
                    secret_name=metadata.name,
                    interval=interval,
                    generator=lambda length=_DEFAULT_SECRET_LENGTH: _generate_secret(length),
                    actor=self.actor,
                    ip_address=self.ip_address,
                    reason="policy_rotation",
                )
            )
        if not policies:
            return []
        rotator = SecretRotator(self._vault, policies, clock=_now_utc)
        rotated = rotator.evaluate()
        return [_serialize_metadata(item) for item in rotated]

    def issue_emergency_secret(
        self,
        name: str,
        *,
        length: int = _DEFAULT_SECRET_LENGTH,
        rotation_days: int | None = None,
        labels: Mapping[str, str] | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Provision a break-glass credential and optionally persist its value."""

        secret_value = _generate_secret(length)
        metadata_labels: dict[str, str] = {_BREAKGLASS_LABEL: "true", "status": "active"}
        metadata_labels.update(labels or {})
        rotation_interval = _timedelta_from_days(rotation_days)
        metadata = self.store_secret(
            name,
            secret_value,
            environment=metadata_labels.get("environment", _GLOBAL_ENVIRONMENT),
            rotation_interval=rotation_interval,
            labels=metadata_labels,
        )
        written_to: str | None = None
        if output_path is not None:
            _safe_write(Path(output_path), secret_value + "\n")
            written_to = str(Path(output_path))
        return {"metadata": _serialize_metadata(metadata), "secret_written_to": written_to}

    def revoke_secret(
        self,
        name: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Revoke *name* and return the resulting metadata."""

        metadata = self._vault.revoke_secret(
            name,
            actor=self.actor,
            ip_address=self.ip_address,
            reason=reason,
        )
        return _serialize_metadata(metadata)

    # ------------------------------------------------------------------
    # Governance and auditing
    # ------------------------------------------------------------------
    def audit_events(
        self,
        *,
        limit: int | None = None,
        secret: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent signed audit events, optionally filtered by secret name."""

        events: list[dict[str, Any]] = []
        for entry in self._audit_store.replay(verifier=self._audit_logger.verify):
            payload = entry.record.model_dump(mode="json")
            if secret:
                secret_name = (
                    payload.get("details", {})
                    .get("secret", {})
                    .get("name")
                )
                if secret_name != secret:
                    continue
            events.append({
                "sequence": entry.sequence,
                "chain_hash": entry.chain_hash,
                "record": payload,
            })
        if limit is not None:
            events = events[-limit:]
        return events

    def export_history(self) -> list[dict[str, Any]]:
        """Return metadata history for all managed secrets."""

        return sorted(
            (_serialize_metadata(metadata) for metadata in self._vault.list_metadata()),
            key=lambda item: (item["name"], item["version"]),
        )

    def apply_least_privilege_policy(self) -> dict[str, Any]:
        """Derive and persist a least-privilege access policy from secret labels."""

        policy_map: dict[str, dict[str, set[str]]] = {
            self.actor: {"read": {"*"}, "write": {"*"}}
        }
        for metadata in self._vault.list_metadata():
            name = metadata.name
            labels = metadata.labels
            owner = labels.get("owner")
            runtime_consumer = labels.get("runtime_consumer")
            if owner:
                actor_rules = policy_map.setdefault(owner, {"read": set(), "write": set()})
                actor_rules.setdefault("read", set()).add(name)
                actor_rules.setdefault("write", set()).add(name)
            if runtime_consumer:
                runtime_rules = policy_map.setdefault(runtime_consumer, {"read": set(), "write": set()})
                runtime_rules.setdefault("read", set()).add(name)
        sanitised = {
            actor: {action: sorted(resources) for action, resources in actions.items()}
            for actor, actions in policy_map.items()
        }
        self._policy_data = sanitised
        self._persist_policy()
        self._vault.set_policy_rules(sanitised)
        return {"policy": sanitised}

    def validate_environment(self, environment: str) -> dict[str, Any]:
        """Ensure secrets are scoped to the provided *environment*."""

        mismatches: list[dict[str, Any]] = []
        for metadata in self._vault.list_metadata():
            labels = metadata.labels
            target_env = labels.get("environment", _GLOBAL_ENVIRONMENT)
            if target_env not in {environment, _GLOBAL_ENVIRONMENT}:
                mismatches.append(
                    {
                        "name": metadata.name,
                        "expected_environment": target_env,
                    }
                )
        return {"environment": environment, "mismatches": mismatches}

    # ------------------------------------------------------------------
    # Runtime integration
    # ------------------------------------------------------------------
    def inject_runtime(
        self,
        assignments: Mapping[str, str],
        *,
        destination: Path,
        format: str = "env",
    ) -> dict[str, Any]:
        """Render secrets into a runtime-friendly format."""

        secrets_payload: dict[str, str] = {}
        for variable, secret_name in assignments.items():
            value = self._vault.access_secret(
                secret_name,
                actor=self.actor,
                ip_address=self.ip_address,
            )
            secrets_payload[variable] = value
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if format == "env":
            lines = [f"{key}={value}" for key, value in secrets_payload.items()]
            _safe_write(destination, "\n".join(lines) + "\n")
        elif format == "json":
            _safe_write(destination, json.dumps(secrets_payload, indent=2, sort_keys=True))
        else:
            raise ValueError("Unsupported format for runtime injection")
        return {
            "written_to": str(destination),
            "variables": sorted(secrets_payload.keys()),
        }

    # ------------------------------------------------------------------
    # Continuous delivery automation
    # ------------------------------------------------------------------
    def scan_repository(self, repo_root: Path) -> dict[str, Any]:
        """Perform leak scanning for *repo_root* using the bundled detector."""

        detector = SecretDetector()
        findings = detector.scan_directory(str(repo_root))
        formatted = {
            path: [
                {"type": secret_type, "line": line_num, "excerpt": line}
                for secret_type, line_num, line in entries
            ]
            for path, entries in findings.items()
        }
        return {"findings": formatted, "total_findings": sum(len(v) for v in formatted.values())}

    def run_ci_checks(
        self,
        repo_root: Path,
        *,
        rotation_grace: timedelta | None = None,
        environment: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate governance checks for CI pipelines."""

        leak_report = self.scan_repository(repo_root)
        rotation_report = self._rotation_health(rotation_grace)
        policy_report = self._policy_violations()
        environment_report = (
            self.validate_environment(environment) if environment else None
        )
        action_required = any(
            [
                leak_report["total_findings"] > 0,
                rotation_report["overdue"],
                rotation_report["due_soon"],
                policy_report["violations"],
                environment_report and environment_report["mismatches"],
            ]
        )
        return {
            "status": "action_required" if action_required else "ok",
            "leaks": leak_report,
            "rotation": rotation_report,
            "policy": policy_report,
            "environment": environment_report,
        }

    # ------------------------------------------------------------------
    # Resilience validation
    # ------------------------------------------------------------------
    def run_failure_tests(self) -> dict[str, Any]:
        """Execute deterministic failure drills to ensure guard-rails are active."""

        results: list[dict[str, Any]] = []

        def _record(test: str, passed: bool, detail: str) -> None:
            results.append({"test": test, "passed": passed, "detail": detail})

        try:
            self._vault.access_secret(
                "__nonexistent__",
                actor=self.actor,
                ip_address=self.ip_address,
            )
            _record("access_unknown_secret", False, "Unexpectedly succeeded")
        except SecretVaultError:
            _record("access_unknown_secret", True, "Access correctly denied")

        drill_secret = f"ops/healthcheck/{uuid4().hex}"
        temp_value = _generate_secret(24)
        self.store_secret(
            drill_secret,
            temp_value,
            environment=_GLOBAL_ENVIRONMENT,
            labels={"owner": self.actor, "runtime_consumer": "healthcheck"},
        )
        self.revoke_secret(drill_secret, reason="healthcheck_drill")
        try:
            self._vault.access_secret(
                drill_secret,
                actor=self.actor,
                ip_address=self.ip_address,
            )
            _record("revoked_secret_blocked", False, "Revoked secret remained accessible")
        except SecretVaultError:
            _record("revoked_secret_blocked", True, "Revoked secret access denied")

        storage_exists = self.storage_path.exists()
        _record("storage_available", storage_exists, "Vault storage path present")

        master_exists = self.master_key_path.exists()
        _record("master_key_available", master_exists, "Master key file present")

        audit_ok = self._audit_store.verify_integrity(
            verifier=self._audit_logger.verify
        )
        _record("audit_log_integrity", audit_ok, "Audit chain verified")

        return {
            "results": results,
            "passed": all(item["passed"] for item in results),
        }

    def verify_recovery(self) -> dict[str, Any]:
        """Validate that the vault can be reconstructed from durable assets."""

        recovery_vault = SecretVault(
            storage_path=self.storage_path,
            master_key=self._master_key,
            access_policy=SecretAccessPolicy(self._policy_data),
        )
        secret_count = len(recovery_vault.list_metadata())
        audit_chain_ok = self._audit_store.verify_integrity(
            verifier=self._audit_logger.verify
        )
        return {
            "secret_count": secret_count,
            "audit_log_verified": audit_chain_ok,
            "storage_path": str(self.storage_path),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_or_create_master_key(self) -> bytes:
        if self.master_key_path.exists():
            key = self.master_key_path.read_text(encoding="utf-8").strip()
            if not key:
                raise ValueError("Master key file is empty")
            return key.encode("utf-8")
        key_bytes = SecretVault.generate_key()
        _safe_write(self.master_key_path, key_bytes.decode("utf-8") + "\n")
        return key_bytes

    def _load_policy(self) -> dict[str, dict[str, list[str]]]:
        if not self.policy_path.exists():
            return {self.actor: {"read": ["*"], "write": ["*"]}}
        raw = self.policy_path.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
        policy: dict[str, dict[str, list[str]]] = {}
        for actor, actions in data.items():
            if not isinstance(actions, Mapping):
                continue
            sanitized_actions: dict[str, list[str]] = {}
            for action, resources in actions.items():
                if not isinstance(resources, Iterable):
                    continue
                sanitized_actions[str(action)] = sorted({str(item) for item in resources})
            if sanitized_actions:
                policy[str(actor)] = sanitized_actions
        if not policy:
            policy = {self.actor: {"read": ["*"], "write": ["*"]}}
        return policy

    def _persist_policy(self) -> None:
        payload = json.dumps(self._policy_data, indent=2, sort_keys=True)
        _safe_write(self.policy_path, payload)

    def _rotation_health(self, grace: timedelta | None) -> dict[str, Any]:
        now = _now_utc()
        if grace is None:
            grace = timedelta(days=self.rotation_default_days)
        overdue: list[dict[str, Any]] = []
        due_soon: list[dict[str, Any]] = []
        for metadata in self._vault.list_metadata():
            interval = metadata.rotation_interval
            if interval is None:
                continue
            next_due = metadata.updated_at + interval
            item = {
                "name": metadata.name,
                "next_due": next_due.isoformat(),
                "interval_seconds": interval.total_seconds(),
            }
            if next_due <= now:
                overdue.append(item)
            elif next_due <= now + grace:
                due_soon.append(item)
        return {"overdue": overdue, "due_soon": due_soon}

    def _policy_violations(self) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        for actor, actions in self._policy_data.items():
            if actor == self.actor:
                continue
            for action, resources in actions.items():
                if "*" in resources:
                    violations.append(
                        {"actor": actor, "action": action, "reason": "wildcard access"}
                    )
        return {"violations": violations}
