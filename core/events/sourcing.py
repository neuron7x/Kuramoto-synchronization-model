"""Domain event sourcing infrastructure for TradePulse.

This module provides a minimal yet production-ready implementation of an
append-only event store tailored for PostgreSQL JSONB storage, aggregate roots
for key trading entities, snapshotting helpers, projection rebuild tooling, and
materialized view refresh utilities for read models.  The design embraces
classic Event Sourcing + CQRS patterns while remaining pragmatic for Python
3.11 and SQLAlchemy 2.x.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Protocol,
)
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    and_,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from domain.order import OrderSide, OrderStatus, OrderType

LOGGER = logging.getLogger(__name__)

__all__ = [
    "AggregateRoot",
    "AggregateSnapshot",
    "ConcurrencyError",
    "DomainEvent",
    "EventEnvelope",
    "EventReplay",
    "MaterializedView",
    "MaterializedViewManager",
    "OrderAggregate",
    "OrderCreated",
    "OrderFilled",
    "OrderSubmitted",
    "OrderCancelled",
    "OrderRejected",
    "PositionAggregate",
    "PositionAdjusted",
    "PositionClosed",
    "PositionOpened",
    "PortfolioAggregate",
    "PortfolioCreated",
    "CashDeposited",
    "CashWithdrawn",
    "PositionLinked",
    "PnLRealized",
    "ExposureUpdated",
    "PostgresEventStore",
    "Projection",
    "ProjectionRebuilder",
    "restore_from_snapshot",
    "take_snapshot",
]


# ---------------------------------------------------------------------------
# Event payloads and envelopes
# ---------------------------------------------------------------------------


_EVENT_REGISTRY: dict[str, type["DomainEvent"]] = {}


class DomainEvent(BaseModel):
    """Base class for domain events stored in the event store."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # ``stream_version`` is injected during hydration and excluded from persistence.
    stream_version: int | None = Field(default=None, exclude=True)

    # ``event_name`` is derived automatically to avoid accidental drift between
    # the class name and the persisted value.  Subclasses may override when a
    # historical rename is required.
    event_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Register subclasses for lookup during event hydration."""

        super().__init_subclass__(**kwargs)
        cls.event_name = getattr(cls, "event_name", cls.__name__)
        if cls.event_name in _EVENT_REGISTRY:
            raise ValueError(
                f"Duplicate domain event name registered: {cls.event_name}"
            )
        _EVENT_REGISTRY[cls.event_name] = cls

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DomainEvent":
        """Hydrate an event instance from a persisted JSON payload."""

        return cls.model_validate(payload)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""

        return self.model_dump(mode="json")


@dataclass(slots=True)
class EventEnvelope:
    """Envelope for persisted events with metadata required by the store."""

    aggregate_id: str
    aggregate_type: str
    version: int
    event_type: str
    payload: DomainEvent
    metadata: Mapping[str, Any]
    correlation_id: str | None
    causation_id: str | None
    stored_at: datetime


@dataclass(slots=True)
class AggregateSnapshot:
    """Snapshot container persisted for faster aggregate hydration."""

    aggregate_id: str
    aggregate_type: str
    version: int
    state: Mapping[str, Any]
    taken_at: datetime


class Projection(Protocol):
    """Projection protocol for rebuilding read models."""

    name: str

    def interested_in(self) -> set[str] | None:
        """Return the set of event types this projection cares about."""

    def reset(self, session: Session) -> None:
        """Clear or truncate read models prior to rebuild."""

    def project(self, envelope: EventEnvelope, session: Session) -> None:
        """Apply a single event to the projection within the provided session."""


# ---------------------------------------------------------------------------
# Aggregate roots base class
# ---------------------------------------------------------------------------


class AggregateRoot:
    """Base class implementing change tracking for aggregates."""

    aggregate_type: ClassVar[str]

    def __init__(self, aggregate_id: str, *, version: int = 0) -> None:
        if not getattr(self, "aggregate_type", None):
            raise ValueError("Aggregate subclasses must define 'aggregate_type'")
        self.id = aggregate_id
        self.version = version
        self._pending_events: list[DomainEvent] = []

    # Public API -----------------------------------------------------------------

    def load_from_history(self, events: Iterable[DomainEvent]) -> None:
        """Rehydrate aggregate state from historic events."""

        for event in events:
            self._apply(event, is_new=False)

    def get_pending_events(self) -> list[DomainEvent]:
        """Return all uncommitted events raised since instantiation."""

        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        """Clear pending events post persistence."""

        self._pending_events.clear()

    # Snapshot support ------------------------------------------------------------

    def snapshot_state(self) -> Mapping[str, Any]:  # pragma: no cover - interface
        """Return serialisable state for snapshotting."""

        raise NotImplementedError

    def load_snapshot(self, state: Mapping[str, Any]) -> None:  # pragma: no cover
        """Restore aggregate state from a snapshot payload."""

        raise NotImplementedError

    # Internal helpers ------------------------------------------------------------

    def _raise_event(self, event: DomainEvent) -> None:
        self._apply(event, is_new=True)
        self._pending_events.append(event)

    def _apply(self, event: DomainEvent, *, is_new: bool) -> None:
        handler_name = f"_apply_{event.event_name}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            raise AttributeError(
                f"Aggregate '{self.aggregate_type}' missing handler for event '{event.event_name}'"
            )
        handler(event)
        if is_new:
            self.version += 1
        else:
            # For historic events the version is managed externally by the store.
            self.version = max(
                self.version, getattr(event, "stream_version", self.version)
            )


# ---------------------------------------------------------------------------
# Order aggregate and events
# ---------------------------------------------------------------------------


class OrderCreated(DomainEvent):
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float | None = None
    order_type: OrderType


class OrderSubmitted(DomainEvent):
    order_id: str
    venue_order_id: str


class OrderFilled(DomainEvent):
    order_id: str
    fill_quantity: float
    fill_price: float
    cumulative_quantity: float
    average_price: float
    status: OrderStatus


class OrderCancelled(DomainEvent):
    order_id: str
    reason: str | None = None


class OrderRejected(DomainEvent):
    order_id: str
    reason: str | None = None


class OrderAggregate(AggregateRoot):
    aggregate_type = "order"

    def __init__(self, aggregate_id: str, *, version: int = 0) -> None:
        super().__init__(aggregate_id, version=version)
        self.symbol: str | None = None
        self.side: OrderSide | None = None
        self.quantity: float = 0.0
        self.price: float | None = None
        self.order_type: OrderType | None = None
        self.status: OrderStatus = OrderStatus.PENDING
        self.average_price: float | None = None
        self.filled_quantity: float = 0.0
        self.venue_order_id: str | None = None
        self.rejection_reason: str | None = None

    # Aggregate behaviour --------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float | None,
        order_type: OrderType,
    ) -> "OrderAggregate":
        aggregate = cls(order_id)
        aggregate._raise_event(
            OrderCreated(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
            )
        )
        return aggregate

    def mark_submitted(self, venue_order_id: str) -> None:
        if self.status not in {OrderStatus.PENDING, OrderStatus.OPEN}:
            raise ValueError(f"Cannot submit order in status {self.status}")
        self._raise_event(
            OrderSubmitted(order_id=self.id, venue_order_id=venue_order_id)
        )

    def record_fill(self, *, quantity: float, price: float) -> None:
        if quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        new_total = self.filled_quantity + quantity
        if new_total - self.quantity > 1e-9:
            raise ValueError("Fill quantity exceeds order size")
        if price <= 0:
            raise ValueError("Fill price must be positive")

        if self.average_price is None:
            avg_price = price
        else:
            avg_price = (
                self.average_price * self.filled_quantity + price * quantity
            ) / new_total

        status = (
            OrderStatus.FILLED
            if abs(new_total - self.quantity) < 1e-9
            else OrderStatus.PARTIALLY_FILLED
        )
        self._raise_event(
            OrderFilled(
                order_id=self.id,
                fill_quantity=quantity,
                fill_price=price,
                cumulative_quantity=new_total,
                average_price=avg_price,
                status=status,
            )
        )

    def cancel(self, reason: str | None = None) -> None:
        if self.status in {OrderStatus.CANCELLED, OrderStatus.FILLED}:
            return
        self._raise_event(OrderCancelled(order_id=self.id, reason=reason))

    def reject(self, reason: str | None = None) -> None:
        if self.status is OrderStatus.FILLED:
            raise ValueError("Cannot reject a filled order")
        self._raise_event(OrderRejected(order_id=self.id, reason=reason))

    # Event handlers -------------------------------------------------------------

    def _apply_OrderCreated(self, event: OrderCreated) -> None:
        self.symbol = event.symbol
        self.side = event.side
        self.quantity = event.quantity
        self.price = event.price
        self.order_type = event.order_type
        self.status = OrderStatus.PENDING

    def _apply_OrderSubmitted(self, event: OrderSubmitted) -> None:
        self.status = OrderStatus.OPEN
        self.venue_order_id = event.venue_order_id

    def _apply_OrderFilled(self, event: OrderFilled) -> None:
        self.status = event.status
        self.filled_quantity = event.cumulative_quantity
        self.average_price = event.average_price

    def _apply_OrderCancelled(self, event: OrderCancelled) -> None:
        self.status = OrderStatus.CANCELLED

    def _apply_OrderRejected(self, event: OrderRejected) -> None:
        self.status = OrderStatus.REJECTED
        self.rejection_reason = event.reason

    # Snapshot support -----------------------------------------------------------

    def snapshot_state(self) -> Mapping[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value if self.side else None,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type.value if self.order_type else None,
            "status": self.status.value,
            "average_price": self.average_price,
            "filled_quantity": self.filled_quantity,
            "venue_order_id": self.venue_order_id,
            "rejection_reason": self.rejection_reason,
        }

    def load_snapshot(self, state: Mapping[str, Any]) -> None:
        self.symbol = state.get("symbol")
        self.side = OrderSide(state["side"]) if state.get("side") else None
        self.quantity = float(state.get("quantity", 0.0))
        self.price = state.get("price")
        self.order_type = (
            OrderType(state["order_type"]) if state.get("order_type") else None
        )
        self.status = OrderStatus(state.get("status", OrderStatus.PENDING.value))
        self.average_price = state.get("average_price")
        self.filled_quantity = float(state.get("filled_quantity", 0.0))
        self.venue_order_id = state.get("venue_order_id")
        self.rejection_reason = state.get("rejection_reason")


# ---------------------------------------------------------------------------
# Position aggregate and events
# ---------------------------------------------------------------------------


class PositionOpened(DomainEvent):
    position_id: str
    symbol: str
    quantity: float
    average_price: float


class PositionAdjusted(DomainEvent):
    position_id: str
    delta_quantity: float
    execution_price: float
    new_quantity: float
    new_average_price: float


class PositionClosed(DomainEvent):
    position_id: str
    closing_price: float
    realised_pnl: float


class PositionAggregate(AggregateRoot):
    aggregate_type = "position"

    def __init__(self, aggregate_id: str, *, version: int = 0) -> None:
        super().__init__(aggregate_id, version=version)
        self.symbol: str | None = None
        self.quantity: float = 0.0
        self.average_price: float = 0.0
        self.realised_pnl: float = 0.0
        self.is_closed: bool = False

    @classmethod
    def open(
        cls, *, position_id: str, symbol: str, quantity: float, average_price: float
    ) -> "PositionAggregate":
        if quantity == 0:
            raise ValueError("Position quantity must be non-zero on open")
        if average_price <= 0:
            raise ValueError("Average price must be positive")
        aggregate = cls(position_id)
        aggregate._raise_event(
            PositionOpened(
                position_id=position_id,
                symbol=symbol,
                quantity=quantity,
                average_price=average_price,
            )
        )
        return aggregate

    def adjust(self, *, delta_quantity: float, execution_price: float) -> None:
        if self.is_closed:
            raise ValueError("Cannot adjust a closed position")
        new_quantity = self.quantity + delta_quantity
        if execution_price <= 0:
            raise ValueError("Execution price must be positive")

        if new_quantity == 0:
            new_average_price = 0.0
        else:
            notional_existing = self.average_price * self.quantity
            notional_delta = execution_price * delta_quantity
            new_average_price = (notional_existing + notional_delta) / new_quantity

        self._raise_event(
            PositionAdjusted(
                position_id=self.id,
                delta_quantity=delta_quantity,
                execution_price=execution_price,
                new_quantity=new_quantity,
                new_average_price=new_average_price,
            )
        )

    def close(self, *, closing_price: float) -> None:
        if self.is_closed:
            return
        if closing_price <= 0:
            raise ValueError("Closing price must be positive")
        realised_pnl = (closing_price - self.average_price) * self.quantity
        self._raise_event(
            PositionClosed(
                position_id=self.id,
                closing_price=closing_price,
                realised_pnl=realised_pnl,
            )
        )

    # Event handlers -------------------------------------------------------------

    def _apply_PositionOpened(self, event: PositionOpened) -> None:
        self.symbol = event.symbol
        self.quantity = event.quantity
        self.average_price = event.average_price
        self.is_closed = False

    def _apply_PositionAdjusted(self, event: PositionAdjusted) -> None:
        self.quantity = event.new_quantity
        self.average_price = event.new_average_price
        if self.quantity == 0:
            self.is_closed = True

    def _apply_PositionClosed(self, event: PositionClosed) -> None:
        self.is_closed = True
        self.realised_pnl += event.realised_pnl
        self.quantity = 0.0

    # Snapshot support -----------------------------------------------------------

    def snapshot_state(self) -> Mapping[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "realised_pnl": self.realised_pnl,
            "is_closed": self.is_closed,
        }

    def load_snapshot(self, state: Mapping[str, Any]) -> None:
        self.symbol = state.get("symbol")
        self.quantity = float(state.get("quantity", 0.0))
        self.average_price = float(state.get("average_price", 0.0))
        self.realised_pnl = float(state.get("realised_pnl", 0.0))
        self.is_closed = bool(state.get("is_closed", False))


# ---------------------------------------------------------------------------
# Portfolio aggregate and events
# ---------------------------------------------------------------------------


class PortfolioCreated(DomainEvent):
    portfolio_id: str
    base_currency: str


class CashDeposited(DomainEvent):
    portfolio_id: str
    amount: float


class CashWithdrawn(DomainEvent):
    portfolio_id: str
    amount: float


class PositionLinked(DomainEvent):
    portfolio_id: str
    position_id: str
    symbol: str
    quantity: float


class PnLRealized(DomainEvent):
    portfolio_id: str
    position_id: str
    realised_pnl: float


class ExposureUpdated(DomainEvent):
    portfolio_id: str
    exposures: Dict[str, float]


class PortfolioAggregate(AggregateRoot):
    aggregate_type = "portfolio"

    def __init__(self, aggregate_id: str, *, version: int = 0) -> None:
        super().__init__(aggregate_id, version=version)
        self.base_currency: str | None = None
        self.cash_balance: float = 0.0
        self.positions: MutableMapping[str, dict[str, Any]] = {}
        self.realised_pnl: float = 0.0
        self.exposures: MutableMapping[str, float] = {}

    @classmethod
    def create(cls, *, portfolio_id: str, base_currency: str) -> "PortfolioAggregate":
        aggregate = cls(portfolio_id)
        aggregate._raise_event(
            PortfolioCreated(portfolio_id=portfolio_id, base_currency=base_currency)
        )
        return aggregate

    def deposit_cash(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self._raise_event(CashDeposited(portfolio_id=self.id, amount=amount))

    def withdraw_cash(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self.cash_balance - amount < -1e-9:
            raise ValueError("Insufficient cash for withdrawal")
        self._raise_event(CashWithdrawn(portfolio_id=self.id, amount=amount))

    def link_position(self, position_id: str, symbol: str, quantity: float) -> None:
        self._raise_event(
            PositionLinked(
                portfolio_id=self.id,
                position_id=position_id,
                symbol=symbol,
                quantity=quantity,
            )
        )

    def realise_pnl(self, position_id: str, realised_pnl: float) -> None:
        self._raise_event(
            PnLRealized(
                portfolio_id=self.id, position_id=position_id, realised_pnl=realised_pnl
            )
        )

    def update_exposure(self, exposures: Mapping[str, float]) -> None:
        self._raise_event(
            ExposureUpdated(portfolio_id=self.id, exposures=dict(exposures))
        )

    # Event handlers -------------------------------------------------------------

    def _apply_PortfolioCreated(self, event: PortfolioCreated) -> None:
        self.base_currency = event.base_currency

    def _apply_CashDeposited(self, event: CashDeposited) -> None:
        self.cash_balance += event.amount

    def _apply_CashWithdrawn(self, event: CashWithdrawn) -> None:
        self.cash_balance -= event.amount

    def _apply_PositionLinked(self, event: PositionLinked) -> None:
        self.positions[event.position_id] = {
            "symbol": event.symbol,
            "quantity": event.quantity,
        }

    def _apply_PnLRealized(self, event: PnLRealized) -> None:
        self.realised_pnl += event.realised_pnl

    def _apply_ExposureUpdated(self, event: ExposureUpdated) -> None:
        self.exposures.update(event.exposures)

    # Snapshot support -----------------------------------------------------------

    def snapshot_state(self) -> Mapping[str, Any]:
        return {
            "base_currency": self.base_currency,
            "cash_balance": self.cash_balance,
            "positions": json.loads(json.dumps(self.positions)),
            "realised_pnl": self.realised_pnl,
            "exposures": dict(self.exposures),
        }

    def load_snapshot(self, state: Mapping[str, Any]) -> None:
        self.base_currency = state.get("base_currency")
        self.cash_balance = float(state.get("cash_balance", 0.0))
        self.positions = dict(state.get("positions", {}))
        self.realised_pnl = float(state.get("realised_pnl", 0.0))
        self.exposures = dict(state.get("exposures", {}))


# ---------------------------------------------------------------------------
# Event Store implementation (PostgreSQL JSONB backed)
# ---------------------------------------------------------------------------


class ConcurrencyError(RuntimeError):
    """Raised when optimistic concurrency expectations are violated."""


class PostgresEventStore:
    """Event store persisting events and snapshots in PostgreSQL."""

    def __init__(
        self, engine: Engine, *, schema: str = "public", table_prefix: str = "es_"
    ) -> None:
        self._engine = engine
        self._schema = schema
        self._metadata = MetaData(schema=schema)
        self._events = self._create_events_table(table_prefix)
        self._snapshots = self._create_snapshots_table(table_prefix)
        self._session_factory = sessionmaker(
            bind=engine, expire_on_commit=False, future=True
        )

    # Table definitions ---------------------------------------------------------

    def _create_events_table(self, prefix: str) -> Table:
        return Table(
            f"{prefix}events",
            self._metadata,
            Column("id", BigInteger, primary_key=True, autoincrement=True),
            Column("event_id", String(36), nullable=False, unique=True),
            Column("aggregate_id", String(255), nullable=False),
            Column("aggregate_type", String(64), nullable=False),
            Column("version", Integer, nullable=False),
            Column("event_type", String(128), nullable=False),
            Column("correlation_id", String(64), nullable=True),
            Column("causation_id", String(64), nullable=True),
            Column(
                "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
            ),
            Column("payload", JSONB, nullable=False),
            Column("occurred_at", DateTime(timezone=True), nullable=False),
            Column(
                "recorded_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=func.now(),
            ),
            UniqueConstraint(
                "aggregate_id",
                "aggregate_type",
                "version",
                name="uq_event_stream_version",
            ),
            Index("ix_event_store_stream", "aggregate_type", "aggregate_id"),
        )

    def _create_snapshots_table(self, prefix: str) -> Table:
        return Table(
            f"{prefix}snapshots",
            self._metadata,
            Column("id", BigInteger, primary_key=True, autoincrement=True),
            Column("aggregate_id", String(255), nullable=False),
            Column("aggregate_type", String(64), nullable=False),
            Column("version", Integer, nullable=False),
            Column("state", JSONB, nullable=False),
            Column(
                "taken_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=func.now(),
            ),
            UniqueConstraint(
                "aggregate_id", "aggregate_type", name="uq_snapshot_latest"
            ),
            CheckConstraint("version >= 0", name="ck_snapshot_version_non_negative"),
        )

    # Engine helpers ------------------------------------------------------------

    def create_schema(self) -> None:
        """Create backing tables if they do not already exist."""

        with self._engine.begin() as connection:
            self._metadata.create_all(connection)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Event operations ----------------------------------------------------------

    def append(
        self,
        *,
        aggregate: AggregateRoot,
        events: Iterable[DomainEvent],
        expected_version: int | None,
        metadata: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> int:
        """Persist events for an aggregate applying optimistic concurrency."""

        metadata_payload = dict(metadata or {})
        with self._session() as session:
            current_version = self._current_stream_version(
                session, aggregate.id, aggregate.aggregate_type
            )
            if expected_version is not None and current_version != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version} but stream is at {current_version}"
                )

            version = current_version
            for event in events:
                version += 1
                payload = event.to_dict()
                event_name = event.event_name
                insert_stmt = self._events.insert().values(
                    event_id=str(event.event_id),
                    aggregate_id=aggregate.id,
                    aggregate_type=aggregate.aggregate_type,
                    version=version,
                    event_type=event_name,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    metadata=metadata_payload,
                    payload=payload,
                    occurred_at=event.occurred_at,
                )
                try:
                    session.execute(insert_stmt)
                except IntegrityError as exc:  # pragma: no cover - requires DB
                    raise ConcurrencyError("Event insert violated constraints") from exc
            return version

    def load_stream(
        self,
        *,
        aggregate_id: str,
        aggregate_type: str,
        since_version: int = 0,
    ) -> list[EventEnvelope]:
        """Load events for a stream ordered by version."""

        with self._session() as session:
            stmt = (
                select(self._events)
                .where(
                    and_(
                        self._events.c.aggregate_id == aggregate_id,
                        self._events.c.aggregate_type == aggregate_type,
                        self._events.c.version > since_version,
                    )
                )
                .order_by(self._events.c.version.asc())
            )
            rows = session.execute(stmt).all()
        envelopes: list[EventEnvelope] = []
        for row in rows:
            payload = self._hydrate_event(row.payload, row.event_type)
            payload.stream_version = row.version
            envelopes.append(
                EventEnvelope(
                    aggregate_id=row.aggregate_id,
                    aggregate_type=row.aggregate_type,
                    version=row.version,
                    event_type=row.event_type,
                    payload=payload,
                    metadata=row.metadata,
                    correlation_id=row.correlation_id,
                    causation_id=row.causation_id,
                    stored_at=row.recorded_at,
                )
            )
        return envelopes

    def iterate_all_events(
        self, *, chunk_size: int = 1000
    ) -> Iterator[list[EventEnvelope]]:
        """Yield envelopes for all events in batches for projection rebuilds."""

        with self._session() as session:
            last_id = 0
            while True:
                stmt = (
                    select(self._events)
                    .where(self._events.c.id > last_id)
                    .order_by(self._events.c.id.asc())
                    .limit(chunk_size)
                )
                rows = session.execute(stmt).all()
                if not rows:
                    break
                envelopes: list[EventEnvelope] = []
                for row in rows:
                    payload = self._hydrate_event(row.payload, row.event_type)
                    payload.stream_version = row.version
                    envelopes.append(
                        EventEnvelope(
                            aggregate_id=row.aggregate_id,
                            aggregate_type=row.aggregate_type,
                            version=row.version,
                            event_type=row.event_type,
                            payload=payload,
                            metadata=row.metadata,
                            correlation_id=row.correlation_id,
                            causation_id=row.causation_id,
                            stored_at=row.recorded_at,
                        )
                    )
                    last_id = row.id
                yield envelopes

    def _current_stream_version(
        self, session: Session, aggregate_id: str, aggregate_type: str
    ) -> int:
        stmt = select(func.max(self._events.c.version)).where(
            and_(
                self._events.c.aggregate_id == aggregate_id,
                self._events.c.aggregate_type == aggregate_type,
            )
        )
        version = session.execute(stmt).scalar_one_or_none()
        return int(version or 0)

    def _hydrate_event(
        self, payload: Mapping[str, Any], event_type: str
    ) -> DomainEvent:
        model_cls = _EVENT_REGISTRY.get(event_type)
        if model_cls is None:
            raise KeyError(
                f"Unknown event type '{event_type}' encountered during hydration"
            )
        return model_cls.from_dict(payload)

    # Snapshot support -----------------------------------------------------------

    def store_snapshot(self, snapshot: AggregateSnapshot) -> None:
        """Upsert a snapshot for an aggregate."""

        with self._session() as session:
            upsert = (
                insert(self._snapshots)
                .values(
                    aggregate_id=snapshot.aggregate_id,
                    aggregate_type=snapshot.aggregate_type,
                    version=snapshot.version,
                    state=snapshot.state,
                    taken_at=snapshot.taken_at,
                )
                .on_conflict_do_update(
                    index_elements=[
                        self._snapshots.c.aggregate_id,
                        self._snapshots.c.aggregate_type,
                    ],
                    set_={
                        "version": snapshot.version,
                        "state": snapshot.state,
                        "taken_at": snapshot.taken_at,
                    },
                )
            )
            session.execute(upsert)

    def load_latest_snapshot(
        self, *, aggregate_id: str, aggregate_type: str
    ) -> AggregateSnapshot | None:
        with self._session() as session:
            stmt = (
                select(self._snapshots)
                .where(
                    and_(
                        self._snapshots.c.aggregate_id == aggregate_id,
                        self._snapshots.c.aggregate_type == aggregate_type,
                    )
                )
                .order_by(self._snapshots.c.version.desc())
                .limit(1)
            )
            row = session.execute(stmt).first()
            if row is None:
                return None
            return AggregateSnapshot(
                aggregate_id=row.aggregate_id,
                aggregate_type=row.aggregate_type,
                version=row.version,
                state=row.state,
                taken_at=row.taken_at,
            )


# ---------------------------------------------------------------------------
# Event replay utilities
# ---------------------------------------------------------------------------


class EventReplay:
    """Helpers to replay streams for debugging or diagnostics."""

    def __init__(self, store: PostgresEventStore) -> None:
        self._store = store

    def rehydrate(
        self, aggregate_cls: type[AggregateRoot], aggregate_id: str
    ) -> AggregateRoot:
        aggregate = aggregate_cls(aggregate_id)
        snapshot = self._store.load_latest_snapshot(
            aggregate_id=aggregate_id, aggregate_type=aggregate.aggregate_type
        )
        if snapshot:
            aggregate.load_snapshot(snapshot.state)
            since_version = snapshot.version
        else:
            since_version = 0

        envelopes = self._store.load_stream(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate.aggregate_type,
            since_version=since_version,
        )
        aggregate.load_from_history([envelope.payload for envelope in envelopes])
        return aggregate

    def print_timeline(
        self, aggregate_cls: type[AggregateRoot], aggregate_id: str
    ) -> list[str]:
        aggregate = aggregate_cls(aggregate_id)
        envelopes = self._store.load_stream(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate.aggregate_type,
            since_version=0,
        )
        timeline: list[str] = []
        for envelope in envelopes:
            payload_repr = json.dumps(envelope.payload.to_dict(), default=str)
            timeline_entry = (
                f"{envelope.stored_at.isoformat()} | v{envelope.version} | "
                f"{envelope.event_type} | {payload_repr}"
            )
            timeline.append(timeline_entry)
        return timeline


# ---------------------------------------------------------------------------
# Projection rebuilding
# ---------------------------------------------------------------------------


class ProjectionRebuilder:
    """Stream-through rebuild helper for projections backed by PostgreSQL."""

    def __init__(self, store: PostgresEventStore) -> None:
        self._store = store

    def rebuild(self, projection: Projection, *, chunk_size: int = 1000) -> None:
        LOGGER.info("Rebuilding projection '%s'", projection.name)
        with self._store._session() as session:  # pylint: disable=protected-access
            projection.reset(session)
            interested = projection.interested_in()
            for batch in self._store.iterate_all_events(chunk_size=chunk_size):
                for envelope in batch:
                    if interested is None or envelope.event_type in interested:
                        projection.project(envelope, session)
            session.commit()
        LOGGER.info("Projection '%s' rebuild completed", projection.name)


# ---------------------------------------------------------------------------
# Materialized view helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MaterializedView:
    """Represents a read model backed by a PostgreSQL materialized view."""

    name: str
    definition_sql: str
    refresh_concurrently: bool = True
    with_data: bool = True


class MaterializedViewManager:
    """Utility to create and refresh materialized view based read models."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_exists(self, view: MaterializedView) -> None:
        """Create the materialized view if it is absent."""

        create_sql = "CREATE MATERIALIZED VIEW IF NOT EXISTS {name} AS {definition} {with_data}".format(
            name=view.name,
            definition=view.definition_sql,
            with_data="WITH DATA" if view.with_data else "WITH NO DATA",
        )
        with self._engine.begin() as connection:
            connection.execute(text(create_sql))

    def refresh(self, view: MaterializedView) -> None:
        """Refresh the materialized view, optionally concurrently."""

        if view.refresh_concurrently:
            refresh_sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view.name}"
        else:
            refresh_sql = f"REFRESH MATERIALIZED VIEW {view.name}"
        with self._engine.begin() as connection:
            connection.execute(text(refresh_sql))


# ---------------------------------------------------------------------------
# Utility functions for snapshots
# ---------------------------------------------------------------------------


def take_snapshot(aggregate: AggregateRoot) -> AggregateSnapshot:
    """Capture the aggregate state in a snapshot envelope."""

    return AggregateSnapshot(
        aggregate_id=aggregate.id,
        aggregate_type=aggregate.aggregate_type,
        version=aggregate.version,
        state=dict(aggregate.snapshot_state()),
        taken_at=datetime.now(UTC),
    )


def restore_from_snapshot(
    aggregate_cls: type[AggregateRoot], snapshot: AggregateSnapshot
) -> AggregateRoot:
    """Instantiate aggregate from snapshot without accessing the event store."""

    aggregate = aggregate_cls(snapshot.aggregate_id, version=snapshot.version)
    aggregate.load_snapshot(snapshot.state)
    return aggregate
