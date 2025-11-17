# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Execution risk controls with kill-switch governance and telemetry hooks.

This module houses the reference :class:`RiskManager` used by the live trading
runner (see ``docs/runbook_live_trading.md``) and the risk, signals, and
observability blueprint in ``docs/risk_ml_observability.md``. It enforces
position/notional limits, order-rate throttles, and a kill-switch escalation
mechanism aligned with the governance expectations formalised in
``docs/documentation_governance.md`` and ``docs/monitoring.md``.

TradePulse routes all order flow through this module to ensure regulatory and
internal guardrails are enforced before interacting with external venues. The
implementation codifies the governance controls described in
``docs/execution.md`` and the observability guarantees tracked in
``docs/quality_gates.md``.

**Scope of responsibilities**

* Enforce static and dynamic risk limits (:class:`RiskLimits`) across notional,
  position, and order-rate dimensions with deterministic violation handling.
* Persist kill-switch decisions and rate-limit breaches so runbooks in
  ``docs/runbook_kill_switch_failover.md`` can be executed with full context.
* Normalise instrument identifiers via ``core.data.catalog`` to maintain data
  lineage across research, execution, and reporting pipelines.

**Operational integrations**

The implementation depends on catalog normalisation utilities, execution audit
logging, and metrics collectors to ensure every decision is observable and
attributable—an explicit requirement in ``docs/quality_gates.md``. Database
connectivity honours the configuration schemas in ``core.config.cli_models`` and
``libs.db`` so deployments can select SQLite, Postgres, or in-memory stores
without modifying risk logic.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    TypeVar,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.config.cli_models import PostgresTLSConfig
from core.data.catalog import normalize_symbol
from core.utils.logging import get_logger
from core.utils.metrics import get_metrics_collector
from interfaces.execution import PortfolioRiskAnalyzer, RiskController
from libs.db import (
    DatabasePoolConfig,
    DatabaseRuntimeConfig,
    DatabaseSettings,
    KillSwitchStateRepository,
    RetryPolicy,
    SessionManager,
    create_engine_from_config,
)

from ..audit import ExecutionAuditLogger, get_execution_audit_logger


class RiskError(RuntimeError):
    """Base exception for risk-control violations."""


class DataQualityError(RiskError):
    """Raised when persisted state fails data quality gates."""


class LimitViolation(RiskError):
    """Raised when position or notional limits would be breached."""


class OrderRateExceeded(RiskError):
    """Raised when the order rate throttle blocks a submission."""


@dataclass(slots=True)
class RiskLimits:
    """Risk guardrails that must be enforced prior to execution.

    Attributes:
        max_notional: Absolute notional cap per instrument.
        max_position: Signed position cap.
        max_orders_per_interval: Order submissions allowed within ``interval_seconds``.
        interval_seconds: Rolling window length for the throttle.
        kill_switch_limit_multiplier: Severity multiplier that instantly trips the
            kill-switch when exceeded.
        kill_switch_violation_threshold: Consecutive limit breaches that trigger
            the kill-switch.
        kill_switch_rate_limit_threshold: Consecutive throttle breaches that
            trigger the kill-switch.
        max_relative_drawdown: Maximum fractional equity drawdown tolerated before
            the kill-switch engages. Values between 0 and 1 are treated as ratios,
            while values between 1 and 100 are interpreted as percentages.
    """

    max_notional: float = float("inf")
    max_position: float = float("inf")
    max_orders_per_interval: int = 60
    interval_seconds: float = 1.0
    kill_switch_limit_multiplier: float = 1.5
    kill_switch_violation_threshold: int = 3
    kill_switch_rate_limit_threshold: int = 3
    max_relative_drawdown: float | None = None

    def __post_init__(self) -> None:
        if self.max_orders_per_interval < 0:
            self.max_orders_per_interval = 0
        if self.interval_seconds < 0:
            self.interval_seconds = 0.0
        if self.kill_switch_limit_multiplier < 1.0:
            self.kill_switch_limit_multiplier = 1.0
        if self.kill_switch_violation_threshold < 1:
            self.kill_switch_violation_threshold = 1
        if self.kill_switch_rate_limit_threshold < 1:
            self.kill_switch_rate_limit_threshold = 1
        if self.max_relative_drawdown is not None:
            numeric = float(self.max_relative_drawdown)
            if numeric <= 0:
                raise ValueError("max_relative_drawdown must be positive")
            if numeric >= 1:
                if numeric <= 100:
                    numeric /= 100.0
                else:
                    raise ValueError("max_relative_drawdown must be <= 100")
            self.max_relative_drawdown = numeric


class KillSwitchStateStore(Protocol):
    """Persistence backend for kill-switch state."""

    def load(self) -> tuple[bool, str] | None:
        """Return the last persisted state, if any."""

    def save(self, engaged: bool, reason: str) -> None:
        """Persist the supplied state atomically."""


class RiskStateStore(Protocol):
    """Persistence backend for :class:`RiskManager` exposures."""

    def load(self) -> tuple[Mapping[str, float], Mapping[str, float]] | None:
        """Return persisted positions and notionals, if available."""

    def save(
        self,
        positions: Mapping[str, float],
        notionals: Mapping[str, float],
    ) -> None:
        """Persist the supplied exposure snapshot atomically."""


T = TypeVar("T")


class KillSwitchStateRecord(BaseModel):
    """Validated kill-switch payload loaded from persistence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    engaged: bool
    reason: str = Field(default="", max_length=2048)
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _coerce_payload(cls, data: object) -> dict[str, object]:
        if isinstance(data, dict):
            payload = dict(data)
        elif isinstance(data, tuple):
            if len(data) != 3:
                raise ValueError("expected 3-tuple payload")
            payload = {"engaged": data[0], "reason": data[1], "updated_at": data[2]}
        else:
            raise TypeError("unsupported payload shape")

        payload["engaged"] = bool(payload.get("engaged", False))
        payload["reason"] = payload.get("reason") or ""

        raw_ts = payload.get("updated_at")
        if raw_ts is None:
            raise ValueError("updated_at is required")
        if isinstance(raw_ts, datetime):
            timestamp = raw_ts
        else:
            if not isinstance(raw_ts, str):
                raise TypeError("updated_at must be str or datetime")
            normalised = raw_ts.strip().replace(" ", "T")
            if normalised.endswith("Z") or normalised.endswith("z"):
                normalised = f"{normalised[:-1]}+00:00"
            try:
                timestamp = datetime.fromisoformat(normalised)
            except ValueError as exc:
                raise ValueError("updated_at is not ISO 8601 compliant") from exc

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        payload["updated_at"] = timestamp
        return payload

    @model_validator(mode="after")
    def _validate_reason(self) -> "KillSwitchStateRecord":
        if self.engaged and not self.reason:
            raise ValueError("reason must be provided when kill-switch is engaged")
        if any(ord(ch) < 32 and ch not in {"\t", "\n"} for ch in self.reason):
            raise ValueError("reason contains control characters")
        return self


class RiskStateRecord(BaseModel):
    """Validated exposure snapshot used for persistence."""

    model_config = ConfigDict(extra="forbid")

    positions: Mapping[str, float] = Field(default_factory=dict)
    last_notional: Mapping[str, float] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_payload(cls, data: object) -> dict[str, Mapping[str, float]]:
        if data is None:
            return {"positions": {}, "last_notional": {}}
        if isinstance(data, RiskStateRecord):
            return data.model_dump()
        if isinstance(data, Mapping):
            payload: dict[str, Mapping[str, float]] = {}
            for key in ("positions", "last_notional"):
                raw = data.get(key, {})
                if raw is None:
                    payload[key] = {}
                    continue
                if not isinstance(raw, Mapping):
                    raise TypeError(f"{key} section must be a mapping")
                payload[key] = dict(raw)
            return payload
        raise TypeError("risk state payload must be a mapping")

    @model_validator(mode="after")
    def _normalise(self) -> "RiskStateRecord":
        def _sanitise(source: Mapping[str, float]) -> dict[str, float]:
            normalised: dict[str, float] = {}
            for raw_symbol, raw_value in source.items():
                if raw_symbol is None:
                    continue
                symbol = str(raw_symbol).strip()
                if not symbol:
                    continue
                try:
                    numeric = float(raw_value)
                except (TypeError, ValueError):
                    continue
                normalised[symbol] = numeric
            return normalised

        object.__setattr__(self, "positions", _sanitise(self.positions))
        object.__setattr__(self, "last_notional", _sanitise(self.last_notional))
        return self


class BaseKillSwitchStateStore(KillSwitchStateStore, ABC):
    """Shared validation and quarantine controls for kill-switch persistence."""

    def __init__(
        self,
        *,
        max_staleness: float = 300.0,
        max_future_drift: float = 5.0,
        max_reason_length: int = 512,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_staleness <= 0:
            raise ValueError("max_staleness must be positive")
        if max_future_drift < 0:
            raise ValueError("max_future_drift must be non-negative")
        if max_reason_length <= 0:
            raise ValueError("max_reason_length must be positive")

        self._max_staleness = timedelta(seconds=float(max_staleness))
        self._max_future_drift = timedelta(seconds=float(max_future_drift))
        self._max_reason_length = int(max_reason_length)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._quarantined = False
        self._quarantine_reason: str | None = None
        self._logger = get_logger(__name__)

    def load(self) -> tuple[bool, str] | None:
        self._check_not_quarantined()
        row = self._load_row()
        if row is None:
            return None
        record = self._validate_record(row)
        self._enforce_range_checks(record)
        self._enforce_temporal_contract(record)
        return record.engaged, record.reason

    def save(self, engaged: bool, reason: str) -> None:
        payload_reason = reason or ""
        with self._lock:
            self._check_not_quarantined()
            self._enforce_outgoing_contracts(bool(engaged), payload_reason)
            self._save_payload(bool(engaged), payload_reason)

    def is_quarantined(self) -> bool:
        return self._quarantined

    def quarantine_reason(self) -> str | None:
        return self._quarantine_reason

    def clear_quarantine(self) -> None:
        with self._lock:
            self._quarantined = False
            self._quarantine_reason = None

    @abstractmethod
    def _load_row(self) -> tuple[object, ...] | None:
        """Return the raw persistence payload or ``None`` when empty."""

    @abstractmethod
    def _save_payload(self, engaged: bool, reason: str) -> None:
        """Persist the provided payload atomically."""

    def _check_not_quarantined(self) -> None:
        if self._quarantined:
            raise DataQualityError(
                self._quarantine_reason
                or "kill-switch store quarantined due to invalid state"
            )

    def _quarantine(self, reason: str, *, exc: Exception | None = None) -> None:
        with self._lock:
            self._quarantined = True
            self._quarantine_reason = reason
        error_payload = {
            "reason": reason,
            "error_type": type(exc).__name__ if exc else None,
            "error_message": str(exc) if exc else None,
        }
        self._logger.error("Kill-switch store quarantined", **error_payload)

    def _validate_record(self, row: tuple[object, ...]) -> KillSwitchStateRecord:
        try:
            return KillSwitchStateRecord.model_validate(row)
        except ValidationError as exc:
            message = "Persisted kill-switch state failed schema validation"
            self._quarantine(message, exc=exc)
            raise DataQualityError(message) from exc

    def _enforce_range_checks(self, record: KillSwitchStateRecord) -> None:
        if len(record.reason) > self._max_reason_length:
            message = (
                "Persisted kill-switch reason exceeds allowed length"
                f" ({len(record.reason)} > {self._max_reason_length})"
            )
            self._quarantine(message)
            raise DataQualityError(message)

    def _enforce_temporal_contract(self, record: KillSwitchStateRecord) -> None:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        updated_at = record.updated_at
        if now - updated_at > self._max_staleness:
            message = (
                "Persisted kill-switch state is stale"
                f" ({(now - updated_at).total_seconds():.3f}s > {self._max_staleness.total_seconds():.3f}s)"
            )
            self._quarantine(message)
            raise DataQualityError(message)
        if updated_at - now > self._max_future_drift:
            message = (
                "Persisted kill-switch timestamp is in the future"
                f" ({(updated_at - now).total_seconds():.3f}s > {self._max_future_drift.total_seconds():.3f}s)"
            )
            self._quarantine(message)
            raise DataQualityError(message)

    def _enforce_outgoing_contracts(self, engaged: bool, reason: str) -> None:
        if engaged and not reason:
            raise DataQualityError(
                "reason must be supplied when engaging the kill-switch"
            )
        if len(reason) > self._max_reason_length:
            raise DataQualityError(
                f"reason exceeds allowed length {len(reason)} > {self._max_reason_length}"
            )
        if any(ord(ch) < 32 and ch not in {"\t", "\n"} for ch in reason):
            raise DataQualityError("reason contains control characters")


class SQLiteKillSwitchStateStore(BaseKillSwitchStateStore):
    """SQLite-backed store used to persist kill-switch state across restarts."""

    _UPSERT_STATEMENT = """
        INSERT INTO kill_switch_state (id, engaged, reason, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            engaged = excluded.engaged,
            reason = excluded.reason,
            updated_at = CURRENT_TIMESTAMP
    """

    def __init__(
        self,
        path: str | Path,
        *,
        timeout: float = 10.0,
        max_retries: int = 5,
        retry_interval: float = 0.05,
        backoff_multiplier: float = 2.0,
        max_staleness: float = 300.0,
        max_future_drift: float = 5.0,
        max_reason_length: int = 512,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_interval <= 0:
            raise ValueError("retry_interval must be positive")
        if backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")

        self._timeout = float(timeout)
        self._max_retries = int(max_retries)
        self._retry_interval = float(retry_interval)
        self._backoff_multiplier = float(backoff_multiplier)

        super().__init__(
            max_staleness=max_staleness,
            max_future_drift=max_future_drift,
            max_reason_length=max_reason_length,
            clock=clock,
        )
        self._initialise()

    def _initialise(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path, timeout=self._timeout) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS kill_switch_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    engaged INTEGER NOT NULL CHECK (engaged IN (0, 1)),
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _with_retry(
        self, operation: Callable[[sqlite3.Connection], T], *, write: bool = False
    ) -> T:
        delay = self._retry_interval
        attempts_remaining = self._max_retries
        while True:
            try:
                with sqlite3.connect(self._path, timeout=self._timeout) as connection:
                    if write:
                        connection.execute("PRAGMA journal_mode=WAL")
                    return operation(connection)
            except sqlite3.OperationalError as exc:
                if not self._should_retry(exc) or attempts_remaining <= 0:
                    raise
                time.sleep(delay)
                attempts_remaining -= 1
                delay = min(delay * self._backoff_multiplier, self._timeout)

    @staticmethod
    def _should_retry(error: sqlite3.OperationalError) -> bool:
        message = str(error).lower()
        return "locked" in message or "busy" in message

    def _load_row(self) -> tuple[object, ...] | None:

        def _load(connection: sqlite3.Connection) -> tuple[object, ...] | None:
            cursor = connection.execute(
                "SELECT engaged, reason, updated_at FROM kill_switch_state WHERE id = 1"
            )
            return cursor.fetchone()

        return self._with_retry(_load)

    def _save_payload(self, engaged: bool, reason: str) -> None:

        def _save(connection: sqlite3.Connection) -> None:
            connection.execute(
                self._UPSERT_STATEMENT,
                (1, int(bool(engaged)), reason),
            )

        self._with_retry(_save, write=True)


class KillSwitchRepository(Protocol):
    """Minimal interface implemented by kill-switch persistence adapters."""

    def load(self) -> object | None:
        """Return the persisted kill-switch payload, if available."""

    def upsert(self, *, engaged: bool, reason: str) -> object:
        """Persist the supplied state atomically and return the stored record."""


class PostgresKillSwitchStateStore(BaseKillSwitchStateStore):
    """PostgreSQL-backed kill-switch store using pooled SQLAlchemy sessions."""

    def __init__(
        self,
        dsn: str,
        *,
        tls: PostgresTLSConfig | None = None,
        read_replicas: Sequence[str] | None = None,
        pool_min_size: int = 1,
        pool_max_size: int = 4,
        pool_max_overflow: int = 4,
        acquire_timeout: float | None = 2.0,
        pool_recycle_seconds: float = 1_800.0,
        connect_timeout: float = 5.0,
        statement_timeout_ms: int = 5_000,
        retry_policy: RetryPolicy | None = None,
        max_retries: int = 3,
        retry_interval: float = 0.1,
        backoff_multiplier: float = 2.0,
        max_staleness: float = 300.0,
        max_future_drift: float = 5.0,
        max_reason_length: int = 512,
        clock: Callable[[], datetime] | None = None,
        session_manager: SessionManager | None = None,
        repository: KillSwitchRepository | None = None,
        ensure_schema: bool = True,
        application_name: str = "tradepulse-kill-switch",
        echo_statements: bool = False,
    ) -> None:
        if pool_min_size < 0:
            raise ValueError("pool_min_size must be non-negative")
        if pool_max_size <= 0:
            raise ValueError("pool_max_size must be positive")
        if pool_min_size > pool_max_size:
            raise ValueError("pool_min_size cannot exceed pool_max_size")
        if pool_max_overflow < 0:
            raise ValueError("pool_max_overflow must be non-negative")
        if acquire_timeout is not None and acquire_timeout < 0:
            raise ValueError("acquire_timeout must be non-negative")
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        if retry_interval < 0:
            raise ValueError("retry_interval must be non-negative")
        if backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")

        super().__init__(
            max_staleness=max_staleness,
            max_future_drift=max_future_drift,
            max_reason_length=max_reason_length,
            clock=clock,
        )

        effective_retry = retry_policy
        if effective_retry is None:
            total_attempts = max(int(max_retries), 0) + 1
            initial_backoff = retry_interval if retry_interval > 0 else 0.05
            computed_max = max(
                initial_backoff,
                retry_interval * (backoff_multiplier ** max(int(max_retries), 0)),
            )
            effective_retry = RetryPolicy(
                attempts=total_attempts,
                initial_backoff=initial_backoff,
                max_backoff=computed_max,
                max_jitter=min(initial_backoff, 0.5),
            )

        self._retry_policy = effective_retry
        self._session_manager = session_manager
        self._owns_session_manager = False

        if repository is None:
            if session_manager is None:
                if tls is None:
                    raise ValueError(
                        "tls must be provided when using the default PostgreSQL connection factory"
                    )
                pool_config = DatabasePoolConfig(
                    size=pool_max_size,
                    max_overflow=pool_max_overflow,
                    timeout=acquire_timeout,
                    recycle=pool_recycle_seconds,
                )
                runtime_config = DatabaseRuntimeConfig(
                    application_name=application_name,
                    connect_timeout_seconds=connect_timeout,
                    statement_timeout_ms=statement_timeout_ms,
                )
                settings = DatabaseSettings(
                    writer_dsn=dsn,
                    reader_dsns=tuple(read_replicas or ()),
                    tls=tls,
                    pool=pool_config,
                    runtime=runtime_config,
                    echo_statements=echo_statements,
                )
                writer_engine = create_engine_from_config(
                    settings.writer_dsn,
                    tls=settings.tls,
                    pool=settings.pool,
                    runtime=settings.runtime,
                    echo=settings.echo_statements,
                )
                reader_engines = [
                    create_engine_from_config(
                        replica,
                        tls=settings.tls,
                        pool=settings.pool,
                        runtime=settings.runtime,
                        echo=settings.echo_statements,
                    )
                    for replica in settings.reader_dsns
                ]
                session_manager = SessionManager(writer_engine, reader_engines)
                session_manager.warmup(
                    writer_connections=pool_min_size,
                    reader_connections=pool_min_size if reader_engines else 0,
                )
                self._session_manager = session_manager
                self._owns_session_manager = True
            if self._session_manager is None:
                raise RuntimeError(
                    "session_manager must be provided when repository is None"
                )
            repository = KillSwitchStateRepository(
                self._session_manager,
                retry_policy=effective_retry,
                logger=get_logger(__name__),
            )

        self._repository: KillSwitchRepository = repository

        if ensure_schema:
            ensure = getattr(self._repository, "ensure_schema", None)
            if callable(ensure):
                ensure()

    def close(self) -> None:
        if self._owns_session_manager and self._session_manager is not None:
            self._session_manager.close()
        closer = getattr(self._repository, "close", None)
        if callable(closer):
            closer()

    def _load_row(self) -> tuple[object, ...] | None:
        payload = self._execute_with_retry(self._repository.load)
        if payload is None:
            return None
        if isinstance(payload, tuple):
            return payload
        if (
            hasattr(payload, "engaged")
            and hasattr(payload, "reason")
            and hasattr(payload, "updated_at")
        ):
            return (
                bool(getattr(payload, "engaged")),
                str(getattr(payload, "reason")),
                getattr(payload, "updated_at"),
            )
        raise DataQualityError("Unsupported payload type returned by repository")

    def _save_payload(self, engaged: bool, reason: str) -> None:
        self._execute_with_retry(
            lambda: self._repository.upsert(engaged=bool(engaged), reason=reason)
        )

    def _execute_with_retry(self, operation: Callable[[], T]) -> T:
        base_logger = getattr(self._logger, "logger", self._logger)
        retrying = self._retry_policy.build(logger=base_logger)
        for attempt in retrying:
            with attempt:
                return operation()
        raise RuntimeError("Database retry loop exited unexpectedly")


class JsonRiskStateStore(RiskStateStore):
    """Persist :class:`RiskManager` exposure snapshots to JSON."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[Mapping[str, float], Mapping[str, float]] | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text())
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive parsing
            raise DataQualityError("Persisted risk state is not valid JSON") from exc
        record = RiskStateRecord.model_validate(payload)
        return record.positions, record.last_notional

    def save(
        self,
        positions: Mapping[str, float],
        notionals: Mapping[str, float],
    ) -> None:
        record = RiskStateRecord(
            positions=dict(positions), last_notional=dict(notionals)
        )
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "positions": record.positions,
                    "last_notional": record.last_notional,
                },
                indent=2,
                sort_keys=True,
            )
        )
        tmp_path.replace(self._path)


class KillSwitch:
    """Global kill-switch toggled on critical failures with optional persistence.

    The kill-switch mirrors the operational blueprint in
    ``docs/admin_remote_control.md`` and is surfaced via CLI and observability
    tooling for rapid operator response. When supplied with a
    :class:`KillSwitchStateStore` it reloads the persisted state during
    initialisation to preserve operator intent across restarts.
    """

    def __init__(self, store: KillSwitchStateStore | None = None) -> None:
        self._store = store
        self._triggered = False
        self._reason = ""
        if self._store is not None:
            self._refresh_from_store()

    def _refresh_from_store(self) -> None:
        if self._store is None:
            return

        try:
            persisted = self._store.load()
        except DataQualityError as exc:
            self._triggered = True
            self._reason = str(exc)
            raise
        if persisted is None:
            self._triggered = False
            self._reason = ""
            return

        engaged, reason = persisted
        self._triggered = bool(engaged)
        self._reason = reason or ""

    def trigger(self, reason: str) -> None:
        """Engage the kill-switch with an explanatory ``reason``."""

        self._triggered = True
        self._reason = reason
        if self._store is not None:
            self._store.save(True, reason)

    def reset(self) -> None:
        """Clear the kill-switch state."""

        self._triggered = False
        self._reason = ""
        if self._store is not None:
            self._store.save(False, "")

    @property
    def reason(self) -> str:
        """Return the human-readable explanation for the last trigger."""

        if self._store is not None:
            self._refresh_from_store()
        return self._reason

    def is_triggered(self) -> bool:
        """Indicate whether the kill-switch is currently engaged."""

        if self._store is not None:
            self._refresh_from_store()
        return self._triggered

    def guard(self) -> None:
        """Raise :class:`RiskError` if the kill-switch is active."""

        if self._store is not None:
            self._refresh_from_store()
        if self._triggered:
            raise RiskError(
                f"Kill-switch engaged: {self._reason or 'unspecified reason'}"
            )


class RiskManager(RiskController):
    """Apply notional/position caps and order throttling.

    The manager coordinates with :mod:`execution.audit`, records metrics for the
    observability pipeline in ``docs/monitoring.md`` and enforces the governance
    rules codified in ``docs/documentation_governance.md`` before orders reach
    the venue adapters.
    """

    def __init__(
        self,
        limits: RiskLimits,
        *,
        time_source: Callable[[], float] | None = None,
        audit_logger: ExecutionAuditLogger | None = None,
        kill_switch_store: KillSwitchStateStore | None = None,
        risk_state_store: RiskStateStore | None = None,
    ) -> None:
        self.limits = limits
        self._kill_switch = KillSwitch(store=kill_switch_store)
        self._time = time_source or time.time
        self._positions: MutableMapping[str, float] = {}
        self._last_notional: MutableMapping[str, float] = {}
        self._risk_state_store = risk_state_store
        self._submissions: deque[float] = deque()
        self._logger = get_logger(__name__)
        self._metrics = get_metrics_collector()
        self._audit = audit_logger or get_execution_audit_logger()
        self._limit_violation_streak = 0
        self._throttle_violation_streak = 0
        self._equity = 0.0
        self._peak_equity = 0.0
        self._current_drawdown = 0.0
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._drawdown_halt_notified = False
        self._latest_neural_directive: dict[str, float | str] | None = None
        self._restore_risk_state()

    def update_limits(self, **updates: object) -> RiskLimits:
        """Apply supported updates to :class:`RiskLimits` and return the result."""

        allowed_fields = {
            "max_notional",
            "max_position",
            "kill_switch_violation_threshold",
            "kill_switch_limit_multiplier",
            "kill_switch_rate_limit_threshold",
            "max_orders_per_interval",
        }
        invalid = set(updates) - allowed_fields
        if invalid:
            joined = ", ".join(sorted(invalid))
            raise ValueError(f"Unsupported risk limit fields: {joined}")
        sanitized = {key: value for key, value in updates.items() if value is not None}
        if not sanitized:
            return self.limits
        new_limits = replace(self.limits, **sanitized)
        self._logger.info(  # noqa: TRY400 - structured logging
            "Risk limits updated",
            extra={
                "event": "risk.limits_updated",
                "changes": sanitized,
            },
        )
        self.limits = new_limits
        return self.limits

    def apply_neural_directive(
        self,
        *,
        action: str,
        alloc_main: float,
        alloc_alt: float,
        alloc_scale: float,
    ) -> dict[str, float | str]:
        """Persist the latest neural-controller directive for auditability."""

        directive = {
            "action": action,
            "alloc_main": float(max(0.0, min(1.0, alloc_main))),
            "alloc_alt": float(max(0.0, min(1.0, alloc_alt))),
            "alloc_scale": float(max(0.0, min(1.0, alloc_scale))),
        }
        self._latest_neural_directive = directive
        self._logger.info(  # noqa: TRY400 - structured logging
            "Neural directive applied",
            extra={"event": "risk.neural_directive", "payload": directive},
        )
        return directive

    @property
    def latest_neural_directive(self) -> dict[str, float | str] | None:
        """Return the most recent neural directive if one has been applied."""

        return self._latest_neural_directive

    def _canonical_symbol(self, symbol: str) -> str:
        return normalize_symbol(symbol)

    def _restore_risk_state(self) -> None:
        if self._risk_state_store is None:
            return
        try:
            snapshot = self._risk_state_store.load()
        except DataQualityError:
            self._logger.exception("Persisted risk state failed validation")
            raise
        if not snapshot:
            return
        positions, notionals = snapshot
        for symbol, position in positions.items():
            try:
                canonical = self._canonical_symbol(symbol)
                self._positions[canonical] = float(position)
            except Exception:  # pragma: no cover - defensive normalisation path
                self._logger.warning(
                    "Failed to restore position entry",  # noqa: TRY400 - structured logging
                    extra={
                        "event": "risk.restore_position_failed",
                        "symbol": symbol,
                    },
                )
        for symbol, notional in notionals.items():
            try:
                canonical = self._canonical_symbol(symbol)
                self._last_notional[canonical] = abs(float(notional))
            except Exception:  # pragma: no cover - defensive normalisation path
                self._logger.warning(
                    "Failed to restore notional entry",  # noqa: TRY400
                    extra={
                        "event": "risk.restore_notional_failed",
                        "symbol": symbol,
                    },
                )

    def _persist_risk_state(self) -> None:
        if self._risk_state_store is None:
            return
        try:
            self._risk_state_store.save(self._positions, self._last_notional)
        except Exception as exc:  # pragma: no cover - persistence failures rare
            self._logger.warning(
                "Failed to persist risk exposure snapshot",  # noqa: TRY400
                extra={"event": "risk.persist_failed", "error": str(exc)},
            )

    @property
    def equity(self) -> float:
        """Return the most recent portfolio equity observation."""

        return self._equity

    @property
    def peak_equity(self) -> float:
        """Return the recorded equity high-water mark."""

        return self._peak_equity

    @property
    def current_drawdown(self) -> float:
        """Return the current fractional drawdown."""

        return self._current_drawdown

    @property
    def realized_pnl(self) -> float:
        """Return the last recorded realised PnL value."""

        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        """Return the last recorded unrealised PnL value."""

        return self._unrealized_pnl

    @property
    def paper_trading_active(self) -> bool:
        """Indicate whether real trading should remain halted."""

        return self._kill_switch.is_triggered()

    def update_portfolio_equity(
        self,
        equity: float,
        *,
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
    ) -> None:
        """Record portfolio equity/PnL and enforce drawdown guardrails."""

        equity_value = float(equity)
        if not math.isfinite(equity_value):
            raise ValueError("equity must be finite")
        if equity_value < 0:
            raise ValueError("equity must be non-negative")

        self._equity = equity_value
        if equity_value > self._peak_equity:
            self._peak_equity = equity_value

        if realized_pnl is not None:
            realized_value = float(realized_pnl)
            if not math.isfinite(realized_value):
                raise ValueError("realized_pnl must be finite")
            self._realized_pnl = realized_value

        if unrealized_pnl is not None:
            unrealized_value = float(unrealized_pnl)
            if not math.isfinite(unrealized_value):
                raise ValueError("unrealized_pnl must be finite")
            self._unrealized_pnl = unrealized_value

        if self._peak_equity > 0:
            drawdown = max(0.0, (self._peak_equity - self._equity) / self._peak_equity)
        else:
            drawdown = 0.0

        self._current_drawdown = drawdown
        self._metrics.record_drawdown(drawdown)

        limit = self.limits.max_relative_drawdown
        if limit is None:
            self._drawdown_halt_notified = False
            return

        if drawdown >= limit:
            reason = (
                "Equity drawdown "
                f"{drawdown:.2%} breached limit {limit:.2%} "
                f"(peak={self._peak_equity:.2f}, equity={self._equity:.2f}) "
                "– switching to paper trading"
            )
            if not self._drawdown_halt_notified:
                self._audit.emit(
                    {
                        "event": "portfolio_drawdown_breach",
                        "equity": self._equity,
                        "peak_equity": self._peak_equity,
                        "drawdown": drawdown,
                        "drawdown_limit": limit,
                        "realized_pnl": self._realized_pnl,
                        "unrealized_pnl": self._unrealized_pnl,
                        "reason": reason,
                    }
                )
                self._drawdown_halt_notified = True
            self._trigger_kill_switch(reason, violation_type="drawdown_limit")
        else:
            self._drawdown_halt_notified = False

    def hydrate_positions(
        self,
        mapping: Mapping[str, tuple[float, float]],
        *,
        replace: bool = False,
    ) -> None:
        """Hydrate internal exposure tracking from external sources."""

        if replace:
            self._positions.clear()
            self._last_notional.clear()

        for symbol, payload in mapping.items():
            try:
                position, notional = payload
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "hydrate_positions expects mapping values to be 2-tuples"
                ) from exc

            canonical = self._canonical_symbol(symbol)
            try:
                position_value = float(position)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid position value for {symbol!r}") from exc
            try:
                notional_value = abs(float(notional))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid notional value for {symbol!r}") from exc

            if abs(position_value) <= 1e-12:
                self._positions.pop(canonical, None)
            else:
                self._positions[canonical] = position_value

            if notional_value <= 1e-12:
                self._last_notional.pop(canonical, None)
            else:
                self._last_notional[canonical] = notional_value

        self._persist_risk_state()

    def _check_rate_limit(self, symbol: str, now: float) -> None:
        if self.limits.max_orders_per_interval <= 0:
            return
        window = max(self.limits.interval_seconds, 0.0)
        while self._submissions and now - self._submissions[0] > window:
            self._submissions.popleft()
        if len(self._submissions) >= self.limits.max_orders_per_interval:
            self._throttle_violation_streak += 1
            reason = f"Order throttle exceeded: {len(self._submissions)} submissions in {window}s"
            if (
                self._throttle_violation_streak
                >= self.limits.kill_switch_rate_limit_threshold
            ):
                self._trigger_kill_switch(
                    reason,
                    symbol=symbol,
                    violation_type="rate_limit",
                )
            raise OrderRateExceeded(reason)
        self._throttle_violation_streak = 0

    def _validate_inputs(self, qty: float, price: float) -> None:
        if qty < 0:
            raise ValueError("quantity must be non-negative")
        if price <= 0:
            raise ValueError("price must be positive")

    def _record_risk_audit(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str,
        reason: str | None = None,
        violation_type: str | None = None,
    ) -> None:
        payload = {
            "event": "risk_validation",
            "status": status,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "reason": reason,
            "violation_type": violation_type,
            "kill_switch_engaged": self._kill_switch.is_triggered(),
            "consecutive_limit_violations": self._limit_violation_streak,
            "consecutive_rate_limit_violations": self._throttle_violation_streak,
        }
        self._audit.emit(payload)

    def _trigger_kill_switch(
        self,
        reason: str,
        *,
        symbol: str | None = None,
        violation_type: str | None = None,
    ) -> None:
        if self._kill_switch.is_triggered():
            return
        self._kill_switch.trigger(reason)
        self._logger.critical(
            "Kill switch triggered",
            reason=reason,
            symbol=symbol,
            violation_type=violation_type,
            consecutive_limit_violations=self._limit_violation_streak,
            consecutive_rate_limit_violations=self._throttle_violation_streak,
        )
        self._metrics.record_kill_switch_trigger(reason)
        self._audit.emit(
            {
                "event": "kill_switch_triggered",
                "reason": reason,
                "symbol": symbol,
                "violation_type": violation_type,
                "consecutive_limit_violations": self._limit_violation_streak,
                "consecutive_rate_limit_violations": self._throttle_violation_streak,
            }
        )

    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        """Apply risk checks before admitting an order to the execution stack.

        Args:
            symbol: External instrument identifier; normalised via
                :func:`core.data.catalog.normalize_symbol`.
            side: Case-insensitive trade direction (``"buy"`` or ``"sell"``).
            qty: Order quantity expressed in base units. Must be non-negative.
            price: Reference price used for notional calculations. Must be
                strictly positive.

        Raises:
            ValueError: If ``qty`` or ``price`` fall outside allowable ranges.
            RiskError: When the kill-switch is already engaged.
            OrderRateExceeded: If the rate limiter blocks the submission.
            LimitViolation: When position or notional caps would be breached.

        Examples:
            >>> limits = RiskLimits(max_notional=10_000, max_position=5)
            >>> manager = RiskManager(limits)
            >>> manager.validate_order("BTC-USD", "buy", 1, 25_000.0)
            Traceback (most recent call last):
            ...
            LimitViolation: Notional cap exceeded for BTC-USD: 25000.0 > 10000.0

        Notes:
            - Successful validation appends the submission timestamp for rate-limit
              accounting and emits telemetry via :mod:`execution.audit`.
            - Consecutive limit or throttle violations trigger the kill-switch when
              thresholds in :class:`RiskLimits` are met, matching the operational
              response plan in ``docs/admin_remote_control.md``.
        """

        self._validate_inputs(qty, price)
        canonical_symbol = self._canonical_symbol(symbol)
        try:
            self._kill_switch.guard()
        except RiskError as exc:
            self._metrics.record_risk_validation(
                canonical_symbol, "kill_switch_blocked"
            )
            self._record_risk_audit(
                symbol=canonical_symbol,
                side=side.lower(),
                quantity=float(qty),
                price=float(price),
                status="blocked",
                reason=str(exc),
                violation_type="kill_switch",
            )
            raise
        now = self._time()
        try:
            self._check_rate_limit(canonical_symbol, now)
        except OrderRateExceeded as exc:
            reason = str(exc)
            self._metrics.record_risk_validation(canonical_symbol, "rate_limited")
            self._record_risk_audit(
                symbol=canonical_symbol,
                side=side.lower(),
                quantity=float(qty),
                price=float(price),
                status="rejected",
                reason=reason,
                violation_type="rate_limit",
            )
            raise

        side_sign = 1.0 if side.lower() == "buy" else -1.0
        current_position = float(self._positions.get(canonical_symbol, 0.0))
        new_position = current_position + side_sign * qty

        if abs(new_position) > self.limits.max_position:
            reason = (
                f"Position cap exceeded for {canonical_symbol}: "
                f"{new_position} > {self.limits.max_position}"
            )
            self._limit_violation_streak += 1
            severe = abs(new_position) > (
                self.limits.max_position * self.limits.kill_switch_limit_multiplier
            )
            if severe or (
                self._limit_violation_streak
                >= self.limits.kill_switch_violation_threshold
            ):
                self._trigger_kill_switch(
                    reason,
                    symbol=canonical_symbol,
                    violation_type="position_limit",
                )
            self._metrics.record_risk_validation(canonical_symbol, "position_limit")
            self._record_risk_audit(
                symbol=canonical_symbol,
                side=side.lower(),
                quantity=float(qty),
                price=float(price),
                status="rejected",
                reason=reason,
                violation_type="position_limit",
            )
            raise LimitViolation(reason)

        projected_notional = abs(new_position * price)
        if projected_notional > self.limits.max_notional:
            reason = (
                f"Notional cap exceeded for {canonical_symbol}: "
                f"{projected_notional} > {self.limits.max_notional}"
            )
            self._limit_violation_streak += 1
            severe = projected_notional > (
                self.limits.max_notional * self.limits.kill_switch_limit_multiplier
            )
            if severe or (
                self._limit_violation_streak
                >= self.limits.kill_switch_violation_threshold
            ):
                self._trigger_kill_switch(
                    reason,
                    symbol=canonical_symbol,
                    violation_type="notional_limit",
                )
            self._metrics.record_risk_validation(canonical_symbol, "notional_limit")
            self._record_risk_audit(
                symbol=canonical_symbol,
                side=side.lower(),
                quantity=float(qty),
                price=float(price),
                status="rejected",
                reason=reason,
                violation_type="notional_limit",
            )
            raise LimitViolation(reason)

        if self.limits.max_orders_per_interval > 0:
            self._submissions.append(now)
        else:
            self._submissions.clear()
        self._limit_violation_streak = 0
        self._metrics.record_risk_validation(canonical_symbol, "passed")
        self._record_risk_audit(
            symbol=canonical_symbol,
            side=side.lower(),
            quantity=float(qty),
            price=float(price),
            status="passed",
            reason=None,
            violation_type=None,
        )

    @property
    def kill_switch(self) -> KillSwitch:
        """Expose the kill-switch handle."""

        return self._kill_switch

    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        """Update exposure after a confirmed fill.

        Args:
            symbol: External instrument identifier; normalised via
                :func:`core.data.catalog.normalize_symbol`.
            side: Executed direction (``"buy"`` or ``"sell"``).
            qty: Fill quantity in base units.
            price: Fill price used for notional tracking.

        Notes:
            Exposure updates feed portfolio analytics described in
            ``docs/risk_ml_observability.md``.
        """

        self._validate_inputs(qty, price)
        canonical_symbol = self._canonical_symbol(symbol)
        side_sign = 1.0 if side.lower() == "buy" else -1.0
        position = float(self._positions.get(canonical_symbol, 0.0)) + side_sign * qty
        self._positions[canonical_symbol] = position
        self._last_notional[canonical_symbol] = abs(position * price)
        self._persist_risk_state()

    def current_position(self, symbol: str) -> float:
        """Return the signed position for ``symbol``."""

        canonical_symbol = self._canonical_symbol(symbol)
        return float(self._positions.get(canonical_symbol, 0.0))

    def current_notional(self, symbol: str) -> float:
        """Return the absolute notional exposure for ``symbol``."""

        canonical_symbol = self._canonical_symbol(symbol)
        return float(self._last_notional.get(canonical_symbol, 0.0))

    def exposure_snapshot(self) -> dict[str, dict[str, float]]:
        """Return a serialisable snapshot of tracked positions and notionals."""

        snapshot: dict[str, dict[str, float]] = {}
        for symbol, position in self._positions.items():
            snapshot[symbol] = {
                "position": float(position),
                "notional": float(self._last_notional.get(symbol, 0.0)),
            }
        for symbol, notional in self._last_notional.items():
            if symbol in snapshot:
                snapshot[symbol]["notional"] = float(notional)
                continue
            snapshot[symbol] = {"position": 0.0, "notional": float(notional)}
        return dict(sorted(snapshot.items()))


class IdempotentRetryExecutor:
    """Retry wrapper that guarantees idempotency via explicit keys.

    The executor is designed for side-effect-free RPCs such as venue state
    queries and follows the retry governance guidance in ``docs/execution.md``.
    """

    def __init__(self, *, backoff: Callable[[int], float] | None = None) -> None:
        self._results: Dict[str, object] = {}
        self._backoff = backoff

    def run(
        self,
        key: str,
        func: Callable[[int], object],
        retries: int = 3,
        retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> object:
        """Execute ``func`` with retries while caching the first success.

        Args:
            key: Cache key ensuring idempotent semantics.
            func: Callable receiving the attempt count (starting at ``1``).
            retries: Maximum number of attempts.
            retry_exceptions: Tuple of exception types that should trigger retry
                behaviour.

        Returns:
            object: The result of ``func`` from the first successful attempt.

        Raises:
            Exception: Re-raises the last exception when retries are exhausted.

        Examples:
            >>> executor = IdempotentRetryExecutor()
            >>> executor.run("ping", lambda attempt: attempt)
            1
        """

        if key in self._results:
            return self._results[key]

        attempt = 0
        last_error: Exception | None = None
        while attempt < retries:
            attempt += 1
            try:
                result = func(attempt)
                self._results[key] = result
                return result
            except retry_exceptions as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                if self._backoff is not None:
                    delay = max(0.0, float(self._backoff(attempt)))
                    if delay:
                        time.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RuntimeError(
            "IdempotentRetryExecutor terminated without executing the callable"
        )


class DefaultPortfolioRiskAnalyzer(PortfolioRiskAnalyzer):
    """Portfolio risk analyzer compatible with :func:`portfolio_heat`.

    The analyzer mirrors the directional heat aggregation described in
    ``docs/risk_ml_observability.md`` and provides a lightweight default for
    CLI tooling and notebooks.
    """

    def heat(self, positions: Iterable[Mapping[str, float]]) -> float:
        total = 0.0
        for pos in positions:
            qty = float(pos.get("qty", 0.0))
            price = float(pos.get("price", 0.0))
            risk_weight = float(pos.get("risk_weight", 1.0))
            side = pos.get("side", "long")
            direction = 1.0 if side == "long" else -1.0
            total += abs(qty * price * risk_weight * direction)
        return float(total)


def portfolio_heat(positions: Iterable[Mapping[str, float]]) -> float:
    """Compute aggregate risk heat with directionality and weights.

    Args:
        positions: Iterable of dictionaries containing ``qty``, ``price``,
            ``risk_weight``, and ``side`` keys.

    Returns:
        float: Absolute risk heat used for monitoring dashboards in
        ``docs/monitoring.md``.
    """

    analyzer = DefaultPortfolioRiskAnalyzer()
    return analyzer.heat(positions)


__all__ = [
    "RiskError",
    "DataQualityError",
    "LimitViolation",
    "OrderRateExceeded",
    "RiskLimits",
    "KillSwitchStateStore",
    "RiskStateStore",
    "KillSwitchStateRecord",
    "SQLiteKillSwitchStateStore",
    "PostgresKillSwitchStateStore",
    "JsonRiskStateStore",
    "KillSwitch",
    "RiskManager",
    "DefaultPortfolioRiskAnalyzer",
    "IdempotentRetryExecutor",
    "portfolio_heat",
]
