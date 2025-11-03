# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Database persistence backend for order ledger.

Provides optional persistence to Timescale or ClickHouse databases for
enhanced durability and queryability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, Protocol

__all__ = ["LedgerDatabaseBackend", "TimescaleLedgerBackend", "ClickHouseLedgerBackend"]


class LedgerDatabaseBackend(Protocol):
    """Protocol for database persistence backends."""

    def initialize_schema(self) -> None:
        """Create necessary tables and indexes."""
        ...

    def append_event(
        self,
        sequence: int,
        event: str,
        timestamp: str,
        order_id: str | None,
        correlation_id: str | None,
        metadata: Mapping[str, Any],
        order_snapshot: Mapping[str, Any] | None,
        state_snapshot: Mapping[str, Any] | None,
        digest: str,
        previous_digest: str | None,
    ) -> None:
        """Persist an event to the database."""
        ...

    def replay_events(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Replay events from the database."""
        ...

    def get_latest_sequence(self) -> int:
        """Get the latest sequence number in the database."""
        ...


@dataclass
class TimescaleLedgerBackend:
    """Timescale database backend for order ledger persistence."""

    connection_string: str
    table_name: str = "order_ledger_events"

    def __post_init__(self) -> None:
        self._conn = None
        try:
            import psycopg
            self._psycopg = psycopg
        except ImportError:
            raise ImportError(
                "psycopg is required for TimescaleLedgerBackend. "
                "Install with: pip install psycopg[binary]"
            )

    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg.connect(self.connection_string)
        return self._conn

    def initialize_schema(self) -> None:
        """Create ledger table as hypertable."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            # Create main events table
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    sequence BIGINT NOT NULL,
                    event TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    order_id TEXT,
                    correlation_id TEXT,
                    metadata JSONB,
                    order_snapshot JSONB,
                    state_snapshot JSONB,
                    digest TEXT NOT NULL,
                    previous_digest TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (timestamp, sequence)
                );
            """)

            # Convert to hypertable if not already
            cur.execute(f"""
                SELECT create_hypertable('{self.table_name}', 'timestamp',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );
            """)

            # Create indexes
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_sequence
                ON {self.table_name} (sequence);
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_order_id
                ON {self.table_name} (order_id)
                WHERE order_id IS NOT NULL;
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_correlation_id
                ON {self.table_name} (correlation_id)
                WHERE correlation_id IS NOT NULL;
            """)

            conn.commit()

    def append_event(
        self,
        sequence: int,
        event: str,
        timestamp: str,
        order_id: str | None,
        correlation_id: str | None,
        metadata: Mapping[str, Any],
        order_snapshot: Mapping[str, Any] | None,
        state_snapshot: Mapping[str, Any] | None,
        digest: str,
        previous_digest: str | None,
    ) -> None:
        """Persist event to Timescale."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.table_name}
                (sequence, event, timestamp, order_id, correlation_id,
                 metadata, order_snapshot, state_snapshot, digest, previous_digest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sequence,
                    event,
                    timestamp,
                    order_id,
                    correlation_id,
                    json.dumps(metadata) if metadata else None,
                    json.dumps(order_snapshot) if order_snapshot else None,
                    json.dumps(state_snapshot) if state_snapshot else None,
                    digest,
                    previous_digest,
                ),
            )
            conn.commit()

    def replay_events(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Replay events from Timescale."""
        conn = self._get_connection()
        query = f"SELECT * FROM {self.table_name}"
        conditions = []
        params = []

        if start_sequence is not None:
            conditions.append("sequence >= %s")
            params.append(start_sequence)
        if end_sequence is not None:
            conditions.append("sequence <= %s")
            params.append(end_sequence)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY sequence ASC"

        with conn.cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                yield {
                    "sequence": row[0],
                    "event": row[1],
                    "timestamp": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
                    "order_id": row[3],
                    "correlation_id": row[4],
                    "metadata": row[5],
                    "order_snapshot": row[6],
                    "state_snapshot": row[7],
                    "digest": row[8],
                    "previous_digest": row[9],
                }

    def get_latest_sequence(self) -> int:
        """Get the latest sequence number."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COALESCE(MAX(sequence), 0) FROM {self.table_name}")
            result = cur.fetchone()
            return int(result[0]) if result else 0


@dataclass
class ClickHouseLedgerBackend:
    """ClickHouse database backend for order ledger persistence."""

    connection_string: str
    table_name: str = "order_ledger_events"
    database: str = "tradepulse"

    def __post_init__(self) -> None:
        try:
            import clickhouse_connect
            self._client = clickhouse_connect.get_client(
                host=self.connection_string.split("://")[1].split(":")[0],
                port=8123,
                database=self.database,
            )
        except ImportError:
            raise ImportError(
                "clickhouse-connect is required for ClickHouseLedgerBackend. "
                "Install with: pip install clickhouse-connect"
            )

    def initialize_schema(self) -> None:
        """Create ledger table in ClickHouse."""
        self._client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.database}.{self.table_name} (
                sequence UInt64,
                event String,
                timestamp DateTime64(3),
                order_id Nullable(String),
                correlation_id Nullable(String),
                metadata String,
                order_snapshot Nullable(String),
                state_snapshot Nullable(String),
                digest String,
                previous_digest Nullable(String),
                created_at DateTime DEFAULT now()
            )
            ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (sequence, timestamp)
            SETTINGS index_granularity = 8192
        """)

    def append_event(
        self,
        sequence: int,
        event: str,
        timestamp: str,
        order_id: str | None,
        correlation_id: str | None,
        metadata: Mapping[str, Any],
        order_snapshot: Mapping[str, Any] | None,
        state_snapshot: Mapping[str, Any] | None,
        digest: str,
        previous_digest: str | None,
    ) -> None:
        """Persist event to ClickHouse."""
        self._client.insert(
            f"{self.database}.{self.table_name}",
            [
                [
                    sequence,
                    event,
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                    order_id,
                    correlation_id,
                    json.dumps(metadata) if metadata else "{}",
                    json.dumps(order_snapshot) if order_snapshot else None,
                    json.dumps(state_snapshot) if state_snapshot else None,
                    digest,
                    previous_digest,
                ]
            ],
            column_names=[
                "sequence",
                "event",
                "timestamp",
                "order_id",
                "correlation_id",
                "metadata",
                "order_snapshot",
                "state_snapshot",
                "digest",
                "previous_digest",
            ],
        )

    def replay_events(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Replay events from ClickHouse."""
        query = f"SELECT * FROM {self.database}.{self.table_name}"
        conditions = []

        if start_sequence is not None:
            conditions.append(f"sequence >= {start_sequence}")
        if end_sequence is not None:
            conditions.append(f"sequence <= {end_sequence}")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY sequence ASC"

        result = self._client.query(query)
        for row in result.result_rows:
            yield {
                "sequence": row[0],
                "event": row[1],
                "timestamp": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
                "order_id": row[3],
                "correlation_id": row[4],
                "metadata": json.loads(row[5]) if row[5] else {},
                "order_snapshot": json.loads(row[6]) if row[6] else None,
                "state_snapshot": json.loads(row[7]) if row[7] else None,
                "digest": row[8],
                "previous_digest": row[9],
            }

    def get_latest_sequence(self) -> int:
        """Get the latest sequence number."""
        result = self._client.query(
            f"SELECT COALESCE(MAX(sequence), 0) FROM {self.database}.{self.table_name}"
        )
        return int(result.result_rows[0][0]) if result.result_rows else 0
