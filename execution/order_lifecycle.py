# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Deterministic order lifecycle management with PostgreSQL journaling.

The module provides two collaborating components:

``OrderLifecycleStore``
    Persists every state transition to a relational database (PostgreSQL in
    production, SQLite is supported for testing).  Each transition is written to
    a durable journal with an idempotency key so callers can safely retry after
    crashes or network failures.

``OrderLifecycle``
    Implements a deterministic state machine on top of
    :class:`domain.order.OrderStatus`.  The lifecycle only allows transitions
    explicitly declared in the transition table, guaranteeing that replaying the
    same events yields the same terminal state regardless of timing or
    repetition.

The design goals address the operational requirements expressed in the
deployment runbooks:

* **Idempotent states** – transitions are guarded by correlation identifiers so
  repeated notifications from execution venues or recovery workers are safe;
* **Crash recovery** – the journal acts as a write-ahead log that can be replayed
  after a process restart to reconstruct the in-memory order book;
* **PostgreSQL journaling** – SQL emitted by ``OrderLifecycleStore`` uses
  PostgreSQL semantics by default, while still supporting SQLite during unit
  tests;
* **Deterministic transitions** – the state machine is encoded as an explicit
  mapping making it impossible to branch into ambiguous states.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from domain import OrderStatus
from libs.db import DataAccessLayer

__all__ = [
    "OrderEvent",
    "OrderTransition",
    "OrderLifecycleStore",
    "OrderLifecycle",
]


class OrderEvent(str, Enum):
    """Events that drive the state machine."""

    SUBMIT = "submit"
    ACK = "ack"
    FILL_PARTIAL = "fill_partial"
    FILL_FINAL = "fill_final"
    CANCEL = "cancel"
    REJECT = "reject"


TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
)


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        candidate = value.strip()
        candidate = candidate.replace(" ", "T")
        if candidate.endswith("Z"):
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if "+" not in candidate and not candidate.endswith("Z"):
            candidate += "+00:00"
        return datetime.fromisoformat(candidate)
    raise TypeError(f"Unsupported timestamp type: {type(value)!r}")


@dataclass(slots=True)
class OrderTransition:
    """Materialized representation of a lifecycle transition."""

    sequence: int
    order_id: str
    correlation_id: str
    event: OrderEvent
    from_status: OrderStatus
    to_status: OrderStatus
    details: Mapping[str, Any]
    created_at: datetime


class OrderLifecycleStore:
    """Durable persistence for order lifecycle transitions."""

    def __init__(
        self,
        dal: DataAccessLayer,
        *,
        schema: str | None = "execution",
        table: str = "order_journal",
        dialect: str = "postgres",
    ) -> None:
        self._dal = dal
        self._schema = schema
        self._table = table
        self._dialect = dialect.lower()
        if self._dialect not in {"postgres", "sqlite"}:
            raise ValueError("dialect must be either 'postgres' or 'sqlite'")

        self._placeholder = "%s" if self._dialect == "postgres" else "?"
        self._qualified_table = self._build_qualified_table()
        self._insert_sql = self._build_insert_sql()
        self._select_one_sql = self._build_select_one_sql()
        self._history_sql = self._build_history_sql()
        self._latest_sql = self._build_latest_sql()

    # ------------------------------------------------------------------
    # Schema helpers
    def ensure_schema(self) -> None:
        """Create the journal table if it does not exist."""

        if self._dialect == "postgres" and self._schema is not None:
            schema_sql = (
                f"CREATE SCHEMA IF NOT EXISTS {_quote_identifier(self._schema)}"
            )
            self._dal.execute(schema_sql, ())

        create_sql = self._build_create_table_sql()
        self._dal.execute(create_sql, ())

        index_name = self._index_name()
        index_sql = (
            f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
            f"ON {self._qualified_table} (order_id, correlation_id)"
        )
        self._dal.execute(index_sql, ())

    def _build_create_table_sql(self) -> str:
        if self._dialect == "postgres":
            details_type = "JSONB NOT NULL DEFAULT '{}'::jsonb"
            created_default = "timezone('utc', now())"
            serial = "BIGSERIAL"
            timestamp_type = "TIMESTAMPTZ NOT NULL"
        else:  # sqlite
            details_type = "TEXT NOT NULL DEFAULT '{}'"
            created_default = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
            serial = "INTEGER"
            timestamp_type = "TEXT NOT NULL"

        return (
            f"CREATE TABLE IF NOT EXISTS {self._qualified_table} ("
            f"sequence {serial} PRIMARY KEY"
            f", order_id TEXT NOT NULL"
            f", correlation_id TEXT NOT NULL"
            f", event TEXT NOT NULL"
            f", from_status TEXT NOT NULL"
            f", to_status TEXT NOT NULL"
            f", details {details_type}"
            f", created_at {timestamp_type} DEFAULT {created_default}"
            ")"
        )

    def _build_qualified_table(self) -> str:
        table = _quote_identifier(self._table)
        if self._schema:
            return f"{_quote_identifier(self._schema)}.{table}"
        return table

    def _index_name(self) -> str:
        schema_part = self._schema or "public"
        name = f"{schema_part}_{self._table}_uq"
        safe = name.replace(".", "_")
        if not _IDENTIFIER_RE.match(safe):
            safe = re.sub(r"[^A-Za-z0-9_]", "_", safe)
        return _quote_identifier(safe)

    def _build_insert_sql(self) -> str:
        details_placeholder = (
            f"{self._placeholder}::jsonb"
            if self._dialect == "postgres"
            else self._placeholder
        )
        values = ", ".join(
            [
                self._placeholder,
                self._placeholder,
                self._placeholder,
                self._placeholder,
                self._placeholder,
                details_placeholder,
            ]
        )
        return "".join(
            [
                "INSERT INTO ",
                self._qualified_table,
                " (order_id, correlation_id, event, from_status, to_status, details) ",
                "VALUES (",
                values,
                ") ON CONFLICT (order_id, correlation_id) DO NOTHING",
            ]
        )

    def _build_select_one_sql(self) -> str:
        return "".join(
            [
                "SELECT sequence, order_id, correlation_id, event, from_status, ",
                "to_status, details, created_at ",
                "FROM ",
                self._qualified_table,
                " WHERE order_id = ",
                self._placeholder,
                " AND correlation_id = ",
                self._placeholder,
            ]
        )

    def _build_history_sql(self) -> str:
        return "".join(
            [
                "SELECT sequence, order_id, correlation_id, event, from_status, ",
                "to_status, details, created_at ",
                "FROM ",
                self._qualified_table,
                " WHERE order_id = ",
                self._placeholder,
                " ORDER BY sequence",
            ]
        )

    def _build_latest_sql(self) -> str:
        return "".join(
            [
                "SELECT t.sequence, t.order_id, t.correlation_id, t.event, ",
                "t.from_status, t.to_status, t.details, t.created_at ",
                "FROM ",
                self._qualified_table,
                " AS t JOIN (",
                "SELECT order_id, MAX(sequence) AS max_sequence FROM ",
                self._qualified_table,
                " GROUP BY order_id",
                ") AS latest ON t.order_id = latest.order_id ",
                "AND t.sequence = latest.max_sequence",
            ]
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    def append(
        self,
        order_id: str,
        correlation_id: str,
        event: OrderEvent,
        *,
        from_status: OrderStatus,
        to_status: OrderStatus,
        details: Mapping[str, Any] | None = None,
    ) -> OrderTransition:
        payload = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
        params = (
            order_id,
            correlation_id,
            event.value,
            from_status.value,
            to_status.value,
            payload,
        )

        existing_sql = self._select_one_sql
        latest_sql = "".join(
            [
                "SELECT sequence, order_id, correlation_id, event, from_status, ",
                "to_status, details, created_at FROM ",
                self._qualified_table,
                " WHERE order_id = ",
                self._placeholder,
                " ORDER BY sequence DESC LIMIT 1",
            ]
        )
        if self._dialect == "postgres":
            existing_sql += " FOR UPDATE"
            latest_sql += " FOR UPDATE"

        with self._dal.transaction() as connection:
            cursor = connection.cursor()

            cursor.execute(existing_sql, (order_id, correlation_id))
            existing = cursor.fetchone()
            if existing is not None:
                stored = self._row_to_transition(self._coerce_row(existing))
                if stored.event != event or stored.to_status != to_status:
                    raise ValueError(
                        "Idempotency violation: correlation_id already recorded with different transition"
                    )
                if stored.from_status != from_status:
                    raise ValueError(
                        "Inconsistent transition replay detected for correlation_id"
                    )
                return stored

            cursor.execute(latest_sql, (order_id,))
            latest = cursor.fetchone()
            if latest is not None:
                last_transition = self._row_to_transition(self._coerce_row(latest))
                if last_transition.to_status != from_status:
                    raise ValueError(
                        "Concurrent transition detected for order: expected %s, found %s"
                        % (from_status.value, last_transition.to_status.value)
                    )

            cursor.execute(self._insert_sql, params)

            cursor.execute(self._select_one_sql, (order_id, correlation_id))
            stored_row = cursor.fetchone()

        if stored_row is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Failed to read back order transition")

        stored = self._row_to_transition(self._coerce_row(stored_row))
        if stored.event != event or stored.to_status != to_status:
            raise ValueError(
                "Idempotency violation: correlation_id already recorded with different transition"
            )
        if stored.from_status != from_status:
            raise ValueError(
                "Inconsistent transition replay detected for correlation_id"
            )
        return stored

    def get(self, order_id: str, correlation_id: str) -> OrderTransition | None:
        row = self._dal.fetch_one(self._select_one_sql, (order_id, correlation_id))
        if row is None:
            return None
        return self._row_to_transition(self._coerce_row(row))

    def last_transition(self, order_id: str) -> OrderTransition | None:
        sql = "".join(
            [
                "SELECT sequence, order_id, correlation_id, event, from_status, ",
                "to_status, details, created_at FROM ",
                self._qualified_table,
                " WHERE order_id = ",
                self._placeholder,
                " ORDER BY sequence DESC LIMIT 1",
            ]
        )
        row = self._dal.fetch_one(sql, (order_id,))
        if row is None:
            return None
        return self._row_to_transition(self._coerce_row(row))

    def history(self, order_id: str) -> list[OrderTransition]:
        rows = self._dal.fetch_all(self._history_sql, (order_id,))
        return [self._row_to_transition(self._coerce_row(row)) for row in rows]

    def active_orders(self) -> dict[str, OrderTransition]:
        rows = self._dal.fetch_all(self._latest_sql, ())
        transitions = [self._row_to_transition(self._coerce_row(row)) for row in rows]
        return {
            transition.order_id: transition
            for transition in transitions
            if transition.to_status not in TERMINAL_STATUSES
        }

    # ------------------------------------------------------------------
    # Conversion helpers
    @staticmethod
    def _coerce_row(row: Mapping[str, Any] | Sequence[Any]) -> MutableMapping[str, Any]:
        if isinstance(row, Mapping):
            return dict(row)
        columns = [
            "sequence",
            "order_id",
            "correlation_id",
            "event",
            "from_status",
            "to_status",
            "details",
            "created_at",
        ]
        return {column: row[idx] for idx, column in enumerate(columns)}

    @staticmethod
    def _decode_details(payload: Any) -> Mapping[str, Any]:
        if payload in (None, "", b""):
            return {}
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:  # pragma: no cover - defensive guard
                return {"raw": payload}
        if isinstance(payload, Mapping):
            return dict(payload)
        return {"raw": payload}

    def _row_to_transition(self, data: MutableMapping[str, Any]) -> OrderTransition:
        details = self._decode_details(data.get("details"))
        created_at = _parse_timestamp(data.get("created_at"))
        return OrderTransition(
            sequence=int(data["sequence"]),
            order_id=str(data["order_id"]),
            correlation_id=str(data["correlation_id"]),
            event=OrderEvent(str(data["event"])),
            from_status=OrderStatus(str(data["from_status"])),
            to_status=OrderStatus(str(data["to_status"])),
            details=details,
            created_at=created_at,
        )


class OrderLifecycle:
    """Deterministic state machine backed by :class:`OrderLifecycleStore`."""

    _TRANSITIONS: Mapping[tuple[OrderStatus, OrderEvent], OrderStatus] = {
        (OrderStatus.PENDING, OrderEvent.SUBMIT): OrderStatus.PENDING,
        (OrderStatus.PENDING, OrderEvent.ACK): OrderStatus.OPEN,
        (OrderStatus.PENDING, OrderEvent.CANCEL): OrderStatus.CANCELLED,
        (OrderStatus.PENDING, OrderEvent.REJECT): OrderStatus.REJECTED,
        (OrderStatus.OPEN, OrderEvent.ACK): OrderStatus.OPEN,
        (OrderStatus.OPEN, OrderEvent.FILL_PARTIAL): OrderStatus.PARTIALLY_FILLED,
        (OrderStatus.OPEN, OrderEvent.FILL_FINAL): OrderStatus.FILLED,
        (OrderStatus.OPEN, OrderEvent.CANCEL): OrderStatus.CANCELLED,
        (OrderStatus.OPEN, OrderEvent.REJECT): OrderStatus.REJECTED,
        (
            OrderStatus.PARTIALLY_FILLED,
            OrderEvent.FILL_PARTIAL,
        ): OrderStatus.PARTIALLY_FILLED,
        (
            OrderStatus.PARTIALLY_FILLED,
            OrderEvent.FILL_FINAL,
        ): OrderStatus.FILLED,
        (
            OrderStatus.PARTIALLY_FILLED,
            OrderEvent.CANCEL,
        ): OrderStatus.CANCELLED,
        (
            OrderStatus.FILLED,
            OrderEvent.FILL_FINAL,
        ): OrderStatus.FILLED,
        (
            OrderStatus.CANCELLED,
            OrderEvent.CANCEL,
        ): OrderStatus.CANCELLED,
        (
            OrderStatus.REJECTED,
            OrderEvent.REJECT,
        ): OrderStatus.REJECTED,
    }

    def __init__(
        self,
        store: OrderLifecycleStore,
        *,
        initial_status: OrderStatus = OrderStatus.PENDING,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._initial_status = initial_status
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Public API
    def apply(
        self,
        order_id: str,
        event: OrderEvent,
        *,
        correlation_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> OrderTransition:
        if not order_id:
            raise ValueError("order_id must be provided")
        if not correlation_id:
            raise ValueError("correlation_id must be provided")

        with self._lock:
            existing = self._store.get(order_id, correlation_id)
            if existing is not None:
                if existing.event != event:
                    raise ValueError(
                        "Idempotency violation: correlation_id already recorded with different event"
                    )
                return existing
            current = self._store.last_transition(order_id)
            from_status = current.to_status if current else self._initial_status
            to_status = self._resolve_transition(from_status, event)
            payload = dict(metadata or {})
            payload.setdefault("event_ts", self._clock().isoformat())
            transition = self._store.append(
                order_id,
                correlation_id,
                event,
                from_status=from_status,
                to_status=to_status,
                details=payload,
            )
            return transition

    def get_state(self, order_id: str) -> OrderStatus:
        with self._lock:
            current = self._store.last_transition(order_id)
            if current is None:
                return self._initial_status
            return current.to_status

    def history(self, order_id: str) -> list[OrderTransition]:
        return self._store.history(order_id)

    def recover_active_orders(self) -> dict[str, OrderTransition]:
        return self._store.active_orders()

    # ------------------------------------------------------------------
    # Internal helpers
    def _resolve_transition(
        self, from_status: OrderStatus, event: OrderEvent
    ) -> OrderStatus:
        try:
            return self._TRANSITIONS[(from_status, event)]
        except KeyError as exc:
            raise ValueError(
                f"Transition {from_status.value!r} -> {event.value!r} is not permitted"
            ) from exc
