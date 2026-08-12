# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from execution.arbitrage.inventory import (
    InventoryError,
    InventoryManager,
    InventoryTarget,
)
from execution.arbitrage.liquidity import LiquidityError, LiquidityLedger


def _build_ledger() -> LiquidityLedger:
    return LiquidityLedger()


def test_liquidity_ledger_rejects_balance_below_reservations() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("5"),
        quote_available=Decimal("50000"),
    )
    ledger.reserve(
        "res-1",
        "EX1",
        "BTCUSDT",
        base_amount=Decimal("3"),
        quote_amount=Decimal("0"),
    )
    with pytest.raises(LiquidityError):
        ledger.set_balance(
            "EX1",
            "BTCUSDT",
            base_available=Decimal("2"),
            quote_available=Decimal("50000"),
        )


def test_liquidity_ledger_commit_rejects_negative_balances() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("2"),
        quote_available=Decimal("10000"),
    )
    reservation = ledger.reserve(
        "res-commit",
        "EX1",
        "BTCUSDT",
        base_amount=Decimal("2"),
        quote_amount=Decimal("0"),
    )
    ledger.apply_fill("EX1", "BTCUSDT", base_delta=Decimal("-1"))
    with pytest.raises(LiquidityError):
        ledger.commit(reservation.reservation_id)


def test_liquidity_ledger_commit_failure_does_not_mutate_state() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("2"),
        quote_available=Decimal("10000"),
    )
    reservation = ledger.reserve(
        "res-failure",
        "EX1",
        "BTCUSDT",
        base_amount=Decimal("2"),
        quote_amount=Decimal("0"),
    )
    ledger.apply_fill("EX1", "BTCUSDT", base_delta=Decimal("-1"))
    with pytest.raises(LiquidityError):
        ledger.commit(reservation.reservation_id)

    # Reservation should still be outstanding and the balances unchanged.
    ledger.release(reservation.reservation_id)
    balances = ledger.available_balances()[("EX1", "BTCUSDT")]
    assert balances[0] == Decimal("1")
    assert balances[1] == Decimal("10000")


def test_inventory_manager_identifies_balanced_state() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("5"),
        quote_available=Decimal("5000"),
    )
    ledger.set_balance(
        "EX2",
        "BTCUSDT",
        base_available=Decimal("5"),
        quote_available=Decimal("6000"),
    )
    manager = InventoryManager(
        ledger,
        {"BTCUSDT": ("BTC", "USDT")},
        rebalance_tolerance=Decimal("0.05"),
        min_transfer=Decimal("0.5"),
    )
    targets = {
        "EX1": InventoryTarget(target_weight=Decimal("1")),
        "EX2": InventoryTarget(target_weight=Decimal("1")),
    }
    snapshot, plan = manager.propose_rebalance("BTCUSDT", targets)
    assert plan is None
    assert snapshot.is_balanced(Decimal("0.05"), Decimal("0.5"))


def test_inventory_manager_generates_rebalance_plan() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("10"),
        quote_available=Decimal("4000"),
    )
    ledger.set_balance(
        "EX2",
        "BTCUSDT",
        base_available=Decimal("2"),
        quote_available=Decimal("9000"),
    )
    manager = InventoryManager(
        ledger,
        {"BTCUSDT": ("BTC", "USDT")},
        rebalance_tolerance=Decimal("0.01"),
        min_transfer=Decimal("0.5"),
        transfer_costs={("EX1", "EX2"): Decimal("0.25")},
    )
    targets = {
        "EX1": InventoryTarget(target_weight=Decimal("1"), min_base_buffer=Decimal("4")),
        "EX2": InventoryTarget(target_weight=Decimal("1")),
    }
    snapshot, plan = manager.propose_rebalance("BTCUSDT", targets)
    assert plan is not None
    assert len(plan.transfers) == 1
    transfer = plan.transfers[0]
    assert transfer.source_exchange == "EX1"
    assert transfer.target_exchange == "EX2"
    assert transfer.amount == Decimal("4")
    assert transfer.unit_cost == Decimal("0.25")
    transfer_plan = plan.to_transfer_plan(
        "rebalance-001",
        initiated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        metadata={"strategy": "arbitrage"},
    )
    assert transfer_plan.legs[("EX1", "BTC")] == Decimal("4")
    assert transfer_plan.legs[("EX2", "BTC")] == Decimal("4")
    assert transfer_plan.metadata["estimated_cost"] == str(plan.estimated_cost)
    assert transfer_plan.metadata["strategy"] == "arbitrage"


def test_inventory_manager_respects_buffers_and_costs() -> None:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("12"),
        quote_available=Decimal("8000"),
    )
    ledger.set_balance(
        "EX2",
        "BTCUSDT",
        base_available=Decimal("3"),
        quote_available=Decimal("6000"),
    )
    ledger.set_balance(
        "EX3",
        "BTCUSDT",
        base_available=Decimal("1"),
        quote_available=Decimal("7000"),
    )
    manager = InventoryManager(
        ledger,
        {"BTCUSDT": ("BTC", "USDT")},
        rebalance_tolerance=Decimal("0.02"),
        min_transfer=Decimal("0.25"),
        transfer_costs={
            ("EX1", "EX2"): Decimal("0.10"),
            ("EX1", "EX3"): Decimal("0.03"),
        },
    )
    targets = {
        "EX1": InventoryTarget(
            target_weight=Decimal("2"),
            min_base_buffer=Decimal("6"),
            max_weight=Decimal("0.6"),
        ),
        "EX2": InventoryTarget(target_weight=Decimal("1"), min_base_buffer=Decimal("2")),
        "EX3": InventoryTarget(target_weight=Decimal("1"), min_base_buffer=Decimal("1")),
    }
    snapshot, plan = manager.propose_rebalance("BTCUSDT", targets)
    assert plan is not None
    assert len(plan.transfers) == 2
    amounts = {
        (
            leg.source_exchange,
            leg.target_exchange,
        ): leg
        for leg in plan.transfers
    }
    first_leg = amounts[("EX1", "EX3")]
    assert first_leg.amount == Decimal("3")
    assert first_leg.unit_cost == Decimal("0.03")
    second_leg = amounts[("EX1", "EX2")]
    assert second_leg.amount == Decimal("1")
    assert second_leg.unit_cost == Decimal("0.10")
    assert plan.estimated_cost == Decimal("0.19")


def test_inventory_manager_raises_for_unknown_symbol() -> None:
    ledger = _build_ledger()
    manager = InventoryManager(ledger, {"ETHUSDT": ("ETH", "USDT")})
    with pytest.raises(InventoryError):
        manager.propose_rebalance("BTCUSDT", {"EX1": InventoryTarget(target_weight=Decimal("1"))})


# --------------------------------------------------------------------- one-sided guards
#
# Every fail-closed guard in the liquidity ledger is `if base_violates or quote_violates:
# raise`. A mutation probe left EIGHT `Or -> And` and boundary mutants alive here, because
# each guard was only ever exercised on ONE of its two arms. Under `Or -> And` a violation
# that touches only the base leg (or only the quote leg) slips straight through — the guard
# appears to hold while protecting half of what it claims. These cases drive each arm
# independently, which is the only thing that distinguishes `or` from `and`.


def _seeded_ledger() -> LiquidityLedger:
    ledger = _build_ledger()
    ledger.set_balance(
        "EX1", "BTCUSDT", base_available=Decimal("5"), quote_available=Decimal("50000")
    )
    return ledger


@pytest.mark.parametrize(
    ("base", "quote"),
    [(Decimal("-1"), Decimal("0")), (Decimal("0"), Decimal("-1"))],
)
def test_set_balance_rejects_a_negative_on_either_leg(base: Decimal, quote: Decimal) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        _build_ledger().set_balance("EX1", "BTCUSDT", base_available=base, quote_available=quote)


@pytest.mark.parametrize(
    ("base", "quote"),
    [(Decimal("-1"), Decimal("0")), (Decimal("0"), Decimal("-1"))],
)
def test_reserve_rejects_a_negative_on_either_leg(base: Decimal, quote: Decimal) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        _seeded_ledger().reserve("r", "EX1", "BTCUSDT", base_amount=base, quote_amount=quote)


@pytest.mark.parametrize(
    ("base", "quote"),
    [(Decimal("6"), Decimal("0")), (Decimal("0"), Decimal("60000"))],
)
def test_reserve_rejects_insufficient_liquidity_on_either_leg(
    base: Decimal, quote: Decimal
) -> None:
    with pytest.raises(LiquidityError, match="insufficient available liquidity"):
        _seeded_ledger().reserve("r", "EX1", "BTCUSDT", base_amount=base, quote_amount=quote)


def test_reserve_admits_exactly_the_available_amount() -> None:
    """Matched boundary control: `>` must not be `>=`. Reserving the full balance is legal."""
    ledger = _seeded_ledger()
    reservation = ledger.reserve(
        "r", "EX1", "BTCUSDT", base_amount=Decimal("5"), quote_amount=Decimal("50000")
    )
    assert reservation.base_amount == Decimal("5")
    snapshot = ledger.get_snapshot("EX1", "BTCUSDT")
    assert snapshot is not None
    # get_snapshot reports availability NET of reservations: reserving everything leaves zero.
    assert snapshot.base_available == Decimal("0")
    assert snapshot.quote_available == Decimal("0")


@pytest.mark.parametrize(
    ("base", "quote"),
    [(Decimal("3"), Decimal("0")), (Decimal("0"), Decimal("30000"))],
)
def test_set_balance_rejects_dropping_below_reservations_on_either_leg(
    base: Decimal, quote: Decimal
) -> None:
    ledger = _seeded_ledger()
    ledger.reserve("r", "EX1", "BTCUSDT", base_amount=base, quote_amount=quote)
    with pytest.raises(LiquidityError, match="below outstanding reservations"):
        ledger.set_balance(
            "EX1",
            "BTCUSDT",
            base_available=base - Decimal("1") if base else Decimal("5"),
            quote_available=quote - Decimal("1") if quote else Decimal("50000"),
        )


@pytest.mark.parametrize(
    ("base_delta", "quote_delta"),
    [(Decimal("-6"), Decimal("0")), (Decimal("0"), Decimal("-60000"))],
)
def test_apply_fill_rejects_a_negative_result_on_either_leg(
    base_delta: Decimal, quote_delta: Decimal
) -> None:
    with pytest.raises(LiquidityError, match="negative balance after fill"):
        _seeded_ledger().apply_fill(
            "EX1", "BTCUSDT", base_delta=base_delta, quote_delta=quote_delta
        )


@pytest.mark.parametrize("leg", ["base", "quote"])
def test_commit_rejects_a_negative_result_on_either_leg(leg: str) -> None:
    """`if new_base_available < 0 or new_quote_available < 0` — the last line of defence.

    It IS reachable: reserve against a balance, let a fill drain that balance, then commit.
    The reservation still owes what the balance no longer holds, and committing would settle
    liquidity that is not there. Under `Or -> And` a one-sided shortfall commits silently and
    the ledger goes negative — the exact state this guard exists to make impossible.
    """
    ledger = _seeded_ledger()
    base = Decimal("5") if leg == "base" else Decimal("0")
    quote = Decimal("50000") if leg == "quote" else Decimal("0")
    ledger.reserve("r", "EX1", "BTCUSDT", base_amount=base, quote_amount=quote)
    ledger.apply_fill("EX1", "BTCUSDT", base_delta=-base, quote_delta=-quote)

    with pytest.raises(LiquidityError, match="negative balance after commit"):
        ledger.commit("r")


def test_commit_succeeds_when_the_balance_still_covers_the_reservation() -> None:
    """Matched control for the case above: an ordinary commit must not be blocked."""
    ledger = _seeded_ledger()
    ledger.reserve("r", "EX1", "BTCUSDT", base_amount=Decimal("2"), quote_amount=Decimal("100"))

    ledger.commit("r")

    snapshot = ledger.get_snapshot("EX1", "BTCUSDT")
    assert snapshot is not None
    assert snapshot.base_available == Decimal("3")
    assert snapshot.quote_available == Decimal("49900")
