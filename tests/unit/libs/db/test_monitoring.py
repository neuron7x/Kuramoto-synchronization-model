# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib.util
import sys
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine, text

from core.utils import metrics as metrics_module
from core.utils.metrics import MetricsCollector

_MODULE_PATH = Path(__file__).resolve().parents[4] / "libs" / "db" / "monitoring.py"
_SPEC = importlib.util.spec_from_file_location("geosync.test.db_monitoring", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive guard
    raise RuntimeError("Unable to load database monitoring module for testing")
db_monitoring = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(db_monitoring)
sys.modules.setdefault("geosync.test.db_monitoring", db_monitoring)
DatabaseMonitor = db_monitoring.DatabaseMonitor
instrument_engine_metrics = db_monitoring.instrument_engine_metrics


def test_instrument_engine_metrics_records_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CollectorRegistry()
    collector = MetricsCollector(registry)
    monkeypatch.setattr(metrics_module, "_collector", collector, raising=False)
    monkeypatch.setattr(db_monitoring, "get_metrics_collector", lambda: collector)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        instrument_engine_metrics(engine)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            with pytest.raises(Exception):
                connection.execute(text("SELECT * FROM missing_table"))
    finally:
        engine.dispose()

    success_labels = {
        "database": "sqlite-memory",
        "host": "local",
        "statement_type": "select",
        "status": "success",
    }
    error_labels = {**success_labels, "status": "error"}

    success_count = registry.get_sample_value(
        "geosync_database_query_latency_seconds_count",
        success_labels,
    )
    error_count = registry.get_sample_value(
        "geosync_database_query_latency_seconds_count",
        error_labels,
    )
    success_total = registry.get_sample_value(
        "geosync_database_query_total",
        success_labels,
    )
    error_total = registry.get_sample_value(
        "geosync_database_query_total",
        error_labels,
    )

    assert success_count == 1.0
    assert error_count == 1.0
    assert success_total == 1.0
    assert error_total == 1.0


def test_database_monitor_collects_sqlite_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = CollectorRegistry()
    collector = MetricsCollector(registry)
    monkeypatch.setattr(metrics_module, "_collector", collector, raising=False)
    monkeypatch.setattr(db_monitoring, "get_metrics_collector", lambda: collector)

    db_path = tmp_path / "geosync.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE metrics_test (id INTEGER PRIMARY KEY, value TEXT)")
            )
            connection.execute(text("INSERT INTO metrics_test(value) VALUES ('alpha')"))

        monitor = DatabaseMonitor(engine, interval_seconds=0.1)
        monitor.run_once()
    finally:
        engine.dispose()

    labels = {"database": db_path.name, "host": "local"}
    size_value = registry.get_sample_value("geosync_database_size_bytes", labels)
    growth_value = registry.get_sample_value("geosync_database_size_growth_bytes", labels)

    assert size_value is not None and size_value > 0
    assert growth_value == 0.0
