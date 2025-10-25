"""Event sourcing primitives for TradePulse.

This module introduces a pragmatic Event Sourcing + CQRS toolkit that can be
used by services without committing to a specific framework.  The implementation
focuses on five core capabilities:

* **Durable event store** backed by PostgreSQL JSONB or any store exposing the
  same protocol.
* **Aggregate roots** for the primary trading concepts (orders, positions,
  portfolios) with snapshotting support.
* **Event replay utilities** that power debugging sessions or projection
  rebuilding jobs.
* **Snapshots** and read-model projections to keep performance predictable.
* **Materialized view helpers** for CQRS read models.

The code is written for Python 3.11 using typing-rich, maintainable patterns
that match industry practices circa 2025.  All heavy-weight dependencies are
optional; concrete integrations (for example with ``asyncpg``) can be supplied
by the application layer.  The default PostgreSQL implementation uses JSONB to
store events and snapshots in a single schema, enabling fast, append-only
workloads while remaining debuggable through SQL queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
)
from uuid import UUID, uuid4

from ...domain import Order, OrderSide, OrderType, Position


# ---------------------------------------------------------------------------
# Type aliases and JSON helpers
# ---------------------------------------------------------------------------

JSONDict = Dict[str, Any]
MetadataDict = Dict[str, Any]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EventStoreError(RuntimeError):
    """Base class for event store related failures."""


class ConcurrencyError(EventStoreError):
    """Raised when optimistic locking detects an unexpected version."""


class SnapshotNotFound(EventStoreError):
    """Raised when no snapshot is stored for a given aggregate."""


class ProjectionError(RuntimeError):
    """Raised when a projection cannot be rebuilt or refreshed."""


# ---------------------------------------------------------------------------
# Events, envelopes and snapshots
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DomainEvent:
    """Base domain event.

    Each event captures the aggregate identifier it belongs to, the timestamp of
    occurrence, metadata for correlation/causation, and a stable UUID.  Concrete
    events extend this dataclass with domain-specific payload fields.
    """

    aggregate_id: str
    occurred_at: datetime = field(default_factory=_utcnow)
    metadata: MetadataDict = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)

    @property
    def event_type(self) -> str:
        """Return the fully qualified event type name used for persistence."""

        return self.__class__.__name__

    def payload(self) -> JSONDict:
        """Return a JSON-serialisable payload excluding shared bookkeeping."""

        payload: JSONDict = {}
        for field_info in fields(self):
            name = field_info.name
            if name in {"aggregate_id", "occurred_at", "metadata", "event_id"}:
                continue
            payload[name] = getattr(self, name)
        return payload


@dataclass(slots=True)
class EventEnvelope:
    """Transport representation of a persisted event."""

    aggregate_id: str
    aggregate_type: str
    version: int
    event_type: str
    data: JSONDict
    metadata: MetadataDict
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def from_event(
        cls,
        event: DomainEvent,
        aggregate_type: str,
        version: int,
    ) -> "EventEnvelope":
        return cls(
            aggregate_id=event.aggregate_id,
            aggregate_type=aggregate_type,
            version=version,
            event_type=event.event_type,
            data=event.payload(),
            metadata=dict(event.metadata),
            event_id=event.event_id,
            occurred_at=event.occurred_at,
        )


@dataclass(slots=True)
class AggregateSnapshot:
    """Serialised snapshot for fast aggregate rehydration."""

    aggregate_id: str
    aggregate_type: str
    version: int
    state: JSONDict
    taken_at: datetime = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Event store protocol and PostgreSQL implementation
# ---------------------------------------------------------------------------


class EventStore(Protocol):
    """Abstract event store contract."""

    async def append_to_stream(
        self,
        aggregate_type: str,
        aggregate_id: str,
        events: Sequence[DomainEvent],
        *,
        expected_version: int | None,
    ) -> Sequence[EventEnvelope]:
        """Persist events ensuring optimistic concurrency."""

    async def load_stream(
        self,
        aggregate_type: str,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> Sequence[EventEnvelope]:
        """Load events in order for a specific aggregate."""

    async def load_events(
        self,
        *,
        aggregate_type: str | None = None,
        after: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[EventEnvelope]:
        """Load events across aggregates for projection or debugging."""

    async def store_snapshot(self, snapshot: AggregateSnapshot) -> None:
        """Persist a snapshot."""

    async def load_snapshot(
        self, aggregate_type: str, aggregate_id: str
    ) -> AggregateSnapshot:
        """Load latest snapshot for an aggregate."""

    async def replay(
        self,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        aggregate_type: str | None = None,
        batch_size: int = 500,
        after: datetime | None = None,
    ) -> None:
        """Replay events through the provided handler."""


class PostgresJSONBEventStore(EventStore):
    """Event store implementation backed by PostgreSQL JSONB."""

    def __init__(
        self,
        pool: Any,
        *,
        schema: str = "public",
        events_table: str = "event_store_events",
        snapshots_table: str = "event_store_snapshots",
    ) -> None:
        self._pool = pool
        self._schema = schema
        self._events_table = events_table
        self._snapshots_table = snapshots_table

    # -- helpers -----------------------------------------------------------------

    @property
    def _qualified_events(self) -> str:
        return f'"{self._schema}"."{self._events_table}"'

    @property
    def _qualified_snapshots(self) -> str:
        return f'"{self._schema}"."{self._snapshots_table}"'

    async def setup(self) -> None:
        """Create required tables if they do not exist."""

        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._qualified_events} (
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    version BIGINT NOT NULL,
                    event_id UUID PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    data JSONB NOT NULL,
                    metadata JSONB NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE UNIQUE INDEX IF NOT EXISTS
                    {self._events_table}_id_version_idx
                ON {self._qualified_events} (aggregate_id, aggregate_type, version);

                CREATE TABLE IF NOT EXISTS {self._qualified_snapshots} (
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    version BIGINT NOT NULL,
                    state JSONB NOT NULL,
                    taken_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (aggregate_id, aggregate_type)
                );
                """
            )

    async def append_to_stream(
        self,
        aggregate_type: str,
        aggregate_id: str,
        events: Sequence[DomainEvent],
        *,
        expected_version: int | None,
    ) -> Sequence[EventEnvelope]:
        if not events:
            return []

        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            async with conn.transaction():
                current_version = await conn.fetchval(
                    f"""
                    SELECT COALESCE(MAX(version), 0)
                    FROM {self._qualified_events}
                    WHERE aggregate_id = $1 AND aggregate_type = $2
                    """,
                    aggregate_id,
                    aggregate_type,
                )
                if expected_version is not None and current_version != expected_version:
                    raise ConcurrencyError(
                        "expected version %s but got %s for aggregate %s/%s"
                        % (expected_version, current_version, aggregate_type, aggregate_id)
                    )

                envelopes: list[EventEnvelope] = []
                base_version = int(current_version)
                for offset, event in enumerate(events, start=1):
                    version = base_version + offset
                    envelope = EventEnvelope.from_event(
                        event, aggregate_type=aggregate_type, version=version
                    )
                    await conn.execute(
                        f"""
                        INSERT INTO {self._qualified_events}
                        (aggregate_id, aggregate_type, version, event_id, event_type,
                         data, metadata, occurred_at)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)
                        """,
                        envelope.aggregate_id,
                        envelope.aggregate_type,
                        envelope.version,
                        envelope.event_id,
                        envelope.event_type,
                        envelope.data,
                        envelope.metadata,
                        envelope.occurred_at,
                    )
                    envelopes.append(envelope)
                return envelopes

    async def load_stream(
        self,
        aggregate_type: str,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> Sequence[EventEnvelope]:
        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            rows = await conn.fetch(
                f"""
                SELECT aggregate_id, aggregate_type, version, event_type, data,
                       metadata, event_id, occurred_at
                FROM {self._qualified_events}
                WHERE aggregate_id = $1
                  AND aggregate_type = $2
                  AND version > $3
                ORDER BY version ASC
                """,
                aggregate_id,
                aggregate_type,
                after_version,
            )
        return [
            EventEnvelope(
                aggregate_id=row["aggregate_id"],
                aggregate_type=row["aggregate_type"],
                version=row["version"],
                event_type=row["event_type"],
                data=dict(row["data"]),
                metadata=dict(row["metadata"]),
                event_id=row["event_id"],
                occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    async def load_events(
        self,
        *,
        aggregate_type: str | None = None,
        after: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[EventEnvelope]:
        conditions: list[str] = []
        params: list[Any] = []

        if aggregate_type is not None:
            params.append(aggregate_type)
            conditions.append(f"aggregate_type = ${len(params)}")
        if after is not None:
            params.append(after)
            conditions.append(f"occurred_at > ${len(params)}")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            rows = await conn.fetch(
                f"""
                SELECT aggregate_id, aggregate_type, version, event_type, data,
                       metadata, event_id, occurred_at
                FROM {self._qualified_events}
                {where_clause}
                ORDER BY occurred_at ASC
                LIMIT {limit} OFFSET {offset}
                """,
                *params,
            )

        return [
            EventEnvelope(
                aggregate_id=row["aggregate_id"],
                aggregate_type=row["aggregate_type"],
                version=row["version"],
                event_type=row["event_type"],
                data=dict(row["data"]),
                metadata=dict(row["metadata"]),
                event_id=row["event_id"],
                occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    async def store_snapshot(self, snapshot: AggregateSnapshot) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            await conn.execute(
                f"""
                INSERT INTO {self._qualified_snapshots}
                (aggregate_id, aggregate_type, version, state, taken_at)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                ON CONFLICT (aggregate_id, aggregate_type)
                DO UPDATE SET version = EXCLUDED.version,
                              state = EXCLUDED.state,
                              taken_at = EXCLUDED.taken_at
                """,
                snapshot.aggregate_id,
                snapshot.aggregate_type,
                snapshot.version,
                snapshot.state,
                snapshot.taken_at,
            )

    async def load_snapshot(
        self, aggregate_type: str, aggregate_id: str
    ) -> AggregateSnapshot:
        async with self._pool.acquire() as conn:  # type: ignore[call-arg]
            row = await conn.fetchrow(
                f"""
                SELECT aggregate_id, aggregate_type, version, state, taken_at
                FROM {self._qualified_snapshots}
                WHERE aggregate_id = $1 AND aggregate_type = $2
                """,
                aggregate_id,
                aggregate_type,
            )
        if row is None:
            raise SnapshotNotFound(
                f"no snapshot found for aggregate {aggregate_type}/{aggregate_id}"
            )
        return AggregateSnapshot(
            aggregate_id=row["aggregate_id"],
            aggregate_type=row["aggregate_type"],
            version=row["version"],
            state=dict(row["state"]),
            taken_at=row["taken_at"],
        )

    async def replay(
        self,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        aggregate_type: str | None = None,
        batch_size: int = 500,
        after: datetime | None = None,
    ) -> None:
        offset = 0
        while True:
            batch = await self.load_events(
                aggregate_type=aggregate_type,
                after=after,
                limit=batch_size,
                offset=offset,
            )
            if not batch:
                return
            for envelope in batch:
                await handler(envelope)
            offset += len(batch)


# ---------------------------------------------------------------------------
# Projection contracts
# ---------------------------------------------------------------------------


class Projection(Protocol):
    """CQRS projection contract."""

    async def handle(self, event: EventEnvelope) -> None:  # pragma: no cover - protocol
        ...

    async def reset(self) -> None:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class ProjectionManager:
    """Coordinate projection rebuilds and event replays."""

    store: EventStore
    projections: Sequence[Projection]

    async def rebuild(self, *, aggregate_type: str | None = None) -> None:
        """Drop and rebuild all registered projections."""

        for projection in self.projections:
            await projection.reset()

        async def _dispatch(event: EventEnvelope) -> None:
            for projection in self.projections:
                await projection.handle(event)

        await self.store.replay(_dispatch, aggregate_type=aggregate_type)


# ---------------------------------------------------------------------------
# Materialized view support
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MaterializedView:
    """Describe a PostgreSQL materialized view used as read model."""

    name: str
    refresh_sql: str
    concurrent: bool = True


@dataclass(slots=True)
class MaterializedViewManager:
    """Utility to refresh materialized views after projections replay."""

    connection_factory: Callable[[], Awaitable[Any]]
    views: Sequence[MaterializedView]

    async def refresh_all(self) -> None:
        conn = await self.connection_factory()
        try:
            for view in self.views:
                concurrently = "CONCURRENTLY" if view.concurrent else ""
                statement = f"REFRESH MATERIALIZED VIEW {concurrently} {view.name};"
                await conn.execute(statement)
        except Exception as exc:  # pragma: no cover - defensive programming
            raise ProjectionError("failed to refresh materialized views") from exc
        finally:
            release = getattr(conn, "close", None)
            if callable(release):
                await release()


# ---------------------------------------------------------------------------
# Aggregate infrastructure
# ---------------------------------------------------------------------------


class EventSourcedAggregate:
    """Base class for aggregates following the event sourcing pattern."""

    aggregate_type: ClassVar[str]

    def __init__(self, aggregate_id: str) -> None:
        self.id = aggregate_id
        self.version = 0
        self._pending: list[DomainEvent] = []

    # -- lifecycle -------------------------------------------------------------

    def _apply_event(self, event: DomainEvent, *, is_new: bool) -> None:
        handler_name = f"_apply_{event.event_type}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            raise ProjectionError(f"Missing handler {handler_name} for {self.aggregate_type}")
        handler(event)
        self.version += 1
        if is_new:
            self._pending.append(event)

    def _raise_event(self, event: DomainEvent) -> None:
        if event.aggregate_id != self.id:
            raise ValueError(
                "event aggregate id %s does not match aggregate %s" % (event.aggregate_id, self.id)
            )
        self._apply_event(event, is_new=True)

    def load_from_history(self, history: Iterable[EventEnvelope]) -> None:
        for envelope in history:
            domain_event = self._deserialize_event(envelope)
            self._apply_event(domain_event, is_new=False)
            self.version = envelope.version

    def _deserialize_event(self, envelope: EventEnvelope) -> DomainEvent:
        factory = getattr(self, f"_event_{envelope.event_type}", None)
        if factory is None:
            raise ProjectionError(
                f"Aggregate {self.aggregate_type} cannot deserialise {envelope.event_type}"
            )
        return factory(envelope)

    def collect_new_events(self) -> Sequence[DomainEvent]:
        events = tuple(self._pending)
        self._pending.clear()
        return events

    def to_snapshot(self) -> AggregateSnapshot:
        return AggregateSnapshot(
            aggregate_id=self.id,
            aggregate_type=self.aggregate_type,
            version=self.version,
            state=self._serialize_state(),
        )

    def _serialize_state(self) -> JSONDict:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    @classmethod
    def from_snapshot(cls, snapshot: AggregateSnapshot) -> "EventSourcedAggregate":
        aggregate = cls(snapshot.aggregate_id)
        aggregate.version = snapshot.version
        aggregate._restore_state(snapshot.state)
        return aggregate

    def _restore_state(self, state: Mapping[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Order aggregate
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OrderCreated(DomainEvent):
    symbol: str
    side: str
    quantity: float
    price: float | None
    order_type: str


@dataclass(slots=True)
class OrderSubmitted(DomainEvent):
    venue_order_id: str


@dataclass(slots=True)
class OrderFillRecorded(DomainEvent):
    fill_id: str
    quantity: float
    price: float
    fees: float | None = None


@dataclass(slots=True)
class OrderCancelled(DomainEvent):
    reason: str | None = None


@dataclass(slots=True)
class OrderRejected(DomainEvent):
    reason: str | None = None


class OrderAggregate(EventSourcedAggregate):
    aggregate_type = "order"

    def __init__(self, aggregate_id: str) -> None:
        super().__init__(aggregate_id)
        self._order: Order | None = None

    # -- factory methods -------------------------------------------------------

    @classmethod
    def create(
        cls,
        order_id: str,
        *,
        symbol: str,
        side: OrderSide | str,
        quantity: float,
        price: float | None,
        order_type: OrderType | str,
        metadata: MetadataDict | None = None,
    ) -> "OrderAggregate":
        aggregate = cls(order_id)
        event = OrderCreated(
            aggregate_id=order_id,
            symbol=symbol,
            side=OrderSide(side).value,
            quantity=quantity,
            price=price,
            order_type=OrderType(order_type).value,
            metadata=metadata or {},
        )
        aggregate._raise_event(event)
        return aggregate

    # -- event handlers --------------------------------------------------------

    def _apply_OrderCreated(self, event: OrderCreated) -> None:
        self._order = Order(
            symbol=event.symbol,
            side=event.side,
            quantity=event.quantity,
            price=event.price,
            order_type=event.order_type,
            order_id=self.id,
        )

    def _apply_OrderSubmitted(self, event: OrderSubmitted) -> None:
        assert self._order is not None
        self._order.mark_submitted(event.venue_order_id)

    def _apply_OrderFillRecorded(self, event: OrderFillRecorded) -> None:
        assert self._order is not None
        self._order.record_fill(event.quantity, event.price)

    def _apply_OrderCancelled(self, event: OrderCancelled) -> None:
        assert self._order is not None
        self._order.cancel()
        if event.reason:
            self._order.rejection_reason = event.reason

    def _apply_OrderRejected(self, event: OrderRejected) -> None:
        assert self._order is not None
        self._order.reject(event.reason)

    # -- event factories -------------------------------------------------------

    def _event_OrderCreated(self, envelope: EventEnvelope) -> OrderCreated:
        return OrderCreated(
            aggregate_id=envelope.aggregate_id,
            symbol=envelope.data["symbol"],
            side=envelope.data["side"],
            quantity=envelope.data["quantity"],
            price=envelope.data.get("price"),
            order_type=envelope.data["order_type"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_OrderSubmitted(self, envelope: EventEnvelope) -> OrderSubmitted:
        return OrderSubmitted(
            aggregate_id=envelope.aggregate_id,
            venue_order_id=envelope.data["venue_order_id"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_OrderFillRecorded(self, envelope: EventEnvelope) -> OrderFillRecorded:
        return OrderFillRecorded(
            aggregate_id=envelope.aggregate_id,
            fill_id=envelope.data["fill_id"],
            quantity=envelope.data["quantity"],
            price=envelope.data["price"],
            fees=envelope.data.get("fees"),
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_OrderCancelled(self, envelope: EventEnvelope) -> OrderCancelled:
        return OrderCancelled(
            aggregate_id=envelope.aggregate_id,
            reason=envelope.data.get("reason"),
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_OrderRejected(self, envelope: EventEnvelope) -> OrderRejected:
        return OrderRejected(
            aggregate_id=envelope.aggregate_id,
            reason=envelope.data.get("reason"),
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    # -- command methods -------------------------------------------------------

    def mark_submitted(self, venue_order_id: str, metadata: MetadataDict | None = None) -> None:
        self._raise_event(
            OrderSubmitted(
                aggregate_id=self.id,
                venue_order_id=venue_order_id,
                metadata=metadata or {},
            )
        )

    def record_fill(
        self,
        *,
        fill_id: str,
        quantity: float,
        price: float,
        fees: float | None = None,
        metadata: MetadataDict | None = None,
    ) -> None:
        self._raise_event(
            OrderFillRecorded(
                aggregate_id=self.id,
                fill_id=fill_id,
                quantity=quantity,
                price=price,
                fees=fees,
                metadata=metadata or {},
            )
        )

    def cancel(self, *, reason: str | None = None, metadata: MetadataDict | None = None) -> None:
        self._raise_event(
            OrderCancelled(
                aggregate_id=self.id,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def reject(self, *, reason: str | None = None, metadata: MetadataDict | None = None) -> None:
        self._raise_event(
            OrderRejected(
                aggregate_id=self.id,
                reason=reason,
                metadata=metadata or {},
            )
        )

    # -- state serialisation ---------------------------------------------------

    def _serialize_state(self) -> JSONDict:
        return {
            "order": self._order.to_dict() if self._order else None,
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        order_state = state.get("order")
        if order_state is None:
            self._order = None
            return
        self._order = Order(
            symbol=order_state["symbol"],
            side=order_state["side"],
            quantity=order_state["quantity"],
            price=order_state.get("price"),
            order_type=order_state["order_type"],
            stop_price=order_state.get("stop_price"),
            order_id=self.id,
            status=order_state["status"],
            filled_quantity=order_state["filled_quantity"],
            average_price=order_state.get("average_price"),
            rejection_reason=order_state.get("rejection_reason"),
        )


# ---------------------------------------------------------------------------
# Position aggregate
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PositionMarked(DomainEvent):
    symbol: str
    side: str
    quantity: float
    price: float


@dataclass(slots=True)
class PositionMarkedToMarket(DomainEvent):
    symbol: str
    price: float


class PositionAggregate(EventSourcedAggregate):
    aggregate_type = "position"

    def __init__(self, aggregate_id: str, symbol: str | None = None) -> None:
        super().__init__(aggregate_id)
        self.symbol = symbol or aggregate_id
        self.position = Position(symbol=self.symbol)

    # -- factory ---------------------------------------------------------------

    @classmethod
    def create(cls, position_id: str, symbol: str) -> "PositionAggregate":
        return cls(position_id, symbol=symbol)

    # -- handlers --------------------------------------------------------------

    def _apply_PositionMarked(self, event: PositionMarked) -> None:
        self.position.apply_fill(event.side, event.quantity, event.price)

    def _apply_PositionMarkedToMarket(self, event: PositionMarkedToMarket) -> None:
        self.position.mark_to_market(event.price)

    # -- factories -------------------------------------------------------------

    def _event_PositionMarked(self, envelope: EventEnvelope) -> PositionMarked:
        return PositionMarked(
            aggregate_id=envelope.aggregate_id,
            symbol=envelope.data["symbol"],
            side=envelope.data["side"],
            quantity=envelope.data["quantity"],
            price=envelope.data["price"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_PositionMarkedToMarket(
        self, envelope: EventEnvelope
    ) -> PositionMarkedToMarket:
        return PositionMarkedToMarket(
            aggregate_id=envelope.aggregate_id,
            symbol=envelope.data["symbol"],
            price=envelope.data["price"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    # -- commands --------------------------------------------------------------

    def apply_fill(
        self,
        *,
        side: OrderSide | str,
        quantity: float,
        price: float,
        metadata: MetadataDict | None = None,
    ) -> None:
        self._raise_event(
            PositionMarked(
                aggregate_id=self.id,
                symbol=self.symbol,
                side=OrderSide(side).value,
                quantity=quantity,
                price=price,
                metadata=metadata or {},
            )
        )

    def mark_to_market(self, *, price: float, metadata: MetadataDict | None = None) -> None:
        self._raise_event(
            PositionMarkedToMarket(
                aggregate_id=self.id,
                symbol=self.symbol,
                price=price,
                metadata=metadata or {},
            )
        )

    # -- state -----------------------------------------------------------------

    def _serialize_state(self) -> JSONDict:
        return {
            "symbol": self.position.symbol,
            "quantity": self.position.quantity,
            "entry_price": self.position.entry_price,
            "current_price": self.position.current_price,
            "unrealized_pnl": self.position.unrealized_pnl,
            "realized_pnl": self.position.realized_pnl,
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self.symbol = state["symbol"]
        self.position = Position(
            symbol=self.symbol,
            quantity=state.get("quantity", 0.0),
            entry_price=state.get("entry_price", 0.0),
            current_price=state.get("current_price", 0.0),
            unrealized_pnl=state.get("unrealized_pnl", 0.0),
            realized_pnl=state.get("realized_pnl", 0.0),
        )


# ---------------------------------------------------------------------------
# Portfolio aggregate
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PortfolioCreated(DomainEvent):
    base_currency: str
    initial_cash: float


@dataclass(slots=True)
class PortfolioCashAdjusted(DomainEvent):
    amount: float
    reason: str | None = None


@dataclass(slots=True)
class PortfolioPositionUpdated(DomainEvent):
    symbol: str
    side: str
    quantity: float
    price: float


class PortfolioAggregate(EventSourcedAggregate):
    aggregate_type = "portfolio"

    def __init__(self, aggregate_id: str) -> None:
        super().__init__(aggregate_id)
        self.base_currency = "USD"
        self.cash_balance = 0.0
        self.positions: MutableMapping[str, PositionAggregate] = {}

    # -- factories -------------------------------------------------------------

    @classmethod
    def create(
        cls,
        portfolio_id: str,
        *,
        base_currency: str,
        initial_cash: float,
        metadata: MetadataDict | None = None,
    ) -> "PortfolioAggregate":
        aggregate = cls(portfolio_id)
        aggregate._raise_event(
            PortfolioCreated(
                aggregate_id=portfolio_id,
                base_currency=base_currency,
                initial_cash=initial_cash,
                metadata=metadata or {},
            )
        )
        return aggregate

    # -- handlers --------------------------------------------------------------

    def _apply_PortfolioCreated(self, event: PortfolioCreated) -> None:
        self.base_currency = event.base_currency
        self.cash_balance = event.initial_cash

    def _apply_PortfolioCashAdjusted(self, event: PortfolioCashAdjusted) -> None:
        self.cash_balance += event.amount

    def _apply_PortfolioPositionUpdated(self, event: PortfolioPositionUpdated) -> None:
        position = self.positions.get(event.symbol)
        if position is None:
            position = PositionAggregate.create(position_id=event.symbol, symbol=event.symbol)
            self.positions[event.symbol] = position
        position.position.apply_fill(
            event.side,
            event.quantity,
            event.price,
        )

    # -- event factories -------------------------------------------------------

    def _event_PortfolioCreated(self, envelope: EventEnvelope) -> PortfolioCreated:
        return PortfolioCreated(
            aggregate_id=envelope.aggregate_id,
            base_currency=envelope.data["base_currency"],
            initial_cash=envelope.data["initial_cash"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_PortfolioCashAdjusted(
        self, envelope: EventEnvelope
    ) -> PortfolioCashAdjusted:
        return PortfolioCashAdjusted(
            aggregate_id=envelope.aggregate_id,
            amount=envelope.data["amount"],
            reason=envelope.data.get("reason"),
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    def _event_PortfolioPositionUpdated(
        self, envelope: EventEnvelope
    ) -> PortfolioPositionUpdated:
        return PortfolioPositionUpdated(
            aggregate_id=envelope.aggregate_id,
            symbol=envelope.data["symbol"],
            side=envelope.data["side"],
            quantity=envelope.data["quantity"],
            price=envelope.data["price"],
            metadata=envelope.metadata,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )

    # -- commands --------------------------------------------------------------

    def adjust_cash(
        self,
        *,
        amount: float,
        reason: str | None = None,
        metadata: MetadataDict | None = None,
    ) -> None:
        self._raise_event(
            PortfolioCashAdjusted(
                aggregate_id=self.id,
                amount=amount,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def record_fill(
        self,
        *,
        symbol: str,
        side: OrderSide | str,
        quantity: float,
        price: float,
        metadata: MetadataDict | None = None,
    ) -> None:
        self._raise_event(
            PortfolioPositionUpdated(
                aggregate_id=self.id,
                symbol=symbol,
                side=OrderSide(side).value,
                quantity=quantity,
                price=price,
                metadata=metadata or {},
            )
        )

    # -- serialisation ---------------------------------------------------------

    def _serialize_state(self) -> JSONDict:
        return {
            "base_currency": self.base_currency,
            "cash_balance": self.cash_balance,
            "positions": {
                symbol: position._serialize_state()  # using protected method for efficiency
                for symbol, position in self.positions.items()
            },
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self.base_currency = state.get("base_currency", "USD")
        self.cash_balance = state.get("cash_balance", 0.0)
        self.positions = {}
        positions_state = state.get("positions", {})
        for symbol, payload in positions_state.items():
            position = PositionAggregate.create(position_id=symbol, symbol=symbol)
            position._restore_state(payload)
            self.positions[symbol] = position


__all__ = [
    "AggregateSnapshot",
    "ConcurrencyError",
    "DomainEvent",
    "EventEnvelope",
    "EventSourcedAggregate",
    "EventStore",
    "EventStoreError",
    "MaterializedView",
    "MaterializedViewManager",
    "OrderAggregate",
    "OrderCancelled",
    "OrderCreated",
    "OrderFillRecorded",
    "OrderRejected",
    "OrderSubmitted",
    "PortfolioAggregate",
    "PortfolioCashAdjusted",
    "PortfolioCreated",
    "PortfolioPositionUpdated",
    "PositionAggregate",
    "PositionMarked",
    "PositionMarkedToMarket",
    "PostgresJSONBEventStore",
    "Projection",
    "ProjectionError",
    "ProjectionManager",
    "SnapshotNotFound",
]

