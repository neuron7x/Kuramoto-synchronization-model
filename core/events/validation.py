# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Semantic admission gate for the event store.

Sprint 2 of the remediation plan. Provides a thin ``EventValidator``
protocol invoked inside ``PostgresEventStore.append`` *before* the
insert lands. A validator rejects structurally valid events that would
produce a dead/invariant-violating aggregate state — for example, a
``OrderFilled`` whose ``fill_quantity`` exceeds ``remaining_quantity``,
or an ``ExposureUpdated`` carrying a negative exposure.

Design
------
* The protocol is pure-Python (no runtime dependencies on the DB). It
  operates on a freshly-hydrated ``AggregateState`` snapshot so the
  rule can reference both the incoming event and the current state.
* Validators compose: ``CompositeValidator`` applies a tuple of
  delegates in order, short-circuiting on the first rejection. This
  lets the store wire per-aggregate rules and cross-cutting rules
  (naming, size limits) without a combinatorial explosion.
* Rejections raise :class:`DomainValidationError` rather than
  returning a flag — the store's transactional scope is the correct
  place to roll back, so an exception is the idiomatic signal.

Contracts
---------
V-1  ``validate(event, state)`` is a pure function of its arguments;
     it never mutates the aggregate or writes to the event store.
V-2  ``ValidationResult.ok()`` and ``ValidationResult.rejected(reason)``
     are the only two constructors; the class is frozen.
V-3  A registered validator is called exactly once per incoming event.
V-4  A validator is free to raise a subclass of ``DomainValidationError``
     with richer information; the store surfaces the exception verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from core.events.sourcing import AggregateRoot, DomainEvent

__all__ = [
    "CompositeValidator",
    "DomainValidationError",
    "EventValidator",
    "OrderEventValidator",
    "PortfolioEventValidator",
    "ValidationResult",
]


class DomainValidationError(ValueError):
    """Raised when an event is rejected by semantic validation.

    Subclasses :class:`ValueError` so existing except-handlers that
    treat the store's admission failures uniformly keep working.
    """


@dataclass(frozen=True)
class ValidationResult:
    """Three-state verdict: valid / rejected-with-reason."""

    valid: bool
    reason: str | None = None

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True, reason=None)

    @classmethod
    def rejected(cls, reason: str) -> ValidationResult:
        if not reason:
            raise ValueError("rejection reason must be non-empty")
        return cls(valid=False, reason=reason)


@runtime_checkable
class EventValidator(Protocol):
    """Semantic admission gate invoked by :meth:`PostgresEventStore.append`.

    The validator receives the event to be written and the aggregate
    *before* any new pending events have been applied, so that rules
    referring to "remaining quantity" or "current exposure" see the
    authoritative state.
    """

    def validate(self, event: DomainEvent, aggregate: AggregateRoot) -> ValidationResult: ...


# ---------------------------------------------------------------------------
# Concrete validators
# ---------------------------------------------------------------------------


class OrderEventValidator:
    """Invariants for ``OrderAggregate``.

    * Fills must be positive and never exceed remaining quantity.
    * Fill price must be positive.
    * An already-filled or cancelled order cannot be re-submitted.
    """

    def validate(self, event: DomainEvent, aggregate: AggregateRoot) -> ValidationResult:
        from core.events.sourcing import (
            OrderAggregate,
            OrderCancelled,
            OrderCreated,
            OrderFilled,
            OrderRejected,
            OrderSubmitted,
        )
        from domain.order import OrderStatus, OrderType

        if not isinstance(aggregate, OrderAggregate):
            return ValidationResult.ok()

        if isinstance(event, OrderCreated):
            if event.quantity <= 0:
                return ValidationResult.rejected(
                    f"OrderCreated.quantity must be > 0, got {event.quantity}"
                )
            if event.order_type is OrderType.LIMIT:
                if event.price is None or event.price <= 0:
                    return ValidationResult.rejected(
                        f"LIMIT order requires positive price, got {event.price}"
                    )
            return ValidationResult.ok()

        if isinstance(event, OrderFilled):
            if event.fill_quantity <= 0:
                return ValidationResult.rejected(
                    f"OrderFilled.fill_quantity must be > 0, got {event.fill_quantity}"
                )
            if event.fill_price <= 0:
                return ValidationResult.rejected(
                    f"OrderFilled.fill_price must be > 0, got {event.fill_price}"
                )
            remaining = aggregate.quantity - aggregate.filled_quantity
            if event.fill_quantity - remaining > 1e-9:
                return ValidationResult.rejected(
                    f"fill {event.fill_quantity} exceeds remaining {remaining}"
                )
            return ValidationResult.ok()

        if isinstance(event, OrderSubmitted):
            if aggregate.status in {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }:
                return ValidationResult.rejected(
                    f"cannot submit order in terminal status {aggregate.status}"
                )
            return ValidationResult.ok()

        if isinstance(event, (OrderCancelled, OrderRejected)):
            return ValidationResult.ok()

        return ValidationResult.ok()


class PortfolioEventValidator:
    """Invariants for ``PortfolioAggregate``.

    * Exposures must be non-negative (a "short" exposure is modelled
      as a separate symbol; the value itself is a magnitude).
    * Cash withdrawals cannot exceed the current cash balance.
    * A position can only be linked to a portfolio once.
    """

    def validate(self, event: DomainEvent, aggregate: AggregateRoot) -> ValidationResult:
        from core.events.sourcing import (
            CashDeposited,
            CashWithdrawn,
            ExposureUpdated,
            PortfolioAggregate,
            PositionLinked,
        )

        if not isinstance(aggregate, PortfolioAggregate):
            return ValidationResult.ok()

        if isinstance(event, ExposureUpdated):
            for symbol, value in event.exposures.items():
                if value < 0:
                    return ValidationResult.rejected(f"negative exposure {symbol}={value}")
            return ValidationResult.ok()

        if isinstance(event, CashWithdrawn):
            if event.amount <= 0:
                return ValidationResult.rejected(
                    f"CashWithdrawn.amount must be > 0, got {event.amount}"
                )
            if aggregate.cash_balance - event.amount < -1e-9:
                return ValidationResult.rejected(
                    f"withdrawal {event.amount} exceeds balance {aggregate.cash_balance}"
                )
            return ValidationResult.ok()

        if isinstance(event, CashDeposited):
            if event.amount <= 0:
                return ValidationResult.rejected(
                    f"CashDeposited.amount must be > 0, got {event.amount}"
                )
            return ValidationResult.ok()

        if isinstance(event, PositionLinked):
            if event.position_id in aggregate.positions:
                return ValidationResult.rejected(f"position {event.position_id} already linked")
            return ValidationResult.ok()

        return ValidationResult.ok()


class CompositeValidator:
    """Apply several validators in order; first rejection wins."""

    __slots__ = ("_delegates",)

    def __init__(self, delegates: Iterable[EventValidator]) -> None:
        self._delegates: tuple[EventValidator, ...] = tuple(delegates)

    def validate(self, event: DomainEvent, aggregate: AggregateRoot) -> ValidationResult:
        for d in self._delegates:
            result = d.validate(event, aggregate)
            if not result.valid:
                return result
        return ValidationResult.ok()
