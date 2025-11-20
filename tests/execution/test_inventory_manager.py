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
        "EX1": InventoryTarget(
            target_weight=Decimal("1"), min_base_buffer=Decimal("4")
        ),
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
        "EX2": InventoryTarget(
            target_weight=Decimal("1"), min_base_buffer=Decimal("2")
        ),
        "EX3": InventoryTarget(
            target_weight=Decimal("1"), min_base_buffer=Decimal("1")
        ),
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
        manager.propose_rebalance(
            "BTCUSDT", {"EX1": InventoryTarget(target_weight=Decimal("1"))}
        )
