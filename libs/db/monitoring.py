"""Database observability helpers for engine instrumentation and monitoring."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from weakref import WeakKeyDictionary

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL, make_url

from core.utils.metrics import get_metrics_collector

__all__ = [
    "DatabaseMonitor",
    "instrument_engine_metrics",
    "resolve_connection_labels",
]


LOGGER = logging.getLogger(__name__)
_ENGINE_METADATA: "WeakKeyDictionary[Engine, dict[str, object]]" = WeakKeyDictionary()


def resolve_connection_labels(url: URL | str) -> tuple[str, str]:
    """Return (database, host) labels for the provided SQLAlchemy URL."""

    if isinstance(url, str):
        try:
            url = make_url(url)
        except Exception:  # pragma: no cover - defensive parsing
            return ("unknown", "unknown")

    database = _normalise_database_label(url)
    host = _normalise_host_label(url)
    return (database, host)


def instrument_engine_metrics(engine: Engine, *, dsn: str | None = None) -> None:
    """Attach instrumentation and derived metadata to ``engine``."""

    info = _get_engine_metadata(engine)
    database, host = resolve_connection_labels(dsn or engine.url)
    if "connection_labels" not in info:
        info["connection_labels"] = (database, host)

    if info.get("query_metrics_attached"):
        return

    metrics = get_metrics_collector()

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:  # pragma: no cover - exercised in integration tests
        context._tradepulse_query_start = time.perf_counter()
        context._tradepulse_statement_type = _infer_statement_type(statement)

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:  # pragma: no cover - exercised in integration tests
        start = getattr(context, "_tradepulse_query_start", None)
        statement_type = getattr(context, "_tradepulse_statement_type", "other")
        if start is None:
            return
        metrics.observe_database_query(
            database=database,
            host=host,
            statement_type=statement_type,
            status="success",
            duration=time.perf_counter() - start,
        )

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context) -> None:  # pragma: no cover - defensive guard
        context = exception_context.execution_context
        if context is None:
            return
        start = getattr(context, "_tradepulse_query_start", None)
        statement_type = getattr(context, "_tradepulse_statement_type", "other")
        duration = 0.0 if start is None else time.perf_counter() - start
        metrics.observe_database_query(
            database=database,
            host=host,
            statement_type=statement_type,
            status="error",
            duration=duration,
        )

    info["query_metrics_attached"] = True


class DatabaseMonitor:
    """Periodically collect size statistics for a database engine."""

    def __init__(self, engine: Engine, *, interval_seconds: float = 60.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self._engine = engine
        self._interval = float(interval_seconds)
        self._metrics = get_metrics_collector()
        self._database, self._host = resolve_connection_labels(engine.url)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background monitoring thread."""

        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"db-monitor-{self._database}",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop the monitoring thread and wait for completion."""

        with self._lock:
            thread = self._thread
            if not thread:
                return
            self._stop_event.set()
        thread.join(timeout or self._interval + 1.0)
        with self._lock:
            self._thread = None

    def run_once(self) -> None:
        """Collect a single set of metrics synchronously."""

        size = self._read_database_size()
        if size is None:
            return
        self._metrics.observe_database_size(
            database=self._database,
            host=self._host,
            size_bytes=size,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _run_loop(self) -> None:
        try:
            self.run_once()
            while not self._stop_event.wait(self._interval):
                self.run_once()
        except Exception:  # pragma: no cover - defensive guard
            LOGGER.exception(
                "Database monitor failed",
                extra={"database": self._database, "host": self._host},
            )

    def _read_database_size(self) -> float | None:
        dialect = self._engine.dialect.name
        try:
            if dialect.startswith("postgres"):
                with self._engine.connect() as connection:
                    result = connection.execute(
                        text("SELECT pg_database_size(current_database())")
                    )
                    value = result.scalar_one()
                return float(value)

            if dialect.startswith("sqlite"):
                return self._sqlite_database_size()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning(
                "Failed to collect database size",
                extra={
                    "database": self._database,
                    "host": self._host,
                    "dialect": dialect,
                    "error": str(exc),
                },
            )
        return None

    def _sqlite_database_size(self) -> float | None:
        url = self._engine.url
        if url.database in (None, "", ":memory:"):
            return None
        try:
            return float(Path(url.database).resolve().stat().st_size)
        except FileNotFoundError:
            return None


def _normalise_database_label(url: URL) -> str:
    backend = url.get_backend_name()
    if backend == "sqlite":
        if url.database in (None, "", ":memory:"):
            return "sqlite-memory"
        return Path(url.database).name
    database = (url.database or "default").strip()
    return database or "default"


def _normalise_host_label(url: URL) -> str:
    backend = url.get_backend_name()
    if backend == "sqlite":
        return "local"
    host = (url.host or "unknown").strip()
    return host or "unknown"


def _get_engine_metadata(engine: Engine) -> dict[str, object]:
    info = getattr(engine, "info", None)
    if isinstance(
        info, dict
    ):  # pragma: no branch - attribute available on modern SQLAlchemy
        return info.setdefault("tradepulse", {})
    return _ENGINE_METADATA.setdefault(engine, {})


def _infer_statement_type(statement: object) -> str:
    if isinstance(statement, (bytes, bytearray)):
        try:
            statement = statement.decode("utf-8", errors="ignore")
        except Exception:
            return "other"

    if not isinstance(statement, str):
        return "other"

    stripped = statement.lstrip()
    if not stripped:
        return "other"

    token = stripped.split(None, 1)[0].upper()
    if token == "WITH":
        return "select"
    known = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT"}
    if token in known:
        return token.lower()
    return token.lower()
