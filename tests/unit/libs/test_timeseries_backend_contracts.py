# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for the time-series schema + ingestion backends.

These guard the ClickHouse / Timescale adapters against defects that would
corrupt or silently drop market data: non-deterministic column ordering, a
non-identifier (injectable) column name, a flipped query time-window boundary,
a driver-less adapter that fails open, a partial batch that commits, or a
non-monotonic retention policy.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from libs.db.timeseries.clickhouse import ClickHouseIngestionConnector, ClickHouseSchemaManager
from libs.db.timeseries.config import (
    DimensionColumn,
    IngestionConnectorConfig,
    MeasureColumn,
    RetentionPolicy,
    RollupAggregation,
    RollupMaterialization,
    SLAMetric,
    TimeSeriesSchema,
)
from libs.db.timeseries.timescale import TimescaleIngestionConnector, TimescaleSchemaManager


def _schema(*, database: str | None = None) -> TimeSeriesSchema:
    return TimeSeriesSchema(
        table="market_ticks",
        timestamp_column="ts",
        dimensions=(DimensionColumn(name="symbol"), DimensionColumn(name="venue")),
        measures=(MeasureColumn(name="price", data_type="Float64"),),
        database=database,
    )


def _retention() -> RetentionPolicy:
    return RetentionPolicy(hot=timedelta(days=1), warm=timedelta(days=7), drop=timedelta(days=30))


# ---------------------------------------------------------------------------
# Schema / config invariants
# ---------------------------------------------------------------------------


def test_column_order_is_deterministic_and_timestamp_first() -> None:
    schema = _schema()
    order = schema.column_order()
    assert order[0] == "ts"  # timestamp leads the ingestion tuple.
    assert order == ("ts", "symbol", "venue", "price")
    # Deterministic across repeated calls.
    assert schema.column_order() == order


def test_schema_rejects_non_identifier_names() -> None:
    with pytest.raises(ValueError):
        TimeSeriesSchema(
            table="ticks; DROP TABLE users",
            timestamp_column="ts",
            dimensions=(),
            measures=(MeasureColumn(name="price", data_type="Float64"),),
        )
    with pytest.raises(ValueError):
        DimensionColumn(name="bad name!")


def test_schema_requires_at_least_one_measure() -> None:
    with pytest.raises(ValueError):
        TimeSeriesSchema(table="t", timestamp_column="ts", dimensions=(), measures=())


def test_retention_policy_must_be_monotonic() -> None:
    with pytest.raises(ValueError):
        # warm before hot is non-monotonic and must fail closed.
        RetentionPolicy(hot=timedelta(days=7), warm=timedelta(days=1))


def test_retention_policy_rejects_non_positive_hot() -> None:
    with pytest.raises(ValueError):
        RetentionPolicy(hot=timedelta(0))


def test_rollup_requires_aggregations() -> None:
    with pytest.raises(ValueError):
        RollupMaterialization(name="r", interval=timedelta(minutes=1), aggregations=())


def test_rollup_aggregation_alias_must_be_identifier() -> None:
    with pytest.raises(ValueError):
        RollupAggregation(alias="not valid", expression="sum(price)", data_type="Float64")


def test_sla_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SLAMetric(name="m", query="SELECT 1", threshold_ms=0.0)


def test_ingestion_config_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError):
        IngestionConnectorConfig(batch_size=0)


# ---------------------------------------------------------------------------
# Query boundary + tz normalisation
# ---------------------------------------------------------------------------


def test_clickhouse_create_table_pins_utc_timestamp_and_is_deterministic() -> None:
    manager = ClickHouseSchemaManager(schema=_schema(), retention=_retention())
    ddl = manager.create_table_sql()
    assert "UTC" in ddl  # timezone normalisation is pinned into the DDL.
    assert manager.create_table_sql() == ddl  # deterministic rendering.


def test_timescale_create_table_uses_timestamptz() -> None:
    manager = TimescaleSchemaManager(schema=_schema(), retention=_retention())
    ddl = manager.create_table_sql()
    assert "ts TIMESTAMPTZ NOT NULL" in ddl


def test_clickhouse_query_boundary_is_inclusive_start_exclusive_end() -> None:
    from libs.db.timeseries.clickhouse import ClickHouseQueryBuilder

    query = ClickHouseQueryBuilder(_schema()).ohlcv_query()
    assert ">= %(start_ts)s" in query
    assert "< %(end_ts)s" in query
    assert "ORDER BY bucket ASC" in query  # timestamp order preserved in output.


def test_timescale_query_boundary_is_inclusive_start_exclusive_end() -> None:
    from libs.db.timeseries.timescale import TimescaleQueryBuilder

    query = TimescaleQueryBuilder(_schema()).ohlcv_query()
    assert ">= %(start_ts)s" in query
    assert "< %(end_ts)s" in query
    assert "ORDER BY bucket ASC" in query


# ---------------------------------------------------------------------------
# Ingestion adapters — fail closed / empty verdict / no partial commit
# ---------------------------------------------------------------------------


def test_clickhouse_connector_rejects_client_without_insert() -> None:
    with pytest.raises(TypeError):
        ClickHouseIngestionConnector(client=object(), schema=_schema())


def test_timescale_connector_rejects_connection_without_cursor() -> None:
    with pytest.raises(TypeError):
        TimescaleIngestionConnector(connection=object(), schema=_schema())


def test_clickhouse_flush_on_empty_buffer_is_explicit_zero() -> None:
    client = MagicMock()
    connector = ClickHouseIngestionConnector(client=client, schema=_schema())
    assert connector.flush() == 0
    client.insert.assert_not_called()


def test_timescale_ingest_many_empty_is_explicit_zero() -> None:
    conn = MagicMock()
    connector = TimescaleIngestionConnector(connection=conn, schema=_schema())
    assert connector.ingest_many([]) == 0
    conn.cursor.assert_not_called()
    conn.commit.assert_not_called()


def test_clickhouse_flush_sends_rows_in_canonical_column_order() -> None:
    client = MagicMock()
    schema = _schema()
    connector = ClickHouseIngestionConnector(client=client, schema=schema)
    records: list[Mapping[str, Any]] = [
        {"ts": "2024-01-01T00:00:00Z", "symbol": "BTC", "venue": "X", "price": 10.0}
    ]
    assert connector.ingest_many(records) == 0  # below batch size, buffered
    assert connector.flush() == 1
    _, kwargs = client.insert.call_args
    assert kwargs["column_names"] == list(schema.column_order())


def test_timescale_ingest_binds_parameters_and_commits() -> None:
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    connector = TimescaleIngestionConnector(connection=conn, schema=_schema())
    inserted = connector.ingest_many(
        [{"ts": "2024-01-01T00:00:00Z", "symbol": "BTC", "venue": "X", "price": 10.0}]
    )
    assert inserted == 1
    statement, rows = cursor.executemany.call_args.args
    assert "VALUES (%s, %s, %s, %s)" in statement  # placeholders, not interpolation.
    assert rows == [("2024-01-01T00:00:00Z", "BTC", "X", 10.0)]
    conn.commit.assert_called_once()


def test_timescale_partial_failure_does_not_commit() -> None:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.executemany.side_effect = RuntimeError("driver blew up")
    conn.cursor.return_value.__enter__.return_value = cursor
    connector = TimescaleIngestionConnector(connection=conn, schema=_schema())
    with pytest.raises(RuntimeError):
        connector.ingest_many(
            [{"ts": "2024-01-01T00:00:00Z", "symbol": "BTC", "venue": "X", "price": 1.0}]
        )
    # A batch that fails mid-flight must NOT be committed (no partial persist).
    conn.commit.assert_not_called()
