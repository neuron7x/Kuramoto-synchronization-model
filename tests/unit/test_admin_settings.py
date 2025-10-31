from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.configuration import ConfigurationStoreError
from application.secrets.manager import secret_caller_context
from application.secrets.vault import SecretVault
from application.settings import AdminApiSettings, ConfigNamespaceSettings
from src.audit.audit_logger import AuditLogger


def test_admin_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("TRADEPULSE_AUDIT_SECRET", "env-secret-value")
    monkeypatch.setenv("TRADEPULSE_ADMIN_SUBJECT", "env-operator")
    monkeypatch.setenv("TRADEPULSE_ADMIN_RATE_LIMIT_MAX_ATTEMPTS", "7")
    monkeypatch.setenv("TRADEPULSE_ADMIN_RATE_LIMIT_INTERVAL_SECONDS", "15")
    monkeypatch.setenv(
        "TRADEPULSE_AUDIT_WEBHOOK_URL", "https://audit.example.com/ingest"
    )

    settings = AdminApiSettings()

    assert settings.audit_secret.get_secret_value() == "env-secret-value"
    assert settings.admin_subject == "env-operator"
    assert settings.admin_rate_limit_max_attempts == 7
    assert settings.admin_rate_limit_interval_seconds == 15.0
    assert str(settings.audit_webhook_url) == "https://audit.example.com/ingest"


def test_admin_settings_accepts_explicit_values(monkeypatch):
    monkeypatch.delenv("TRADEPULSE_AUDIT_SECRET", raising=False)

    settings = AdminApiSettings(
        audit_secret="explicit-secret-value",
        admin_subject="explicit",
        admin_rate_limit_max_attempts=3,
        admin_rate_limit_interval_seconds=45.0,
        audit_webhook_url="https://audit.example.com/explicit",
    )

    assert settings.audit_secret.get_secret_value() == "explicit-secret-value"
    assert settings.admin_subject == "explicit"
    assert settings.admin_rate_limit_max_attempts == 3
    assert settings.admin_rate_limit_interval_seconds == 45.0
    assert str(settings.audit_webhook_url) == "https://audit.example.com/explicit"


def test_secret_manager_prefers_file_value(tmp_path):
    path = tmp_path / "audit_secret"
    path.write_text("file-backed-secret-value", encoding="utf-8")
    settings = AdminApiSettings(
        audit_secret="fallback-secret-value",
        audit_secret_path=path,
        secret_refresh_interval_seconds=0.1,
    )

    manager = settings.build_secret_manager()

    assert manager.get("audit_secret") == "file-backed-secret-value"
    path.write_text("rotated-file-secret-value", encoding="utf-8")
    manager.force_refresh("audit_secret")
    assert manager.get("audit_secret") == "rotated-file-secret-value"


def test_two_factor_secret_path_overrides_inline_value(tmp_path):
    path = tmp_path / "two_factor_secret"
    path.write_text("JBSWY3DPEHPK3PXP", encoding="utf-8")
    settings = AdminApiSettings(
        audit_secret="explicit-secret-value",
        two_factor_secret="MFRGGZDFMZTWQ2LK",
        two_factor_secret_path=path,
    )

    manager = settings.build_secret_manager()

    assert manager.get("two_factor_secret") == "JBSWY3DPEHPK3PXP"


def test_siem_secret_path_satisfies_validation(tmp_path):
    secret_path = tmp_path / "siem_secret"
    secret_path.write_text("siem-client-secret-value", encoding="utf-8")

    settings = AdminApiSettings(
        audit_secret="explicit-secret-value",
        siem_endpoint="https://siem.example.com/ingest",
        siem_client_id="siem-client",
        siem_client_secret_path=secret_path,
    )

    manager = settings.build_secret_manager()
    assert manager.get("siem_client_secret") == "siem-client-secret-value"


def test_missing_siem_secret_raises(monkeypatch):
    monkeypatch.delenv("TRADEPULSE_AUDIT_SECRET", raising=False)
    with pytest.raises(ValueError):
        AdminApiSettings(
            audit_secret="explicit-secret-value",
            siem_endpoint="https://siem.example.com/ingest",
            siem_client_id="siem-client",
        )


def test_invalid_two_factor_secret_rejected(monkeypatch):
    monkeypatch.delenv("TRADEPULSE_TWO_FACTOR_SECRET", raising=False)
    with pytest.raises(ValueError):
        AdminApiSettings(
            audit_secret="explicit-secret-value",
            two_factor_secret="invalid-secret",
        )


def test_secret_manager_audits_get_operations():
    audit_logger = MagicMock(spec=AuditLogger)
    settings = AdminApiSettings(audit_secret="audit-secret-value")
    manager = settings.build_secret_manager(audit_logger_factory=lambda _: audit_logger)

    with secret_caller_context(actor="unit", ip_address="198.51.100.10"):
        secret = manager.get("audit_secret")

    assert secret == "audit-secret-value"
    audit_logger.log_event.assert_any_call(
        event_type="secret_get",
        actor="unit",
        ip_address="198.51.100.10",
        details={
            "operation": "get",
            "status": "success",
            "secret": {
                "name": "audit_secret",
                "path": None,
                "min_length": 16,
                "has_fallback": True,
                "cached": True,
                "refresh_interval_seconds": 300.0,
                "managed": False,
            },
        },
    )


def test_secret_manager_audits_provider_resolution():
    audit_logger = MagicMock(spec=AuditLogger)
    settings = AdminApiSettings(audit_secret="audit-secret-value")
    manager = settings.build_secret_manager(audit_logger_factory=lambda _: audit_logger)

    with secret_caller_context(actor="issuer", ip_address="203.0.113.20"):
        resolver = manager.provider("audit_secret")

    audit_logger.log_event.assert_any_call(
        event_type="secret_provider",
        actor="issuer",
        ip_address="203.0.113.20",
        details={
            "operation": "provider",
            "status": "issued",
            "secret": {
                "name": "audit_secret",
                "path": None,
                "min_length": 16,
                "has_fallback": True,
                "cached": True,
                "refresh_interval_seconds": 300.0,
                "managed": False,
            },
        },
    )
    audit_logger.reset_mock()

    with secret_caller_context(actor="resolver", ip_address="198.51.100.30"):
        value = resolver()

    assert value == "audit-secret-value"
    audit_logger.log_event.assert_called_once_with(
        event_type="secret_provider_access",
        actor="resolver",
        ip_address="198.51.100.30",
        details={
            "operation": "provider_access",
            "status": "success",
            "secret": {
                "name": "audit_secret",
                "path": None,
                "min_length": 16,
                "has_fallback": True,
                "cached": True,
                "refresh_interval_seconds": 300.0,
                "managed": False,
            },
        },
    )


def test_secret_manager_audits_force_refresh(tmp_path):
    audit_logger = MagicMock(spec=AuditLogger)
    path = tmp_path / "refreshable"
    path.write_text("initial-value", encoding="utf-8")
    settings = AdminApiSettings(
        audit_secret="fallback-secret-value",
        audit_secret_path=path,
        secret_refresh_interval_seconds=0.1,
    )

    manager = settings.build_secret_manager(audit_logger_factory=lambda _: audit_logger)

    path.write_text("rotated-value", encoding="utf-8")
    with secret_caller_context(actor="rotator", ip_address="192.0.2.40"):
        manager.force_refresh("audit_secret")

    audit_logger.log_event.assert_any_call(
        event_type="secret_force_refresh",
        actor="rotator",
        ip_address="192.0.2.40",
        details={
            "operation": "force_refresh",
            "status": "success",
            "secret": {
                "name": "audit_secret",
                "path": str(path),
                "min_length": 16,
                "has_fallback": True,
                "cached": True,
                "refresh_interval_seconds": 0.1,
                "managed": True,
            },
        },
    )


def test_build_configuration_store_provisions_namespaces(tmp_path):
    master_key = SecretVault.generate_key().decode("utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "config.yaml.j2").write_text(
        "endpoint={{ endpoint }}\n", encoding="utf-8"
    )

    settings = AdminApiSettings(
        audit_secret="audit-secret-value",
        config_vault_path=tmp_path / "vault.json",
        config_vault_master_key=master_key,
        config_template_directory=template_dir,
        config_namespaces=(
            ConfigNamespaceSettings(
                name="prod", readers=("deploy",), writers=("ops",), allow_ci=True
            ),
        ),
    )
    audit_logger = AuditLogger(secret="audit-secret-value")
    store = settings.build_configuration_store(audit_logger=audit_logger)

    store.write_configuration(
        "prod",
        "service",
        {"endpoint": "https://api.tradepulse.invalid"},
        actor="ops",
        ip_address="198.51.100.10",
    )
    config = store.read_configuration(
        "prod",
        "service",
        actor="deploy",
        ip_address="198.51.100.11",
    )
    assert config["endpoint"] == "https://api.tradepulse.invalid"

    store.write_secret(
        "prod",
        "api_key",
        "prod-secret",
        actor="ops",
        ip_address="198.51.100.10",
    )
    env: dict[str, str] = {}
    metadata = store.inject_into_ci(
        "prod",
        {"API_KEY": "api_key"},
        actor="deploy",
        ip_address="198.51.100.11",
        environment=env,
    )
    assert env["API_KEY"] == "prod-secret"
    assert metadata["API_KEY"]["secret"] == "api_key"

    with pytest.raises(ConfigurationStoreError):
        store.read_secret(
            "prod",
            "api_key",
            actor="intruder",
            ip_address="198.51.100.200",
        )


def test_default_access_policy_grants_risk_officers():
    settings = AdminApiSettings(
        audit_secret="explicit-secret-value",
        two_factor_secret="JBSWY3DPEHPK3PXP",
    )

    controller = settings.build_access_controller()

    assert controller.is_allowed(
        "read_kill_switch_state",
        actor="admin-user",
        roles=("risk:officer",),
    )
    assert controller.is_allowed(
        "engage_kill_switch",
        actor="admin-user",
        roles=("risk:officer",),
    )
    assert controller.is_allowed(
        "reset_kill_switch",
        actor="admin-user",
        roles=("risk:officer",),
    )
