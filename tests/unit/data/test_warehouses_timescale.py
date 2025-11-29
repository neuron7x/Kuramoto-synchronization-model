# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for TimescaleDB warehouse integration."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from core.data.models import InstrumentType, MarketMetadata, PriceTick
from core.data.warehouses.timescale import (
    TimescaleConfig,
    TimescaleWarehouse,
    _chunk_iterable,
    _TimescaleIdentifiers,
)


class TestTimescaleConfig:
    """Tests for TimescaleConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Verify default configuration values."""
        config = TimescaleConfig()
        assert config.schema == "public"
        assert config.raw_table == "raw_ticks"
        assert config.rollup_table == "minute_bars"
        assert config.retention_days == 30
        assert config.rollup_retention_days == 180
        assert config.chunk_interval_hours == 24

    def test_custom_config_values(self) -> None:
        """Verify custom configuration values are applied."""
        config = TimescaleConfig(
            schema="custom_schema",
            raw_table="custom_ticks",
            rollup_table="custom_bars",
            retention_days=60,
            rollup_retention_days=365,
            chunk_interval_hours=12,
        )
        assert config.schema == "custom_schema"
        assert config.raw_table == "custom_ticks"
        assert config.rollup_table == "custom_bars"
        assert config.retention_days == 60
        assert config.rollup_retention_days == 365
        assert config.chunk_interval_hours == 12

    def test_invalid_schema_name_raises(self) -> None:
        """Verify invalid schema name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            TimescaleConfig(schema="invalid-schema")

    def test_invalid_raw_table_name_raises(self) -> None:
        """Verify invalid raw_table name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            TimescaleConfig(raw_table="drop; table")

    def test_invalid_rollup_table_name_raises(self) -> None:
        """Verify invalid rollup_table name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            TimescaleConfig(rollup_table="my table")


class TestTimescaleIdentifiers:
    """Tests for _TimescaleIdentifiers dataclass."""

    def test_from_config_creates_identifiers_public_schema(self) -> None:
        """Verify identifiers are created from config with public schema."""
        config = TimescaleConfig(
            schema="public",
            raw_table="test_ticks",
            rollup_table="test_bars",
        )
        identifiers = _TimescaleIdentifiers.from_config(config)
        assert identifiers.schema == "public"
        assert identifiers.raw_table == "test_ticks"
        assert identifiers.rollup_table == "test_bars"
        assert identifiers.schema_prefix == ""
        assert identifiers.raw_qualified == "test_ticks"
        assert identifiers.rollup_qualified == "test_bars"

    def test_from_config_creates_identifiers_custom_schema(self) -> None:
        """Verify identifiers are created from config with custom schema."""
        config = TimescaleConfig(
            schema="custom",
            raw_table="test_ticks",
            rollup_table="test_bars",
        )
        identifiers = _TimescaleIdentifiers.from_config(config)
        assert identifiers.schema == "custom"
        assert identifiers.schema_prefix == "custom."
        assert identifiers.raw_qualified == "custom.test_ticks"
        assert identifiers.rollup_qualified == "custom.test_bars"


class TestTimescaleWarehouse:
    """Tests for TimescaleWarehouse class."""

    @pytest.fixture
    def mock_connection(self) -> MagicMock:
        """Create a mock database connection."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn

    @pytest.fixture
    def warehouse(self, mock_connection: MagicMock) -> TimescaleWarehouse:
        """Create a test warehouse."""
        return TimescaleWarehouse(mock_connection)

    @pytest.fixture
    def sample_tick(self) -> PriceTick:
        """Create a sample PriceTick for testing."""
        metadata = MarketMetadata(
            symbol="BTCUSD",
            venue="binance",
            instrument_type=InstrumentType.SPOT,
        )
        return PriceTick(
            metadata=metadata,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            price=Decimal("50000.50"),
            volume=Decimal("1.5"),
            trade_id="trade123",
        )

    def test_bootstrap_statements_returns_correct_count(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap returns expected number of statements."""
        statements = warehouse.bootstrap_statements()
        assert len(statements) == 6

    def test_bootstrap_statements_creates_extensions(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap creates extension statement."""
        statements = warehouse.bootstrap_statements()
        ext_statement = statements[0]
        assert "timescaledb" in ext_statement.sql.lower()
        assert "pgcrypto" in ext_statement.sql.lower()

    def test_bootstrap_statements_creates_raw_table(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap creates raw table statement."""
        statements = warehouse.bootstrap_statements()
        raw_statement = statements[1]
        assert "CREATE TABLE IF NOT EXISTS" in raw_statement.sql
        assert "raw_ticks" in raw_statement.sql

    def test_bootstrap_statements_creates_hypertable(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap creates hypertable statement."""
        statements = warehouse.bootstrap_statements()
        hypertable_statement = statements[2]
        assert "create_hypertable" in hypertable_statement.sql
        assert "chunk_time_interval" in hypertable_statement.sql

    def test_bootstrap_statements_creates_policies(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap creates policy statements."""
        statements = warehouse.bootstrap_statements()
        policy_statement = statements[3]
        assert "add_retention_policy" in policy_statement.sql
        assert "add_compression_policy" in policy_statement.sql

    def test_bootstrap_statements_creates_rollup_view(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify bootstrap creates rollup materialized view."""
        statements = warehouse.bootstrap_statements()
        rollup_statement = statements[4]
        assert "MATERIALIZED VIEW" in rollup_statement.sql
        assert "timescaledb.continuous" in rollup_statement.sql
        assert "time_bucket" in rollup_statement.sql

    def test_rollup_jobs_returns_jobs(self, warehouse: TimescaleWarehouse) -> None:
        """Verify rollup jobs are returned."""
        jobs = warehouse.rollup_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "timescale-minute-bars-refresh"
        assert "refresh_continuous_aggregate" in jobs[0].statement.sql
        assert jobs[0].schedule_hint == "*/5 * * * *"

    def test_maintenance_tasks_returns_tasks(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify maintenance tasks are returned."""
        tasks = warehouse.maintenance_tasks()
        assert len(tasks) == 2
        assert tasks[0].name == "timescale-reorder-chunks"
        assert tasks[0].cadence == "daily"
        assert tasks[1].name == "timescale-analyze"
        assert tasks[1].cadence == "daily"

    def test_sla_queries_returns_queries(self, warehouse: TimescaleWarehouse) -> None:
        """Verify SLA queries are returned."""
        queries = warehouse.sla_queries()
        assert len(queries) == 3
        assert queries[0].name == "tick_ingest_latency"
        assert queries[1].name == "rollup_freshness"
        assert queries[2].name == "ingest_throughput"

    def test_benchmark_scenarios_returns_scenarios(
        self, warehouse: TimescaleWarehouse
    ) -> None:
        """Verify benchmark scenarios are returned."""
        scenarios = warehouse.benchmark_scenarios()
        assert len(scenarios) == 2
        assert scenarios[0].name == "timescale-binary-copy-40k"
        assert scenarios[0].target_qps == 40000
        assert scenarios[1].name == "timescale-dashboard-rollup"
        assert scenarios[1].target_qps == 750

    def test_backup_plan_returns_steps(self, warehouse: TimescaleWarehouse) -> None:
        """Verify backup plan steps are returned."""
        steps = warehouse.backup_plan()
        assert len(steps) == 3
        assert "pg_basebackup" in steps[0].command
        assert "checksum" in steps[1].command.lower()
        assert "restore" in steps[2].command.lower()

    def test_ingest_ticks_with_empty_list(self, warehouse: TimescaleWarehouse) -> None:
        """Verify empty tick list is handled gracefully."""
        warehouse.ingest_ticks([])  # Should not raise

    def test_ingest_ticks_invalid_chunk_size_raises(
        self, warehouse: TimescaleWarehouse, sample_tick: PriceTick
    ) -> None:
        """Verify invalid chunk size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            warehouse.ingest_ticks([sample_tick], chunk_size=0)

    def test_ingest_ticks_success(
        self, mock_connection: MagicMock, sample_tick: PriceTick
    ) -> None:
        """Verify tick ingestion commits successfully."""
        warehouse = TimescaleWarehouse(mock_connection)
        warehouse.ingest_ticks([sample_tick])
        mock_connection.commit.assert_called_once()

    def test_ingest_ticks_rollback_on_error(
        self, mock_connection: MagicMock, sample_tick: PriceTick
    ) -> None:
        """Verify tick ingestion rolls back on error."""
        # Configure the cursor's executemany to raise an exception
        cursor = MagicMock()
        cursor.executemany.side_effect = Exception("Database error")
        mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

        warehouse = TimescaleWarehouse(mock_connection)
        with pytest.raises(Exception, match="Database error"):
            warehouse.ingest_ticks([sample_tick])
        mock_connection.rollback.assert_called_once()

    def test_ingest_ticks_with_custom_batch_size(
        self, mock_connection: MagicMock
    ) -> None:
        """Verify tick ingestion respects custom batch size."""
        warehouse = TimescaleWarehouse(mock_connection, batch_size=2)
        # Batch size should be 2 by default
        assert warehouse._batch_size == 2

    def test_ingest_ticks_multiple_chunks(
        self, mock_connection: MagicMock, sample_tick: PriceTick
    ) -> None:
        """Verify tick ingestion splits into multiple chunks."""
        ticks = [sample_tick for _ in range(5)]
        warehouse = TimescaleWarehouse(mock_connection, batch_size=2)
        warehouse.ingest_ticks(ticks, chunk_size=2)

        cursor = mock_connection.cursor.return_value.__enter__.return_value
        # Should have 3 batches: 2, 2, 1
        assert cursor.executemany.call_count == 3
        mock_connection.commit.assert_called_once()


class TestChunkIterable:
    """Tests for _chunk_iterable utility function."""

    def test_chunk_iterable_single_chunk(self) -> None:
        """Verify single chunk when items fit."""
        metadata = MarketMetadata(
            symbol="BTCUSD",
            venue="binance",
            instrument_type=InstrumentType.SPOT,
        )
        tick = PriceTick(
            metadata=metadata,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            price=Decimal("50000.50"),
            volume=Decimal("1.5"),
        )
        items = [tick, tick, tick]
        chunks = list(_chunk_iterable(items, 10))
        assert len(chunks) == 1
        assert len(chunks[0]) == 3

    def test_chunk_iterable_multiple_chunks(self) -> None:
        """Verify multiple chunks are created."""
        metadata = MarketMetadata(
            symbol="BTCUSD",
            venue="binance",
            instrument_type=InstrumentType.SPOT,
        )
        tick = PriceTick(
            metadata=metadata,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            price=Decimal("50000.50"),
            volume=Decimal("1.5"),
        )
        items = [tick] * 5
        chunks = list(_chunk_iterable(items, 2))
        assert len(chunks) == 3
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 1

    def test_chunk_iterable_empty_list(self) -> None:
        """Verify empty list produces no chunks."""
        chunks = list(_chunk_iterable([], 10))
        assert len(chunks) == 0
