"""Teeth: concurrent same-correlation_id submits must be idempotent (INV-OMS2).

Reproduces the DEFECT-1 TOCTOU window: step-1 releases the lock with the cid only
in _fingerprints; the enqueue into _pending is a SEPARATE lock after the (slow)
pre-trade checks. Two concurrent same-cid+same-payload submits both pass step 1 and
both enqueue -> a double order. A correct OMS enqueues exactly ONE.
"""
from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem
from execution.order_lifecycle import OrderLifecycle, OrderLifecycleStore
from interfaces.execution import RiskController
from libs.db import DataAccessLayer
import sqlite3


class _SlowRisk(RiskController):
    """Permissive but SLOW validate_order — holds inside the unlocked pre-trade
    window long enough for a second same-cid submit to race in."""

    def validate_order(self, symbol, side, qty, price, **kwargs):
        time.sleep(0.12)
        return None

    def register_fill(self, *a, **k): return None
    def current_position(self, symbol): return 0.0
    def current_notional(self, symbol): return 0.0

    @property
    def kill_switch(self): return None


class _Conn(ExecutionConnector):
    def __init__(self): super().__init__(sandbox=True); self._c = 0
    def place_order(self, order, *, idempotency_key=None):
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        s = replace(order)
        if not s.order_id: s.mark_submitted(f"w-{self._c:04d}")
        self._c += 1
        if idempotency_key: self._idempotency_cache[idempotency_key] = s
        self._orders[s.order_id] = s
        return s


@pytest.fixture()
def _lifecycle(tmp_path: Path) -> OrderLifecycle:
    db = tmp_path / "lc.db"
    store = OrderLifecycleStore(
        DataAccessLayer(lambda: sqlite3.connect(db)), schema=None, dialect="sqlite"
    )
    store.ensure_schema()
    return OrderLifecycle(store, clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_concurrent_same_cid_enqueues_exactly_one(tmp_path, _lifecycle):
    config = OMSConfig(state_path=tmp_path / "s.json", auto_persist=False, pre_trade_timeout=1.0)
    oms = OrderManagementSystem(_Conn(), _SlowRisk(), config, lifecycle=_lifecycle)
    o1 = Order(symbol="BTCUSDT", side=OrderSide.BUY, quantity=1.0, order_type=OrderType.MARKET)
    o2 = replace(o1)  # identical payload
    errs: list[BaseException] = []
    def worker(o):
        try:
            oms.submit(o, correlation_id="CID-RACE")
        except Exception as e:  # a correct fix may raise on the 2nd; that's also fine
            errs.append(e)
    ts = [threading.Thread(target=worker, args=(o,)) for o in (o1, o2)]
    for t in ts: t.start()
    for t in ts: t.join()
    # INV-OMS2: the correlation_id must resolve to exactly ONE queued order.
    assert len(oms._queue) == 1, f"double-submit: {len(oms._queue)} orders queued for one cid"
    assert list(oms._pending.keys()) == ["CID-RACE"]
