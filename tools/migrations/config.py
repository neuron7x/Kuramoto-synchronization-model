"""Configuration helpers for the TradePulse migration toolkit."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml


@dataclass(slots=True)
class IndexExpectation:
    """Expected index definition for schema validation."""

    name: str
    columns: tuple[str, ...] = ()
    unique: bool | None = None


@dataclass(slots=True)
class TriggerExpectation:
    """Expected trigger definition for schema validation."""

    name: str
    function: str | None = None
    event: str | None = None


@dataclass(slots=True)
class TableExpectation:
    """Container for index and trigger expectations."""

    indexes: tuple[IndexExpectation, ...] = ()
    triggers: tuple[TriggerExpectation, ...] = ()


@dataclass(slots=True)
class SchemaExpectations:
    """Schema expectations parsed from configuration files."""

    tables: Mapping[str, TableExpectation] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "SchemaExpectations":
        if not payload:
            return cls()

        tables: MutableMapping[str, TableExpectation] = {}
        for table_name, table_payload in payload.get("tables", {}).items():
            indexes: list[IndexExpectation] = []
            for idx in table_payload.get("indexes", []) or []:
                indexes.append(
                    IndexExpectation(
                        name=idx["name"],
                        columns=tuple(idx.get("columns", []) or ()),
                        unique=idx.get("unique"),
                    )
                )

            triggers: list[TriggerExpectation] = []
            for trigger in table_payload.get("triggers", []) or []:
                triggers.append(
                    TriggerExpectation(
                        name=trigger["name"],
                        function=trigger.get("function"),
                        event=trigger.get("event"),
                    )
                )

            tables[table_name] = TableExpectation(
                indexes=tuple(indexes),
                triggers=tuple(triggers),
            )

        return cls(tables=tables)


@dataclass(slots=True)
class BackupSettings:
    """Backup configuration for migrations."""

    enabled: bool = False
    directory: Path | None = None
    tool: str = "pg_dump"
    retain_last: int = 5


@dataclass(slots=True)
class AlertSettings:
    """Notification settings for migration failures."""

    enabled: bool = False
    webhook_url: str | None = None
    channel: str | None = None


@dataclass(slots=True)
class MigrationSettings:
    """Runtime configuration for the migration toolkit."""

    alembic_ini: Path = Path("alembic.ini")
    database_url: str | None = None
    artifacts_dir: Path = Path("reports/migrations")
    lock_timeout_seconds: int | None = 5
    statement_timeout_seconds: int | None = 60
    default_timebox_seconds: int | None = 300
    schema: SchemaExpectations = field(default_factory=SchemaExpectations)
    backup: BackupSettings = field(default_factory=BackupSettings)
    alerting: AlertSettings = field(default_factory=AlertSettings)
    validation_files: tuple[Path, ...] = ()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MigrationSettings":
        config_path = Path(path) if path else None
        payload: Mapping[str, Any] | None = None
        if config_path and config_path.exists():
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        elif config_path:
            raise FileNotFoundError(f"Migration config not found: {config_path}")

        return cls.from_mapping(payload or {})

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MigrationSettings":
        schema = SchemaExpectations.from_mapping(payload.get("schema"))

        backup_config = payload.get("backup", {}) or {}
        backup = BackupSettings(
            enabled=bool(backup_config.get("enabled", False)),
            directory=Path(backup_config["directory"]) if backup_config.get("directory") else None,
            tool=backup_config.get("tool", "pg_dump"),
            retain_last=int(backup_config.get("retain_last", 5)),
        )

        alert_config = payload.get("alerts", {}) or {}
        alerting = AlertSettings(
            enabled=bool(alert_config.get("enabled", False)),
            webhook_url=alert_config.get("webhook_url"),
            channel=alert_config.get("channel"),
        )

        validation_files = tuple(
            Path(item) for item in payload.get("validations", {}).get("files", [])
        )

        artifacts_dir = payload.get("artifacts", {}).get("directory", "reports/migrations")

        return cls(
            alembic_ini=Path(payload.get("alembic_ini", "alembic.ini")),
            database_url=payload.get("database_url"),
            artifacts_dir=Path(artifacts_dir),
            lock_timeout_seconds=_optional_int(payload.get("lock_timeout_seconds", 5)),
            statement_timeout_seconds=_optional_int(
                payload.get("statement_timeout_seconds", 60)
            ),
            default_timebox_seconds=_optional_int(payload.get("default_timebox_seconds", 300)),
            schema=schema,
            backup=backup,
            alerting=alerting,
            validation_files=validation_files,
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
