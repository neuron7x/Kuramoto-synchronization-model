from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.oms import OMSConfig, OrderManagementSystem
from execution.order_ledger import OrderLedger, OrderLedgerConfig


class DummyConnector:
    """Minimal connector implementing the execution interface used in tests."""

    name = "dummy"

    def __init__(self) -> None:
        self._counter = 0
        self.placed: dict[str, Order] = {}
        self.cancelled: set[str] = set()

    def place_order(self, order: Order, *, idempotency_key: str) -> Order:
        submitted = replace(order)
        submitted.mark_submitted(f"order-{self._counter}")
        self._counter += 1
        self.placed[submitted.order_id] = submitted
        return submitted

    def cancel_order(self, order_id: str) -> bool:
        self.cancelled.add(order_id)
        return True


class DummyRiskController:
    def validate_order(
        self, symbol: str, side: str, quantity: float, price: float | None
    ) -> None:
        return None

    def register_fill(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> None:
        return None


@pytest.fixture()
def simple_order() -> Order:
    return Order(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        order_type=OrderType.LIMIT,
    )


def test_order_ledger_appends_and_replays(tmp_path: Path, simple_order: Order) -> None:
    ledger_path = tmp_path / "order-ledger.jsonl"
    ledger = OrderLedger(ledger_path)

    bootstrap = ledger.append(
        "bootstrap",
        state_snapshot={
            "orders": [],
            "queue": [],
            "processed": {},
            "correlations": {},
        },
        metadata={"comment": "initial"},
    )
    assert bootstrap.sequence == 1
    assert bootstrap.digest

    order_dict = simple_order.to_dict()
    event = ledger.append(
        "order_recorded",
        order=order_dict,
        state_snapshot={
            "orders": [order_dict],
            "queue": [],
            "processed": {"abc": order_dict["order_id"]},
            "correlations": {order_dict["order_id"] or "temp": "abc"},
        },
    )
    assert event.sequence == 2
    assert event.order_snapshot["symbol"] == "BTC-USD"

    events = list(ledger.replay())
    assert [e.sequence for e in events] == [1, 2]

    # Integrity verification should succeed and latest state must match the append payload
    ledger.verify()
    latest_state = ledger.latest_state()
    assert latest_state is not None
    assert latest_state["orders"][0]["symbol"] == "BTC-USD"


def test_oms_writes_and_recovers_from_order_ledger(
    tmp_path: Path, simple_order: Order
) -> None:
    state_path = tmp_path / "oms-state.json"
    ledger_path = tmp_path / "oms-ledger.jsonl"
    config = OMSConfig(state_path=state_path, ledger_path=ledger_path)
    connector = DummyConnector()
    risk = DummyRiskController()
    oms = OrderManagementSystem(connector, risk, config)

    oms.submit(simple_order, correlation_id="corr-1")
    submitted = oms.process_next()
    assert submitted.order_id is not None

    oms.register_fill(submitted.order_id, submitted.quantity, submitted.price or 100.0)

    events = list(oms._ledger.replay())  # type: ignore[attr-defined]
    assert [event.event for event in events] == [
        "order_queued",
        "order_acknowledged",
        "order_fill_recorded",
    ]

    last_state = events[-1].state_snapshot
    assert last_state is not None
    assert last_state["orders"][0]["status"] == OrderStatus.FILLED.value

    # Remove the persisted state to force ledger-driven recovery.
    state_path.unlink()
    connector2 = DummyConnector()
    risk2 = DummyRiskController()
    oms_recovered = OrderManagementSystem(connector2, risk2, config)

    assert len(oms_recovered._orders) == 1  # type: ignore[attr-defined]
    recovered_order = next(iter(oms_recovered._orders.values()))  # type: ignore[attr-defined]
    assert recovered_order.status is OrderStatus.FILLED
    assert recovered_order.order_id == submitted.order_id

    replayed_events = list(oms_recovered._ledger.replay())  # type: ignore[attr-defined]
    assert replayed_events[-1].event == "state_restored"
    assert replayed_events[-1].metadata["source"] == "ledger"


def test_order_ledger_snapshotting_and_indexing(
    tmp_path: Path, simple_order: Order
) -> None:
    ledger_path = tmp_path / "snapshot-ledger.jsonl"
    config = OrderLedgerConfig(
        snapshot_interval=1,
        snapshot_retention=2,
        compaction_threshold_events=50,
        max_journal_size=1024 * 1024,
        archive_retention=2,
        index_stride=1,
    )
    ledger = OrderLedger(ledger_path, config=config)

    order_dict = simple_order.to_dict()
    for i in range(1, 5):
        state = {"orders": [order_dict], "cursor": i}
        ledger.append(
            f"event_{i}",
            order=order_dict,
            metadata={"iteration": i},
            state_snapshot=state,
        )

    sequences = ledger.snapshot_sequences()
    assert len(sequences) == 2
    assert sequences[-1] == 4

    latest_state = ledger.load_snapshot()
    assert latest_state is not None
    assert latest_state["cursor"] == 4

    index_contents = ledger.index_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(index_contents) == 4

    events_from_three = list(ledger.replay_from(3))
    assert [event.sequence for event in events_from_three] == [3, 4]

    with ledger.metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    assert metadata["next_sequence"] == 5


def test_order_ledger_compaction_and_archive(
    tmp_path: Path, simple_order: Order
) -> None:
    ledger_path = tmp_path / "compaction-ledger.jsonl"
    config = OrderLedgerConfig(
        snapshot_interval=1,
        snapshot_retention=5,
        compaction_threshold_events=3,
        max_journal_size=2048,
        archive_retention=3,
        index_stride=1,
    )
    ledger = OrderLedger(ledger_path, config=config)

    order_dict = simple_order.to_dict()
    for i in range(1, 6):
        state = {"orders": [order_dict], "cursor": i}
        ledger.append(
            f"step_{i}",
            order=order_dict,
            metadata={"iteration": i},
            state_snapshot=state,
        )

    sequences = [event.sequence for event in ledger.replay()]
    assert sequences == [5]

    archives_dir = ledger.snapshot_dir / "archives"
    archives = sorted(archives_dir.glob("*.jsonl.gz"))
    assert archives
    assert len(archives) <= config.archive_retention

    with ledger.metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    assert metadata["compacted_through"] == 4
    assert metadata["anchor_digest"] is not None

    ledger.verify()

    recovered = OrderLedger(ledger_path, config=config)
    recovered_events = list(recovered.replay())
    assert [event.sequence for event in recovered_events] == [5]
    restored_state = recovered.load_snapshot()
    assert restored_state is not None
    assert restored_state["cursor"] == 5


def test_order_ledger_self_heals_corruption_and_supports_rollback(
    tmp_path: Path, simple_order: Order
) -> None:
    ledger_path = tmp_path / "healing-ledger.jsonl"
    config = OrderLedgerConfig(
        snapshot_interval=1,
        snapshot_retention=4,
        compaction_threshold_events=100,
        max_journal_size=1024 * 1024,
        archive_retention=2,
        index_stride=1,
    )
    ledger = OrderLedger(ledger_path, config=config)

    order_dict = simple_order.to_dict()
    for i in range(1, 4):
        state = {"orders": [order_dict], "cursor": i}
        ledger.append(
            f"stage_{i}",
            order=order_dict,
            metadata={"iteration": i},
            state_snapshot=state,
        )

    with ledger.path.open("a", encoding="utf-8") as handle:
        handle.write('{"broken": true')

    healed = OrderLedger(ledger_path, config=config)
    healed_events = list(healed.replay())
    assert [event.sequence for event in healed_events] == [1, 2, 3]

    ledger_contents = healed.path.read_text(encoding="utf-8")
    assert "broken" not in ledger_contents

    index_lines = healed.index_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(index_lines) == 3

    snapshot_sequences = healed.snapshot_sequences()
    assert snapshot_sequences == [1, 2, 3]

    rollback_state = healed.load_snapshot(sequence=2)
    assert rollback_state is not None
    assert rollback_state["cursor"] == 2

    with healed.metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    assert metadata["next_sequence"] == 4
    assert metadata["anchor_digest"] is None

    healed.verify()
