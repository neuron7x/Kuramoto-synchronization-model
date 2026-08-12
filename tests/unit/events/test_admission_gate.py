# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the four-barrier ``AdmissionGate`` — Phase 2 extension."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.events.admission import (
    AdmissionGate,
    AdmissionVerdict,
    AggregateTransitionRegistry,
    Barrier,
    RejectCode,
    default_gate,
)
from core.events.sourcing import (
    ExposureUpdated,
    OrderAggregate,
    OrderCreated,
    OrderFilled,
    PortfolioAggregate,
)
from core.events.validation import OrderEventValidator, PortfolioEventValidator
from domain.order import OrderSide, OrderStatus, OrderType

if TYPE_CHECKING:  # pragma: no cover
    from core.events.sourcing import AggregateRoot

# ---- Helpers ------------------------------------------------------------


def _fresh_order() -> OrderAggregate:
    agg = OrderAggregate.create(
        order_id="o-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10.0,
        price=150.0,
        order_type=OrderType.LIMIT,
    )
    agg.clear_pending_events()
    return agg


def _fresh_portfolio() -> PortfolioAggregate:
    agg = PortfolioAggregate.create(portfolio_id="p-1", base_currency="USD")
    agg.clear_pending_events()
    return agg


# ---- AdmissionVerdict basics --------------------------------------------


class TestAdmissionVerdictBasics:
    def test_accept_factory(self) -> None:
        v = AdmissionVerdict.accept()
        assert v.accepted is True
        assert v.code is None
        assert v.barrier is None

    def test_reject_requires_non_empty_reason(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            AdmissionVerdict.reject(
                barrier=Barrier.STATE,
                code=RejectCode.STATE_INCONSISTENT,
                reason="",
                invariant_id="X",
            )

    def test_reject_requires_invariant_id(self) -> None:
        with pytest.raises(ValueError, match="invariant_id"):
            AdmissionVerdict.reject(
                barrier=Barrier.STATE,
                code=RejectCode.STATE_INCONSISTENT,
                reason="bad",
                invariant_id="",
            )

    def test_verdict_is_frozen(self) -> None:
        v = AdmissionVerdict.accept()
        with pytest.raises(AttributeError):
            v.accepted = False  # type: ignore[misc]


# ---- AggregateTransitionRegistry ----------------------------------------


class TestRegistry:
    def test_registered_transition_passes(self) -> None:
        reg = AggregateTransitionRegistry()
        reg.register(
            aggregate_type="order",
            event_type="OrderCreated",
            invariant_id="INV-1",
        )
        assert reg.verify("order", "OrderCreated", _fresh_order()).accepted

    def test_unknown_transition_is_rejected_at_B2(self) -> None:
        reg = AggregateTransitionRegistry()
        v = reg.verify("order", "OrderCreated", _fresh_order())
        assert not v.accepted
        assert v.barrier is Barrier.CAUSAL
        assert v.code is RejectCode.TRANSITION_UNKNOWN

    def test_predicate_rejection_is_also_B2(self) -> None:
        reg = AggregateTransitionRegistry()

        def _not_terminal(agg: "AggregateRoot") -> bool:
            # Predicate sees AggregateRoot in the signature; narrow
            # back to OrderAggregate to consult ``status``.
            if not isinstance(agg, OrderAggregate):
                return True
            return agg.status not in {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }

        reg.register(
            aggregate_type="order",
            event_type="OrderSubmitted",
            invariant_id="ORDER_CANNOT_SUBMIT_TERMINAL",
            predicate=_not_terminal,
        )
        agg = _fresh_order()
        agg.status = OrderStatus.CANCELLED
        v = reg.verify("order", "OrderSubmitted", agg)
        assert not v.accepted
        assert v.barrier is Barrier.CAUSAL
        assert v.invariant_id == "ORDER_CANNOT_SUBMIT_TERMINAL"

    def test_double_registration_raises(self) -> None:
        reg = AggregateTransitionRegistry()
        reg.register(aggregate_type="order", event_type="X", invariant_id="A")
        with pytest.raises(ValueError, match="already registered"):
            reg.register(aggregate_type="order", event_type="X", invariant_id="B")


# ---- Full gate pipeline --------------------------------------------------


class TestAdmissionGatePipeline:
    def test_healthy_event_is_accepted(self) -> None:
        gate = default_gate()
        agg = _fresh_order()
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        verdict = gate.verdict(evt, agg)
        assert verdict.accepted

    def test_unknown_transition_rejected_before_state_barrier(self) -> None:
        """B2 fires before B3: an unregistered transition is rejected
        by CAUSAL even if its state would otherwise be consistent."""
        gate = AdmissionGate(
            registry=AggregateTransitionRegistry(),  # empty
            semantic_validators=(OrderEventValidator(),),
        )
        agg = _fresh_order()
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        v = gate.verdict(evt, agg)
        assert v.barrier is Barrier.CAUSAL
        assert v.code is RejectCode.TRANSITION_UNKNOWN

    def test_state_inconsistency_is_rejected_at_B3(self) -> None:
        gate = default_gate()
        agg = _fresh_order()
        # Overfill: remaining=10, fill=100.
        evt = OrderFilled(
            order_id="o-1",
            fill_quantity=100.0,
            fill_price=150.0,
            cumulative_quantity=100.0,
            average_price=150.0,
            status=OrderStatus.FILLED,
        )
        v = gate.verdict(evt, agg)
        assert not v.accepted
        assert v.barrier is Barrier.STATE
        assert v.code is RejectCode.STATE_INCONSISTENT
        assert "exceeds remaining" in (v.reason or "")

    def test_portfolio_negative_exposure_is_rejected_at_B3(self) -> None:
        gate = default_gate()
        agg = _fresh_portfolio()
        evt = ExposureUpdated(portfolio_id="p-1", exposures={"AAPL": -5.0})
        v = gate.verdict(evt, agg)
        assert not v.accepted
        assert v.barrier is Barrier.STATE
        assert "negative exposure" in (v.reason or "")

    def test_default_gate_is_runtime_checkable_registry(self) -> None:
        gate = default_gate()
        # Internals are private but the gate must behave correctly on
        # every registered aggregate type.
        for evt in [
            OrderCreated(
                order_id="o-1",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=1.0,
                price=1.0,
                order_type=OrderType.LIMIT,
            ),
        ]:
            assert gate.verdict(evt, _fresh_order()).accepted


class TestSemanticValidatorCompatibility:
    def test_validator_protocol_wiring(self) -> None:
        gate = AdmissionGate(
            registry=AggregateTransitionRegistry(),
            semantic_validators=(OrderEventValidator(), PortfolioEventValidator()),
        )
        # Empty registry → any event gets rejected at B2 without
        # reaching the semantic validators; regression guard that this
        # wiring does not accidentally run them first.
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        v = gate.verdict(evt, _fresh_order())
        assert v.barrier is Barrier.CAUSAL
