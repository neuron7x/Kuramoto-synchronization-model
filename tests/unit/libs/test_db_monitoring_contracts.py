# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for database observability helpers.

Defects guarded: mislabelled connection metrics (wrong database/host), a
statement-type classifier that mis-buckets queries, a monitor that never stops
its thread, and a size probe that raises instead of degrading to ``None``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from libs.db.monitoring import (
    DatabaseMonitor,
    _get_engine_metadata,
    _infer_statement_type,
    instrument_engine_metrics,
    resolve_connection_labels,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://user@db.internal:5432/geosync", ("geosync", "db.internal")),
        ("postgresql://user@db.internal:5432/", ("default", "db.internal")),
        ("sqlite:///:memory:", ("sqlite-memory", "local")),
        ("sqlite:////var/lib/geosync/prod.sqlite", ("prod.sqlite", "local")),
    ],
)
def test_resolve_connection_labels(url: str, expected: tuple[str, str]) -> None:
    assert resolve_connection_labels(url) == expected


def test_resolve_connection_labels_degrades_on_unparseable_string() -> None:
    # A malformed URL must degrade to explicit unknowns, not raise.
    assert resolve_connection_labels("::::not-a-url::::") == ("unknown", "unknown")


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT 1", "select"),
        ("  select 1", "select"),
        ("WITH cte AS (SELECT 1) SELECT * FROM cte", "select"),
        ("INSERT INTO t VALUES (1)", "insert"),
        ("UPDATE t SET x = 1", "update"),
        ("DELETE FROM t", "delete"),
        (b"SELECT 1", "select"),
        ("", "other"),
        ("   ", "other"),
        (12345, "other"),
        ("VACUUM", "vacuum"),
    ],
)
def test_infer_statement_type(statement: object, expected: str) -> None:
    assert _infer_statement_type(statement) == expected


def test_instrument_engine_metrics_is_idempotent() -> None:
    engine = create_engine("sqlite://", future=True)
    try:
        instrument_engine_metrics(engine)
        # A second call must be a no-op (guarded by query_metrics_attached), so
        # the same listener is not registered twice.
        instrument_engine_metrics(engine)
        info = _get_engine_metadata(engine)
        assert info["query_metrics_attached"] is True
    finally:
        engine.dispose()


def test_database_monitor_rejects_non_positive_interval() -> None:
    engine = create_engine("sqlite://", future=True)
    try:
        with pytest.raises(ValueError):
            DatabaseMonitor(engine, interval_seconds=0.0)
    finally:
        engine.dispose()


def test_database_monitor_run_once_observes_file_size(tmp_path: Path) -> None:
    db_path = tmp_path / "prod.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
        recorded: dict[str, object] = {}
        monitor = DatabaseMonitor(engine, interval_seconds=0.1)
        monitor._metrics = MagicMock()
        monitor._metrics.observe_database_size.side_effect = (
            lambda **kw: recorded.update(kw)
        )
        monitor.run_once()
        assert recorded["database"] == "prod.sqlite"
        assert isinstance(recorded["size_bytes"], float) and recorded["size_bytes"] > 0
    finally:
        engine.dispose()


def test_database_monitor_memory_db_size_is_none() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    try:
        monitor = DatabaseMonitor(engine, interval_seconds=0.1)
        monitor._metrics = MagicMock()
        # In-memory DB has no file: run_once must skip observation, not crash.
        monitor.run_once()
        monitor._metrics.observe_database_size.assert_not_called()
    finally:
        engine.dispose()


def test_database_monitor_size_probe_degrades_on_connect_failure() -> None:
    engine = create_engine("sqlite://", future=True)
    try:
        monitor = DatabaseMonitor(engine, interval_seconds=0.1)
        broken = MagicMock()
        broken.dialect.name = "postgresql"
        broken.connect.side_effect = RuntimeError("server unreachable")
        monitor._engine = broken
        # A failing size query must degrade to None, never propagate.
        assert monitor._read_database_size() is None
    finally:
        engine.dispose()


def test_database_monitor_start_is_idempotent_and_stops_thread() -> None:
    engine = create_engine("sqlite://", future=True)
    try:
        monitor = DatabaseMonitor(engine, interval_seconds=5.0)
        monitor.start()
        first_thread = monitor._thread
        monitor.start()  # second start must not spawn a new thread
        assert monitor._thread is first_thread
        assert first_thread is not None and first_thread.is_alive()
        monitor.stop(timeout=2.0)
        assert monitor._thread is None
    finally:
        engine.dispose()
