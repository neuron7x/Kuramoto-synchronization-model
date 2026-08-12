# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Event Admission Gate — Phase 2 extension of Sprint-2 validation.

The Sprint-2 commit landed a single-barrier ``EventValidator`` Protocol.
The remediation protocol calls for **four** barriers, each with a
machine-readable reject code so that downstream incident response can
reason about *why* a write was refused:

    B1. Structural     — event schema / required fields / types.
    B2. Causal         — the transition from (aggregate_state → event)
                         exists in the aggregate's declared graph.
    B3. State          — the event is consistent with the live
                         aggregate state (remaining quantity, cash
                         balance, etc.).
    B4. Invariant      — domain rules that cannot be bypassed (signed
                         quantity bounds, exposure ceilings).

Barriers run in ``B1 → B2 → B3 → B4`` order; the first rejection wins.
A rejection carries a structured ``RejectCode`` and the id of the
specific invariant that triggered it, so an audit consumer can answer
"why was this event refused" without parsing free-form text.

Contracts
---------
A-1  Each barrier is a stateless callable.
A-2  ``AdmissionGate.verdict(event, aggregate)`` runs all four barriers
     and returns exactly one of ``ACCEPT`` / ``REJECT(code, reason,
     invariant_id)``.
A-3  The gate never mutates the aggregate, the event, or any global
     state. A rejection is surfaced to the caller as an exception only
     at the persistence boundary — the gate itself returns a verdict.
A-4  ``AggregateTransitionRegistry`` enumerates the allowed
     ``(aggregate_type, current_state_predicate, event_type)`` triples.
     An event whose triple is absent is rejected by B2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

from core.events.validation import (
    EventValidator,
    OrderEventValidator,
    PortfolioEventValidator,
    ValidationResult,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from core.events.sourcing import AggregateRoot, DomainEvent

__all__ = [
    "AdmissionGate",
    "AdmissionVerdict",
    "AggregateTransitionRegistry",
    "Barrier",
    "RejectCode",
    "default_gate",
]


class RejectCode(str, Enum):
    """Machine-readable reject reasons.

    ``str`` base class makes the value trivially serialisable into
    JSON / JSONB without a custom encoder.
    """

    STRUCTURAL_INVALID = "E_STRUCTURAL_INVALID"
    TRANSITION_UNKNOWN = "E_TRANSITION_UNKNOWN"
    STATE_INCONSISTENT = "E_STATE_INCONSISTENT"
    INVARIANT_VIOLATED = "E_INVARIANT_VIOLATED"


class Barrier(str, Enum):
    """Identifies which barrier produced a rejection."""

    STRUCTURAL = "B1_STRUCTURAL"
    CAUSAL = "B2_CAUSAL"
    STATE = "B3_STATE"
    INVARIANT = "B4_INVARIANT"


@dataclass(frozen=True)
class AdmissionVerdict:
    """Single output of ``AdmissionGate.verdict``.

    ``accepted=True`` is always paired with ``barrier=None`` and
    ``code=None``. A rejection carries the triggering barrier, a
    machine-readable code, a human-readable reason, and the id of the
    invariant that failed (e.g. ``"ORDER_FILL_REMAINING"``).
    """

    accepted: bool
    barrier: Barrier | None = None
    code: RejectCode | None = None
    reason: str | None = None
    invariant_id: str | None = None

    @classmethod
    def accept(cls) -> AdmissionVerdict:
        return cls(accepted=True)

    @classmethod
    def reject(
        cls,
        barrier: Barrier,
        code: RejectCode,
        reason: str,
        invariant_id: str,
    ) -> AdmissionVerdict:
        if not reason:
            raise ValueError("reject reason must be non-empty")
        if not invariant_id:
            raise ValueError("invariant_id must be non-empty")
        return cls(
            accepted=False,
            barrier=barrier,
            code=code,
            reason=reason,
            invariant_id=invariant_id,
        )


# ---------------------------------------------------------------------------
# Aggregate transition registry (Barrier B2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Transition:
    aggregate_type: str
    event_type: str
    predicate: Callable[["AggregateRoot"], bool]
    invariant_id: str


class AggregateTransitionRegistry:
    """Declared ``(aggregate_type, event_type, predicate)`` triples.

    A registry-aware gate rejects any event whose ``event_type`` is
    absent for the aggregate's current state under the declared
    predicate. The predicate defaults to "always" so that registries
    can be grown incrementally — a newly-recorded transition that does
    not yet have a predicate is still permitted, but it is now *listed*
    and can be tightened.
    """

    def __init__(self) -> None:
        self._transitions: dict[tuple[str, str], _Transition] = {}

    def register(
        self,
        *,
        aggregate_type: str,
        event_type: str,
        invariant_id: str,
        predicate: Callable[["AggregateRoot"], bool] | None = None,
    ) -> None:
        key = (aggregate_type, event_type)
        if key in self._transitions:
            raise ValueError(f"transition already registered: {key}")
        self._transitions[key] = _Transition(
            aggregate_type=aggregate_type,
            event_type=event_type,
            predicate=predicate if predicate is not None else (lambda _agg: True),
            invariant_id=invariant_id,
        )

    def verify(
        self,
        aggregate_type: str,
        event_type: str,
        aggregate: "AggregateRoot",
    ) -> AdmissionVerdict:
        key = (aggregate_type, event_type)
        transition = self._transitions.get(key)
        if transition is None:
            return AdmissionVerdict.reject(
                barrier=Barrier.CAUSAL,
                code=RejectCode.TRANSITION_UNKNOWN,
                reason=(
                    f"transition {aggregate_type}::{event_type} is not in the "
                    "registry; declare it before writing"
                ),
                invariant_id=f"TRANSITION_{aggregate_type}_{event_type}",
            )
        if not transition.predicate(aggregate):
            return AdmissionVerdict.reject(
                barrier=Barrier.CAUSAL,
                code=RejectCode.TRANSITION_UNKNOWN,
                reason=(
                    f"transition {aggregate_type}::{event_type} is not "
                    "permitted from the current aggregate state"
                ),
                invariant_id=transition.invariant_id,
            )
        return AdmissionVerdict.accept()


# ---------------------------------------------------------------------------
# Full four-barrier gate
# ---------------------------------------------------------------------------


class AdmissionGate:
    """Runs B1 → B2 → B3 → B4, first rejection wins.

    Barriers 1 and 3–4 delegate to the Sprint-2 Pydantic validators (B1
    is the pydantic model validation that already happens in
    ``DomainEvent.__init__``, effectively — the gate re-checks the
    declarative schema one more time via the validator's contract on a
    constructed event). Barrier 2 consults an
    ``AggregateTransitionRegistry``.
    """

    def __init__(
        self,
        registry: AggregateTransitionRegistry,
        semantic_validators: tuple[EventValidator, ...],
    ) -> None:
        self._registry = registry
        self._validators: tuple[EventValidator, ...] = tuple(semantic_validators)

    def verdict(
        self,
        event: "DomainEvent",
        aggregate: "AggregateRoot",
    ) -> AdmissionVerdict:
        # B1 STRUCTURAL — re-run the pydantic model_validate so that a
        # hand-crafted ``DomainEvent`` with post-init field poisoning
        # still gets caught at the gate.
        try:
            event.model_validate(event.model_dump(mode="json"))
        except Exception as exc:
            return AdmissionVerdict.reject(
                barrier=Barrier.STRUCTURAL,
                code=RejectCode.STRUCTURAL_INVALID,
                reason=f"schema violation: {exc}",
                invariant_id=f"SCHEMA_{type(event).__name__}",
            )

        # B2 CAUSAL — the transition must be declared.
        causal = self._registry.verify(aggregate.aggregate_type, event.event_name, aggregate)
        if not causal.accepted:
            return causal

        # B3 STATE + B4 INVARIANT — semantic validators. Each returns a
        # ``ValidationResult``; we map the first rejection to
        # ``STATE_INCONSISTENT`` unless the reason explicitly signals an
        # invariant breach (``invariant:`` prefix), in which case we
        # surface the INVARIANT_VIOLATED code.
        for validator in self._validators:
            result: ValidationResult = validator.validate(event, aggregate)
            if not result.valid:
                reason = result.reason or ""
                if reason.startswith("invariant:"):
                    return AdmissionVerdict.reject(
                        barrier=Barrier.INVARIANT,
                        code=RejectCode.INVARIANT_VIOLATED,
                        reason=reason[len("invariant:") :].strip(),
                        invariant_id=f"INVARIANT_{type(event).__name__}",
                    )
                return AdmissionVerdict.reject(
                    barrier=Barrier.STATE,
                    code=RejectCode.STATE_INCONSISTENT,
                    reason=reason,
                    invariant_id=f"STATE_{type(event).__name__}",
                )

        return AdmissionVerdict.accept()


# ---------------------------------------------------------------------------
# Canonical factory: a gate populated with the built-in validators
# and the minimum transition registry.
# ---------------------------------------------------------------------------


def _build_default_registry() -> AggregateTransitionRegistry:
    registry = AggregateTransitionRegistry()
    # ---- order aggregate ----
    for event_type, invariant_id in [
        ("OrderCreated", "ORDER_CREATE"),
        ("OrderSubmitted", "ORDER_SUBMIT"),
        ("OrderFilled", "ORDER_FILL"),
        ("OrderCancelled", "ORDER_CANCEL"),
        ("OrderRejected", "ORDER_REJECT"),
    ]:
        registry.register(
            aggregate_type="order",
            event_type=event_type,
            invariant_id=invariant_id,
        )
    # ---- position aggregate ----
    for event_type, invariant_id in [
        ("PositionOpened", "POSITION_OPEN"),
        ("PositionAdjusted", "POSITION_ADJUST"),
        ("PositionClosed", "POSITION_CLOSE"),
    ]:
        registry.register(
            aggregate_type="position",
            event_type=event_type,
            invariant_id=invariant_id,
        )
    # ---- portfolio aggregate ----
    for event_type, invariant_id in [
        ("PortfolioCreated", "PORTFOLIO_CREATE"),
        ("CashDeposited", "PORTFOLIO_DEPOSIT"),
        ("CashWithdrawn", "PORTFOLIO_WITHDRAW"),
        ("PositionLinked", "PORTFOLIO_LINK"),
        ("PnLRealized", "PORTFOLIO_PNL"),
        ("ExposureUpdated", "PORTFOLIO_EXPOSURE"),
    ]:
        registry.register(
            aggregate_type="portfolio",
            event_type=event_type,
            invariant_id=invariant_id,
        )
    return registry


def default_gate() -> AdmissionGate:
    """Canonical gate for the order/position/portfolio aggregates."""
    return AdmissionGate(
        registry=_build_default_registry(),
        semantic_validators=(
            OrderEventValidator(),
            PortfolioEventValidator(),
        ),
    )
