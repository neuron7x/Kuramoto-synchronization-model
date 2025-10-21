"""Execution engine for database migrations."""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import subprocess

import httpx
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
 
import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

from .config import MigrationSettings, SchemaExpectations
from .validators import DataValidationError, ValidationResult, ValidationSuite


@dataclass(slots=True)
class MigrationResult:
    """Structured response from migration operations."""

    succeeded: bool
    started_at: dt.datetime
    finished_at: dt.datetime | None
    details: Mapping[str, Any]
    artifact_path: Path | None = None


@dataclass(slots=True)
class MigrationOutcome:
    """Outcome metadata stored as verification artifacts."""

    target: str
    success: bool
    dry_run: bool
    started_at: dt.datetime
    finished_at: dt.datetime | None
    details: Mapping[str, Any]

    def to_json(self) -> str:
        payload = {
            "target": self.target,
            "success": self.success,
            "dry_run": self.dry_run,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "details": self.details,
        }
        return json.dumps(payload, indent=2, sort_keys=True)


class MigrationManager:
    """High-level interface that wraps Alembic commands with guardrails."""

    def __init__(self, settings: MigrationSettings, *, engine: sa.Engine | None = None) -> None:
        self.settings = settings
        self._engine = engine or sa.create_engine(settings.database_url or "sqlite://")
        self._alembic_cfg = self._load_config(settings)
        self._artifacts_dir = settings.artifacts_dir
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_config(settings: MigrationSettings) -> AlembicConfig:
        cfg = AlembicConfig(str(settings.alembic_ini))
        if settings.database_url:
            cfg.set_main_option("sqlalchemy.url", settings.database_url)
        cfg.attributes.setdefault("configure_logger", False)
        return cfg

    @property
    def engine(self) -> sa.Engine:
        return self._engine

    def generate_revision(
        self,
        message: str,
        *,
        autogenerate: bool = True,
        branch_label: str | None = None,
        version_path: str | None = None,
    ) -> Path:
        command.revision(
            self._alembic_cfg,
            message=message,
            autogenerate=autogenerate,
            branch_label=branch_label,
            version_path=version_path,
        )
        script_location = Path(self._alembic_cfg.get_main_option("script_location"))
        script_directory = ScriptDirectory.from_config(self._alembic_cfg)
        latest = script_directory.get_current_head()
        return Path(script_location, "versions", f"{latest}.py")

    def dry_run(self, target: str = "head") -> MigrationOutcome:
        start = dt.datetime.now(dt.timezone.utc)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            command.upgrade(self._alembic_cfg, target, sql=True)
        sql_script = buffer.getvalue()
        finished = dt.datetime.now(dt.timezone.utc)
        artifact = self._write_artifact(
            f"dry-run-{start:%Y%m%d-%H%M%S}.sql",
            sql_script,
            as_bytes=False,
        )
        details = {"sql": sql_script, "artifact": str(artifact)}
        outcome = MigrationOutcome(
            target=target,
            success=True,
            dry_run=True,
            started_at=start,
            finished_at=finished,
            details=details,
        )
        self._write_artifact(
            f"dry-run-{start:%Y%m%d-%H%M%S}.json",
            outcome.to_json(),
            as_bytes=False,
        )
        return outcome

    def upgrade(
        self,
        target: str = "head",
        *,
        dry_run: bool = False,
        timebox_seconds: int | None = None,
        validation_suites: Iterable[ValidationSuite] | None = None,
        create_backup: bool | None = None,
    ) -> MigrationResult:
        if dry_run:
            self.dry_run(target=target)
            return MigrationResult(
                succeeded=True,
                started_at=dt.datetime.now(dt.timezone.utc),
                finished_at=dt.datetime.now(dt.timezone.utc),
                details={"note": "Dry-run executed; no migration applied."},
            )

        if create_backup or (create_backup is None and self.settings.backup.enabled):
            self._create_backup()

        started_at = dt.datetime.now(dt.timezone.utc)
        outcome_details: dict[str, Any] = {}
        try:
            self._timeboxed(self._run_upgrade, timebox_seconds, target)
            finished_at = dt.datetime.now(dt.timezone.utc)
            validation_results: list[ValidationResult] = []
            for suite in validation_suites or self._load_validation_suites():
                validation_results.extend(suite.ensure_success(self.engine))
            outcome_details["validations"] = [
                {
                    "name": result.name,
                    "succeeded": result.succeeded,
                    "details": result.details,
                    "executed_at": result.executed_at.isoformat(),
                }
                for result in validation_results
            ]
            self._write_outcome(
                target=target,
                success=True,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            return MigrationResult(
                succeeded=True,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
        except TimeoutError as exc:
            finished_at = dt.datetime.now(dt.timezone.utc)
            outcome_details["error"] = f"Migration timed out after {timebox_seconds or self.settings.default_timebox_seconds} seconds"
            self._write_outcome(
                target=target,
                success=False,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            self._send_alert("Migration timeout", outcome_details)
            raise MigrationTimeoutError from exc
        except DataValidationError as exc:
            finished_at = dt.datetime.now(dt.timezone.utc)
            outcome_details["validation_error"] = str(exc)
            self._write_outcome(
                target=target,
                success=False,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            self._send_alert("Migration validation failure", outcome_details)
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            finished_at = dt.datetime.now(dt.timezone.utc)
            outcome_details["exception"] = repr(exc)
            self._write_outcome(
                target=target,
                success=False,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            self._send_alert("Migration failure", outcome_details)
            raise

    def downgrade(self, target: str) -> MigrationResult:
        started_at = dt.datetime.now(dt.timezone.utc)
        outcome_details: dict[str, Any] = {}
        try:
            self._timeboxed(self._run_downgrade, None, target)
            finished_at = dt.datetime.now(dt.timezone.utc)
            self._write_outcome(
                target=target,
                success=True,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            return MigrationResult(
                succeeded=True,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            finished_at = dt.datetime.now(dt.timezone.utc)
            outcome_details["exception"] = repr(exc)
            self._write_outcome(
                target=target,
                success=False,
                dry_run=False,
                started_at=started_at,
                finished_at=finished_at,
                details=outcome_details,
            )
            self._send_alert("Downgrade failure", outcome_details)
            raise

    def check_schema(self, expectations: SchemaExpectations | None = None) -> dict[str, Any]:
        inspector = sa.inspect(self.engine)
        expectations = expectations or self.settings.schema
        report: dict[str, Any] = {"tables": {}}
        for table_name, expected in expectations.tables.items():
            table_report: dict[str, Any] = {"indexes": {}, "triggers": {}}
            existing_indexes = {index["name"]: index for index in inspector.get_indexes(table_name)}
            for index in expected.indexes:
                match = existing_indexes.get(index.name)
                table_report["indexes"][index.name] = {
                    "exists": match is not None,
                    "columns": match.get("column_names") if match else None,
                    "unique": match.get("unique") if match else None,
                }
            table_report["triggers"] = self._check_triggers(table_name, expected)
            report["tables"][table_name] = table_report
        artifact = self._write_artifact(
            f"schema-check-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S}.json",
            json.dumps(report, indent=2, sort_keys=True),
            as_bytes=False,
        )
        report["artifact"] = str(artifact)
        return report

    def history(self) -> list[str]:
        script = ScriptDirectory.from_config(self._alembic_cfg)
        return [rev.revision for rev in script.walk_revisions()]

    def current(self) -> str | None:
        with self.engine.connect() as connection:
            self._alembic_cfg.attributes["connection"] = connection
            try:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    command.current(self._alembic_cfg)
                value = buffer.getvalue().strip()
                return value or None
            finally:
                self._alembic_cfg.attributes.pop("connection", None)

    def _run_upgrade(self, target: str) -> None:
        with self.engine.begin() as connection:
            self._apply_timeouts(connection)
            self._alembic_cfg.attributes["connection"] = connection
            try:
                command.upgrade(self._alembic_cfg, target)
            finally:
                self._alembic_cfg.attributes.pop("connection", None)

    def _run_downgrade(self, target: str) -> None:
        with self.engine.begin() as connection:
            self._apply_timeouts(connection)
            self._alembic_cfg.attributes["connection"] = connection
            try:
                command.downgrade(self._alembic_cfg, target)
            finally:
                self._alembic_cfg.attributes.pop("connection", None)

    def _apply_timeouts(self, connection: sa.Connection) -> None:
        dialect_name = connection.dialect.name
        if dialect_name == "postgresql":
            if self.settings.lock_timeout_seconds is not None:
                connection.execute(
                    sa.text("SET lock_timeout TO :timeout"),
                    {"timeout": f"{self.settings.lock_timeout_seconds * 1000}"},
                )
            if self.settings.statement_timeout_seconds is not None:
                connection.execute(
                    sa.text("SET statement_timeout TO :timeout"),
                    {"timeout": f"{self.settings.statement_timeout_seconds * 1000}"},
                )
        elif dialect_name == "sqlite":  # pragma: no cover - sqlite uses busy timeout
            timeout = self.settings.lock_timeout_seconds
            if timeout is not None:
                connection.execute(sa.text(f"PRAGMA busy_timeout = {timeout * 1000}"))

    def _timeboxed(self, func, timeout: int | None, *args, **kwargs) -> Any:
        timeout = timeout or self.settings.default_timebox_seconds
        if timeout is None:
            return func(*args, **kwargs)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            return future.result(timeout=timeout)

    def _write_outcome(
        self,
        *,
        target: str,
        success: bool,
        dry_run: bool,
        started_at: dt.datetime,
        finished_at: dt.datetime | None,
        details: Mapping[str, Any],
    ) -> Path:
        outcome = MigrationOutcome(
            target=target,
            success=success,
            dry_run=dry_run,
            started_at=started_at,
            finished_at=finished_at,
            details=details,
        )
        filename = f"migration-{target}-{started_at:%Y%m%d-%H%M%S}.json"
        return self._write_artifact(filename, outcome.to_json(), as_bytes=False)

    def _send_alert(self, message: str, details: Mapping[str, Any]) -> None:
        settings = self.settings.alerting
        if not settings.enabled or not settings.webhook_url:
            return
        payload = {
            "text": message,
            "channel": settings.channel,
            "details": details,
        }
        try:
            httpx.post(settings.webhook_url, json=payload, timeout=10).raise_for_status()
        except httpx.HTTPError:  # pragma: no cover - best effort
            pass

    def _write_artifact(self, filename: str, content: str, *, as_bytes: bool) -> Path:
        path = self._artifacts_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if as_bytes:
            path.write_bytes(content.encode("utf-8"))
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def _check_triggers(self, table_name: str, expectation: Any) -> Mapping[str, Mapping[str, Any]]:
        dialect_name = self.engine.dialect.name
        if dialect_name != "postgresql":
            return {
                trigger.name: {
                    "supported": False,
                    "exists": None,
                }
                for trigger in expectation.triggers
            }
        query = sa.text(
            """
            SELECT tgname AS name, pg_get_triggerdef(oid) AS definition
            FROM pg_trigger
            WHERE NOT tgisinternal AND tgrelid = :table::regclass
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query, {"table": table_name}).mappings().all()
        definitions = {row["name"]: row["definition"] for row in rows}
        report: dict[str, Mapping[str, Any]] = {}
        for trigger in expectation.triggers:
            definition = definitions.get(trigger.name)
            report[trigger.name] = {
                "exists": definition is not None,
                "matches_function": (trigger.function in (definition or ""))
                if trigger.function
                else None,
                "matches_event": (trigger.event in (definition or ""))
                if trigger.event
                else None,
            }
        return report

    def _create_backup(self) -> None:
        if not self.settings.backup.enabled and not self.settings.backup.directory:
            return
        url = self.settings.database_url
        if not url:
            raise RuntimeError("Database URL required for backups")
        if not url.startswith("postgresql"):
            raise RuntimeError("Backup currently supported only for PostgreSQL URLs")
        backup_dir = self.settings.backup.directory or Path("backups/migrations")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = backup_dir / f"backup-{timestamp}.sql"
        env = os.environ.copy()
        env.setdefault("PGCONNECT_TIMEOUT", "10")
        command_parts = [
            self.settings.backup.tool,
            url,
            "-f",
            str(filename),
        ]
        subprocess.run(command_parts, check=True, env=env)
        self._rotate_backups(backup_dir)

    def _rotate_backups(self, directory: Path) -> None:
        retain = self.settings.backup.retain_last
        if retain <= 0:
            return
        backups = sorted(directory.glob("backup-*.sql"))
        for obsolete in backups[:-retain]:
            obsolete.unlink(missing_ok=True)

    def _load_validation_suites(self) -> Iterable[ValidationSuite]:
        for path in self.settings.validation_files:
            yield ValidationSuite.load(path)


class MigrationTimeoutError(TimeoutError):
    """Raised when a migration exceeds the allotted execution window."""

