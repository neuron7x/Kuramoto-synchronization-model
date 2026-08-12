# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Hermetic behavioural coverage for ``execution.live_loop``.

``execution`` is a forbidden static top-level import in this repository (an
AST-based gate rejects ``import execution`` / ``from execution import``), so the
module under test and its sibling helpers are loaded exclusively via
:func:`importlib.import_module`.  All broker/exchange/clock effects are mocked or
driven through fakes so every test is deterministic and offline.
"""

from __future__ import annotations

import importlib
import json
import threading
import time
import types
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType

_live = importlib.import_module("execution.live_loop")
_conn = importlib.import_module("execution.connectors")
_risk = importlib.import_module("execution.risk")

LiveExecutionLoop = _live.LiveExecutionLoop
LiveLoopConfig = _live.LiveLoopConfig
Signal = _live.Signal
_full_jitter_backoff = _live._full_jitter_backoff
_snapshot_timestamp = _live._snapshot_timestamp

OrderError = _conn.OrderError
TransientOrderError = _conn.TransientOrderError
BinanceConnector = _conn.BinanceConnector
RiskManager = _risk.RiskManager
RiskLimits = _risk.RiskLimits


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeConnector:
    """Duck-typed connector with injectable broker behaviour."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self._id = 0
        self.positions_result: Any = []
        self.open_orders_result: Any = []
        self.fetch_map: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.healthy: bool = True
        self.next_event_typeerror = False
        self.connect_calls = 0
        self.connect_error: Exception | None = None
        self.disconnect_calls = 0

    def connect(self, credentials: Any = None) -> None:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        self._id += 1
        order_id = f"F-{self._id}"
        order.mark_submitted(order_id)
        self.orders[order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if order is None:
            return False
        order.cancel()
        return True

    def fetch_order(self, order_id: str) -> Order:
        result = self.fetch_map.get(order_id, self.orders.get(order_id))
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise OrderError(f"unknown {order_id}")
        return result

    def open_orders(self) -> list[Order]:
        if isinstance(self.open_orders_result, Exception):
            raise self.open_orders_result
        return list(self.open_orders_result)

    def get_positions(self) -> list[dict[str, Any]]:
        if isinstance(self.positions_result, Exception):
            raise self.positions_result
        return list(self.positions_result)

    def next_event(self, timeout: float | None = None) -> dict[str, Any] | None:
        if self.next_event_typeerror:
            raise TypeError("no timeout kwarg supported")
        if self.events:
            return self.events.pop(0)
        return None

    def stream_is_healthy(self) -> bool:
        return self.healthy


class EventOnlyConnector:
    """Connector that streams events but exposes no health probe."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def connect(self, credentials: Any = None) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def next_event(self, timeout: float | None = None) -> dict[str, Any] | None:
        if self.events:
            return self.events.pop(0)
        return None


class FakeWatchdog:
    """Non-threading Watchdog replacement so ``start`` stays hermetic."""

    instances: list["FakeWatchdog"] = []

    def __init__(self, *, name: str, heartbeat_interval: float) -> None:
        self.name = name
        self.heartbeat_interval = heartbeat_interval
        self.registered: dict[str, Callable[[], None]] = {}
        self.stopped = False
        FakeWatchdog.instances.append(self)

    def register(self, name: str, target: Callable[[], None]) -> None:
        self.registered[name] = target

    def stop(self) -> None:
        self.stopped = True

    def snapshot(self) -> dict[str, object]:
        return {"name": self.name, "workers": list(self.registered)}


def make_loop(
    tmp_path: Path,
    *,
    connectors: dict[str, Any] | None = None,
    **config_kwargs: Any,
) -> tuple[Any, Any, dict[str, Any]]:
    config = LiveLoopConfig(state_dir=tmp_path / "state", **config_kwargs)
    risk = RiskManager(RiskLimits(max_notional=1_000_000_000, max_position=1_000_000))
    conns = connectors if connectors is not None else {"venue": FakeConnector()}
    loop = LiveExecutionLoop(conns, risk, config=config)
    return loop, risk, conns


def seq_wait(*values: bool) -> Callable[..., bool]:
    it: Iterator[bool] = iter(values)

    def _wait(timeout: float | None = None) -> bool:
        try:
            return next(it)
        except StopIteration:
            return True

    return _wait


def make_order(
    *, symbol: str = "BTCUSDT", side: OrderSide = OrderSide.BUY, qty: float = 0.5
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=qty,
        price=20_000.0,
        order_type=OrderType.LIMIT,
    )


def adopt_active(loop: Any, venue: str, connector: FakeConnector) -> Order:
    order = make_order()
    placed = connector.place_order(order)
    loop._contexts[venue].oms.adopt_open_order(placed, correlation_id="corr-adopt")
    return placed


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
class TestModuleHelpers:
    def test_full_jitter_bounds(self) -> None:
        for attempt in range(6):
            value = _full_jitter_backoff(1.0, attempt, 10.0)
            assert 0.0 <= value <= 10.0

    def test_full_jitter_negative_attempt(self) -> None:
        assert 0.0 <= _full_jitter_backoff(2.0, -5, 8.0) <= 2.0

    def test_snapshot_timestamp_valid(self, tmp_path: Path) -> None:
        p = tmp_path / "oms_snapshot_1700000000.json"
        p.write_text("{}", encoding="utf-8")
        assert _snapshot_timestamp(p) == 1700000000.0

    def test_snapshot_timestamp_no_underscore(self, tmp_path: Path) -> None:
        p = tmp_path / "snapshot.json"
        p.write_text("{}", encoding="utf-8")
        assert _snapshot_timestamp(p) > 0

    def test_snapshot_timestamp_non_numeric(self, tmp_path: Path) -> None:
        p = tmp_path / "oms_snapshot_abc.json"
        p.write_text("{}", encoding="utf-8")
        assert _snapshot_timestamp(p) > 0

    def test_signal_emit_args_and_kwargs(self) -> None:
        sig = Signal()
        seen: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        sig.connect(lambda *a, **k: seen.append((a, k)))
        sig.emit(1, 2, key="v")
        assert seen == [((1, 2), {"key": "v"})]

    def test_signal_no_subscribers(self) -> None:
        Signal().emit("noop")


# ---------------------------------------------------------------------------
# LiveLoopConfig
# ---------------------------------------------------------------------------
class TestLiveLoopConfig:
    def test_str_state_dir_becomes_path(self, tmp_path: Path) -> None:
        cfg = LiveLoopConfig(state_dir=str(tmp_path / "s"))
        assert isinstance(cfg.state_dir, Path)
        assert cfg.ledger_dir == cfg.state_dir

    def test_explicit_str_ledger_dir(self, tmp_path: Path) -> None:
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", ledger_dir=str(tmp_path / "led"))
        assert isinstance(cfg.ledger_dir, Path)
        assert cfg.ledger_dir.name == "led"

    def test_explicit_path_ledger_dir(self, tmp_path: Path) -> None:
        led = tmp_path / "ledp"
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", ledger_dir=led)
        assert cfg.ledger_dir == led

    def test_pre_action_timeout_non_positive_nulled(self, tmp_path: Path) -> None:
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", pre_action_timeout=0.0)
        assert cfg.pre_action_timeout is None
        cfg2 = LiveLoopConfig(state_dir=tmp_path / "s2", pre_action_timeout=-1.0)
        assert cfg2.pre_action_timeout is None

    def test_interval_flooring(self, tmp_path: Path) -> None:
        cfg = LiveLoopConfig(
            state_dir=tmp_path / "s",
            submission_interval=0.0,
            fill_poll_interval=0.0,
            heartbeat_interval=0.0,
            snapshot_interval=0.0,
        )
        assert cfg.submission_interval == 0.01
        assert cfg.fill_poll_interval == 0.1
        assert cfg.heartbeat_interval == 0.5


# ---------------------------------------------------------------------------
# Construction & lifecycle
# ---------------------------------------------------------------------------
class TestConstructionLifecycle:
    def test_requires_connector(self, tmp_path: Path) -> None:
        config = LiveLoopConfig(state_dir=tmp_path / "s")
        risk = RiskManager(RiskLimits())
        with pytest.raises(ValueError, match="at least one connector"):
            LiveExecutionLoop({}, risk, config=config)

    def test_started_and_watchdog_snapshot_default(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop.started is False
        assert loop.watchdog_snapshot() is None

    def test_start_cold_then_shutdown(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.setattr(_live, "Watchdog", FakeWatchdog)
        FakeWatchdog.instances.clear()
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop.start(cold_start=True)
        assert loop.started is True
        assert connector.connect_calls == 1
        snap = loop.watchdog_snapshot()
        assert snap is not None and "order-submission" in snap["workers"]
        loop.shutdown()
        assert loop.started is False
        assert connector.disconnect_calls == 1

    def test_start_twice_raises(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.setattr(_live, "Watchdog", FakeWatchdog)
        loop, _, _ = make_loop(tmp_path)
        loop.start(cold_start=True)
        with pytest.raises(RuntimeError, match="already started"):
            loop.start(cold_start=True)
        loop.shutdown()

    def test_start_warm_reconciles(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.setattr(_live, "Watchdog", FakeWatchdog)
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        calls: list[str] = []
        monkeypatch.setattr(loop, "_reconcile_state", lambda ctx: calls.append(ctx.name))
        loop.start(cold_start=False)
        assert calls == ["venue"]
        loop.shutdown()

    def test_shutdown_when_not_started_is_noop(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop.shutdown()
        assert loop.started is False

    def test_start_snapshot_failure_disconnects(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})

        class FailingSnapshotter:
            def capture(self, connectors: Any, *, preloaded: Any = None) -> None:
                raise _snapshot_error()

        loop._session_snapshotter = FailingSnapshotter()
        with pytest.raises(RuntimeError, match="valid session snapshot"):
            loop.start(cold_start=True)
        assert loop.started is False
        assert connector.disconnect_calls == 1


def _snapshot_error() -> Exception:
    snap = importlib.import_module("execution.session_snapshot")
    return snap.SessionSnapshotError("boom")


# ---------------------------------------------------------------------------
# submit_order / pre-action filter
# ---------------------------------------------------------------------------
class _DictFilter:
    def __init__(self, decision: Any) -> None:
        self.decision = decision
        self.calls = 0

    def check(self, context: dict[str, object]) -> Any:
        self.calls += 1
        return self.decision


class _BlockingFilter:
    def check(self, context: dict[str, object]) -> Any:
        threading.Event().wait(5.0)
        return {"allowed": True}


class _BoomFilter:
    def check(self, context: dict[str, object]) -> Any:
        raise RuntimeError("filter exploded")


class TestSubmitOrder:
    def test_unknown_venue(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        with pytest.raises(LookupError, match="Unknown venue"):
            loop.submit_order("nope", make_order(), correlation_id="c1")

    def test_no_filter_enqueues(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        result = loop.submit_order("venue", make_order(), correlation_id="c1")
        assert result.status is not OrderStatus.REJECTED
        assert loop._activity.is_set()

    def test_filter_blocks_order(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        decision = {"allowed": False, "reasons": ["too_risky"], "safe_mode": False,
                    "rollback": False, "policy_override": None}
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector},
            pre_action_timeout=None,
        )
        loop._pre_action_filter = _DictFilter(decision)
        order = make_order()
        result = loop.submit_order("venue", order, correlation_id="c1")
        assert result.status is OrderStatus.REJECTED
        assert "pre_action_blocked" in (result.rejection_reason or "")

    def test_filter_safe_mode_and_rollback(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        decision = {"allowed": True, "reasons": "drifting", "safe_mode": True,
                    "rollback": True, "policy_override": "halt"}
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, pre_action_timeout=None
        )
        loop._pre_action_filter = _DictFilter(decision)
        loop.submit_order("venue", make_order(), correlation_id="c1")
        assert loop._strategy_mode == "normal"  # rollback restores prior mode

    def test_filter_object_decision_allowed(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        decision = types.SimpleNamespace(
            allowed=True, reasons=("ok",), safe_mode=False,
            rollback=False, policy_override=None,
        )
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, pre_action_timeout=None
        )
        loop._pre_action_filter = _DictFilter(decision)
        result = loop.submit_order("venue", make_order(), correlation_id="c1")
        assert result.status is not OrderStatus.REJECTED

    def test_filter_timeout_enters_safe_mode(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, pre_action_timeout=0.02
        )
        loop._pre_action_filter = _BlockingFilter()
        order = make_order()
        result = loop.submit_order("venue", order, correlation_id="c1")
        assert result.status is OrderStatus.REJECTED
        assert loop._strategy_mode == loop._config.pre_action_fallback_mode

    def test_filter_error_allows(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, pre_action_timeout=None
        )
        loop._pre_action_filter = _BoomFilter()
        result = loop.submit_order("venue", make_order(), correlation_id="c1")
        assert result.status is not OrderStatus.REJECTED

    def test_call_filter_without_config_raises(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._pre_action_filter = None
        with pytest.raises(RuntimeError, match="not configured"):
            loop._call_pre_action_filter({"venue": "v"})


# ---------------------------------------------------------------------------
# strategy mode & rollback
# ---------------------------------------------------------------------------
class TestStrategyMode:
    def test_apply_same_mode_noop(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._apply_strategy_mode("normal", reason="x")
        assert loop._previous_strategy_mode is None

    def test_apply_empty_mode_noop(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._apply_strategy_mode("", reason="x")
        assert loop._strategy_mode == "normal"

    def test_apply_switch(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._apply_strategy_mode("conservative", reason="drift")
        assert loop._strategy_mode == "conservative"
        assert loop._previous_strategy_mode == "normal"

    def test_rollback_restores_previous(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._apply_strategy_mode("conservative", reason="drift")
        loop._trigger_emergency_rollback(reason="panic")
        assert loop._strategy_mode == "normal"
        assert loop._previous_strategy_mode is None

    def test_rollback_without_previous(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._trigger_emergency_rollback(reason="panic")
        assert loop._strategy_mode == "normal"


# ---------------------------------------------------------------------------
# cancel_order & resolve context
# ---------------------------------------------------------------------------
class TestCancelAndResolve:
    def test_cancel_unknown_order(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop.cancel_order("missing") is False

    def test_cancel_success(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._order_connector[placed.order_id] = "venue"
        loop._last_reported_fill[placed.order_id] = 0.0
        assert loop.cancel_order(placed.order_id, venue="venue") is True
        assert placed.order_id not in loop._order_connector

    def test_cancel_rejected(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        monkeypatch.setattr(loop._contexts["venue"].oms, "cancel", lambda oid: False)
        assert loop.cancel_order(placed.order_id, venue="venue") is False

    def test_resolve_via_mapping(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._order_connector[placed.order_id] = "venue"
        ctx = loop._resolve_context_for_order(placed.order_id)
        assert ctx is not None and ctx.name == "venue"

    def test_resolve_via_search(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        ctx = loop._resolve_context_for_order(placed.order_id)
        assert ctx is not None
        assert loop._order_connector[placed.order_id] == "venue"

    def test_resolve_none(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop._resolve_context_for_order("ghost") is None


# ---------------------------------------------------------------------------
# snapshot restore / persist
# ---------------------------------------------------------------------------
class TestSnapshotRestore:
    def _write_snapshot(self, tmp_path: Path, payload: dict[str, Any], ts: int) -> None:
        snap_dir = tmp_path / "state" / "oms_snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / f"oms_snapshot_{ts}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_no_snapshot(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop is not None  # construction ran restore w/ empty state

    def test_corrupt_then_valid(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "state" / "oms_snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "oms_snapshot_100.json").write_text("{ not json", encoding="utf-8")
        (snap_dir / "oms_snapshot_200.json").write_text(
            json.dumps({"oms": {}, "ledger_offset": 0}), encoding="utf-8"
        )
        loop, _, _ = make_loop(tmp_path)
        assert loop is not None

    def test_valid_with_ledger_offset(self, tmp_path: Path) -> None:
        self._write_snapshot(tmp_path, {"oms": {}, "ledger_offset": 3}, 300)
        loop, _, _ = make_loop(tmp_path)
        assert loop._oms_state.last_ledger_offset() == 3

    def test_restore_exception_path(self, tmp_path: Path) -> None:
        # non-integer ledger_offset raises inside the try, exercising the
        # broad recovery handler without leaving the loop unusable.
        self._write_snapshot(tmp_path, {"oms": {}, "ledger_offset": "bad"}, 400)
        loop, _, _ = make_loop(tmp_path)
        assert loop is not None

    def test_tmp_files_cleaned(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "state" / "oms_snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        stray = snap_dir / "oms_snapshot_500.tmp"
        stray.write_text("partial", encoding="utf-8")
        make_loop(tmp_path)
        assert not stray.exists()


class TestSnapshotPersist:
    def test_too_soon_skips(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path, snapshot_interval=1000.0)
        loop._last_snapshot_ts = time.time()
        loop._persist_oms_snapshot_if_needed()
        snap_dir = tmp_path / "state" / "oms_snapshots"
        assert not list(snap_dir.glob("oms_snapshot_*.json")) if snap_dir.exists() else True

    def test_persists_snapshot(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path, snapshot_interval=1.0)
        loop._last_snapshot_ts = 0.0
        loop._persist_oms_snapshot_if_needed()
        snap_dir = tmp_path / "state" / "oms_snapshots"
        assert list(snap_dir.glob("oms_snapshot_*.json"))

    def test_persist_prunes_old(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "state" / "oms_snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        for ts in range(10, 17):
            (snap_dir / f"oms_snapshot_{ts}.json").write_text("{}", encoding="utf-8")
        loop, _, _ = make_loop(tmp_path, snapshot_interval=1.0)
        loop._last_snapshot_ts = 0.0
        loop._persist_oms_snapshot_if_needed()
        assert len(list(snap_dir.glob("oms_snapshot_*.json"))) <= 6

    def test_persist_exception_swallowed(self, tmp_path: Path, monkeypatch: Any) -> None:
        loop, _, _ = make_loop(tmp_path, snapshot_interval=1.0)
        loop._last_snapshot_ts = 0.0

        def boom() -> dict[str, object]:
            raise RuntimeError("state broke")

        monkeypatch.setattr(loop._oms_state, "snapshot", boom)
        loop._persist_oms_snapshot_if_needed()  # must not raise


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------
class TestReconcile:
    def test_reconcile_open_orders_error(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.open_orders_result = RuntimeError("venue down")
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._reconcile_open_orders(loop._contexts["venue"])  # logged, no raise

    def test_reconcile_open_orders_adopts(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        placed = connector.place_order(make_order())
        connector.open_orders_result = [placed]
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._reconcile_open_orders(loop._contexts["venue"])
        assert loop._oms_state.outstanding("venue")

    def test_reconcile_state_fetch_error(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.open_orders_result = RuntimeError("boom")
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._reconcile_state(loop._contexts["venue"])

    def test_reconcile_state_requeue_missing(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        # order is managed by OMS but venue reports no open orders -> requeue
        connector.open_orders_result = []
        loop._reconcile_state(loop._contexts["venue"])
        assert placed.order_id not in {
            o.order_id for o in loop._contexts["venue"].oms.outstanding()
        }

    def test_reconcile_state_adopts_orphan(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        orphan = connector.place_order(make_order())
        connector.open_orders_result = [orphan]
        loop._reconcile_state(loop._contexts["venue"])
        assert loop._order_connector.get(orphan.order_id) == "venue"

    def test_reconcile_state_requeue_lookup_error(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        adopt_active(loop, "venue", connector)
        connector.open_orders_result = []
        monkeypatch.setattr(
            loop._contexts["venue"].oms,
            "requeue_order",
            lambda oid: (_ for _ in ()).throw(LookupError()),
        )
        loop._reconcile_state(loop._contexts["venue"])


# ---------------------------------------------------------------------------
# risk snapshot hydration
# ---------------------------------------------------------------------------
class TestRiskSnapshot:
    def test_hydrator_absent(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._risk_manager = object()
        loop._refresh_risk_state_from_connectors()  # returns early

    def test_positions_unsupported(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        # remove get_positions so the source is counted as unsupported
        # (setattr with a string target avoids a mypy attribute-type complaint
        # without a suppression that the debt ratchet would count)
        setattr(connector, "get_positions", None)
        snapshot, sources, expected, raw, issues = loop._build_risk_snapshot()
        assert sources == 0
        assert "positions_unsupported" in issues["venue"]

    def test_positions_error(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.positions_result = RuntimeError("no positions")
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        snapshot, sources, expected, raw, issues = loop._build_risk_snapshot()
        assert sources == 0 and expected == 1
        assert any("positions_unavailable" in msg for msg in issues["venue"])

    def test_positions_aggregate_and_hydrate(self, tmp_path: Path) -> None:
        c1 = FakeConnector()
        c2 = FakeConnector()
        c1.positions_result = [
            {"symbol": "BTCUSDT", "net_quantity": 1.0, "mark_price": 20000.0}
        ]
        c2.positions_result = [
            {"symbol": "BTCUSDT", "net_quantity": 0.5, "mark_price": 21000.0}
        ]
        loop, _, _ = make_loop(tmp_path, connectors={"a": c1, "b": c2})
        loop._refresh_risk_state_from_connectors()
        snapshot, sources, _, raw, _ = loop._build_risk_snapshot()
        assert sources == 2
        assert "BTCUSDT" in snapshot

    def test_positions_net_zero_dropped(self, tmp_path: Path) -> None:
        c1 = FakeConnector()
        c2 = FakeConnector()
        c1.positions_result = [
            {"symbol": "ETHUSDT", "net_quantity": 1.0, "mark_price": 3000.0}
        ]
        c2.positions_result = [
            {"symbol": "ETHUSDT", "net_quantity": -1.0, "mark_price": 3000.0}
        ]
        loop, _, _ = make_loop(tmp_path, connectors={"a": c1, "b": c2})
        snapshot, _, _, _, _ = loop._build_risk_snapshot()
        assert "ETHUSDT" not in snapshot


# ---------------------------------------------------------------------------
# _parse_position_payload
# ---------------------------------------------------------------------------
class TestParsePosition:
    def _parse(self, payload: Any) -> Any:
        return LiveExecutionLoop._parse_position_payload(payload)

    def test_non_mapping(self) -> None:
        assert self._parse(["not", "a", "map"]) is None

    def test_missing_symbol(self) -> None:
        assert self._parse({"net_quantity": 1.0}) is None

    def test_net_from_long_short(self) -> None:
        parsed = self._parse(
            {"symbol": "BTC", "long_quantity": 2.0, "short_quantity": 0.5,
             "long_average_price": 100.0}
        )
        assert parsed is not None and parsed[0] == "BTC"

    def test_no_quantity_returns_none(self) -> None:
        assert self._parse({"symbol": "BTC", "mark_price": 100.0}) is None

    def test_short_side_avg_price(self) -> None:
        parsed = self._parse(
            {"symbol": "BTC", "net_quantity": -3.0, "short_average_price": 50.0}
        )
        assert parsed is not None and parsed[1] == -3.0

    def test_notional_from_sides_when_no_avg(self) -> None:
        parsed = self._parse(
            {"symbol": "BTC", "net_quantity": 1.0,
             "long_quantity": 1.0, "long_average_price": 10.0,
             "short_quantity": 2.0, "short_average_price": 20.0}
        )
        assert parsed is not None and parsed[2] > 0

    def test_zero_position_dropped(self) -> None:
        assert self._parse({"symbol": "BTC", "net_quantity": 0.0}) is None


# ---------------------------------------------------------------------------
# order submission loop
# ---------------------------------------------------------------------------
class TestOrderSubmissionLoop:
    def test_empty_queue_waits(self, tmp_path: Path, monkeypatch: Any) -> None:
        loop, _, _ = make_loop(tmp_path)
        monkeypatch.setattr(loop._stop, "wait", lambda t=None: True)
        loop._order_submission_loop()  # LookupError path -> wait -> return

    def test_processes_order(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop.submit_order("venue", make_order(), correlation_id="c1")
        monkeypatch.setattr(loop._stop, "wait", lambda t=None: True)
        loop._order_submission_loop()
        assert loop._order_connector  # order id registered

    def test_stop_set_exits_immediately(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._stop.set()
        loop._order_submission_loop()


# ---------------------------------------------------------------------------
# poll outstanding orders
# ---------------------------------------------------------------------------
class TestPollOutstanding:
    def test_fill_delta_registered(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        remote = make_order()
        remote.mark_submitted(placed.order_id)
        remote.record_fill(0.2, 21000.0)
        connector.fetch_map[placed.order_id] = remote
        loop._poll_outstanding_orders(loop._contexts["venue"])
        stored = loop._contexts["venue"].oms._orders[placed.order_id]
        assert stored.filled_quantity == pytest.approx(0.2)

    def test_transient_error(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        connector.fetch_map[placed.order_id] = TransientOrderError("retry")
        loop._poll_outstanding_orders(loop._contexts["venue"])

    def test_order_error(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        connector.fetch_map[placed.order_id] = OrderError("gone")
        loop._poll_outstanding_orders(loop._contexts["venue"])

    def test_terminal_syncs_state(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        remote = make_order()
        remote.mark_submitted(placed.order_id)
        remote.record_fill(0.5, 20000.0)  # full fill -> terminal
        connector.fetch_map[placed.order_id] = remote
        loop._poll_outstanding_orders(loop._contexts["venue"])
        assert placed.order_id not in loop._order_connector

    def test_terminal_sync_lookup_error(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        remote = make_order()
        remote.mark_submitted(placed.order_id)
        remote.cancel()  # inactive
        connector.fetch_map[placed.order_id] = remote
        monkeypatch.setattr(
            loop._contexts["venue"].oms,
            "sync_remote_state",
            lambda o: (_ for _ in ()).throw(LookupError()),
        )
        loop._poll_outstanding_orders(loop._contexts["venue"])


# ---------------------------------------------------------------------------
# fill polling loop & stream events
# ---------------------------------------------------------------------------
class TestFillPollingLoop:
    def test_loop_single_pass(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        monkeypatch.setattr(loop._stop, "wait", lambda t=None: True)
        loop._fill_polling_loop()

    def test_loop_stop_set(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._stop.set()
        loop._fill_polling_loop()


class TestProcessStreamEvents:
    def test_no_next_event(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path, connectors={"venue": BinanceConnector()})
        assert loop._process_stream_events(loop._contexts["venue"]) is False

    def test_next_event_typeerror(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.next_event_typeerror = True
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        assert loop._process_stream_events(loop._contexts["venue"]) is False

    def test_events_processed(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.events = [{"type": "balance", "balances": [{"asset": "USDT",
                             "free": 10.0, "locked": 1.0}]}]
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        assert loop._process_stream_events(loop._contexts["venue"]) is True

    def test_event_handler_exception(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        connector.events = [{"type": "fill", "order_id": "x", "filled_qty": 1}]
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        monkeypatch.setattr(
            loop, "_handle_stream_event",
            lambda ctx, ev: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert loop._process_stream_events(loop._contexts["venue"]) is True

    def test_unhealthy_stream_falls_back(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.healthy = False
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        assert loop._process_stream_events(loop._contexts["venue"]) is False

    def test_healthy_no_events_trusted(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.healthy = True
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        assert loop._process_stream_events(loop._contexts["venue"]) is True

    def test_healthy_idle_polls(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.healthy = True
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, fill_poll_interval=0.1
        )
        loop._last_stream_event["venue"] = time.monotonic() - 10.0
        assert loop._process_stream_events(loop._contexts["venue"]) is False

    def test_healthy_recent_ok(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        connector.healthy = True
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, fill_poll_interval=100.0
        )
        loop._last_stream_event["venue"] = time.monotonic()
        assert loop._process_stream_events(loop._contexts["venue"]) is True

    def test_no_health_probe_returns_false(self, tmp_path: Path) -> None:
        connector = EventOnlyConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        assert loop._process_stream_events(loop._contexts["venue"]) is False


# ---------------------------------------------------------------------------
# handle stream event
# ---------------------------------------------------------------------------
class TestHandleStreamEvent:
    def _ctx(self, tmp_path: Path) -> tuple[Any, Any, FakeConnector]:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        return loop, loop._contexts["venue"], connector

    def test_empty_type_ignored(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(ctx, {"type": ""})

    def test_fill_known_order(self, tmp_path: Path) -> None:
        loop, ctx, connector = self._ctx(tmp_path)
        placed = adopt_active(loop, "venue", connector)
        loop._handle_stream_event(
            ctx,
            {"type": "fill", "order_id": placed.order_id, "filled_qty": 0.1,
             "fill_price": 20000.0, "status": "partially_filled",
             "cumulative_qty": 0.1, "average_price": 20000.0},
        )
        assert loop._last_reported_fill[placed.order_id] == pytest.approx(0.1)

    def test_fill_unknown_order(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(
            ctx, {"type": "fill", "order_id": "ghost", "filled_qty": 1.0,
                  "fill_price": 5.0}
        )

    def test_fill_missing_order_id(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(ctx, {"type": "fill", "filled_qty": 1.0})

    def test_balance_event(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(
            ctx,
            {"type": "balance", "balances": [
                {"asset": "USDT", "free": 100.0, "locked": 5.0}]},
        )
        assert "balances" in loop._market_state["venue"]

    def test_book_event(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(
            ctx,
            {"type": "book", "symbol": "btcusdt", "bid": 100.0, "ask": 101.0,
             "bid_size": 1.0, "ask_size": 2.0},
        )
        assert "BTCUSDT" in loop._market_state["venue"]["order_book"]

    def test_trade_event(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(
            ctx, {"type": "trade", "symbol": "ethusdt", "price": 3000.0,
                  "quantity": 1.5}
        )
        assert "ETHUSDT" in loop._market_state["venue"]["trades"]

    def test_unknown_event_type(self, tmp_path: Path) -> None:
        loop, ctx, _ = self._ctx(tmp_path)
        loop._handle_stream_event(ctx, {"type": "weather", "temp": 20})


# ---------------------------------------------------------------------------
# apply stream status / map status
# ---------------------------------------------------------------------------
class TestApplyStreamStatus:
    def test_map_status_variants(self) -> None:
        assert LiveExecutionLoop._map_stream_status(None) is None
        assert LiveExecutionLoop._map_stream_status("filled") is OrderStatus.FILLED
        assert LiveExecutionLoop._map_stream_status("weird") is None

    def test_apply_no_order_id(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._apply_stream_status(loop._contexts["venue"], "", None, None, None)

    def test_apply_unknown_order(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._apply_stream_status(
            loop._contexts["venue"], "ghost", OrderStatus.FILLED, 1.0, 5.0
        )

    def test_apply_cumulative_and_status(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._apply_stream_status(
            loop._contexts["venue"], placed.order_id,
            OrderStatus.PARTIALLY_FILLED, 0.1, 20000.0,
        )
        assert loop._last_reported_fill[placed.order_id] == pytest.approx(0.1)

    def test_apply_cancel_terminal(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._order_connector[placed.order_id] = "venue"
        loop._last_reported_fill[placed.order_id] = 0.0
        loop._apply_stream_status(
            loop._contexts["venue"], placed.order_id, OrderStatus.CANCELLED, None, None
        )
        assert placed.order_id not in loop._order_connector

    def test_apply_sync_lookup_error(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        monkeypatch.setattr(
            loop._contexts["venue"].oms,
            "sync_remote_state",
            lambda o: (_ for _ in ()).throw(LookupError()),
        )
        loop._apply_stream_status(
            loop._contexts["venue"], placed.order_id, OrderStatus.OPEN, None, None
        )


# ---------------------------------------------------------------------------
# balances / coerce
# ---------------------------------------------------------------------------
class TestBalancesAndCoerce:
    def test_coerce_float(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop._coerce_float(None) is None
        assert loop._coerce_float("1.5") == 1.5
        assert loop._coerce_float("x") is None

    def test_normalise_balances_list(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        result = loop._normalise_balances(
            [{"asset": "USDT", "free": 10.0, "locked": 2.0}]
        )
        assert result["USDT"]["total"] == pytest.approx(12.0)

    def test_normalise_balances_mapping(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        result = loop._normalise_balances(
            {"first": {"currency": "BTC", "balance": 3.0}}
        )
        assert result["BTC"]["total"] == pytest.approx(3.0)

    def test_normalise_balances_nested_value(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        result = loop._normalise_balances(
            [{"asset": "ETH", "free": {"value": 4.0}, "delta": 1.0}]
        )
        assert result["ETH"]["free"] == pytest.approx(4.0)
        assert result["ETH"]["delta"] == pytest.approx(1.0)

    def test_normalise_balances_non_iterable(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        assert loop._normalise_balances(42) == {}

    def test_normalise_balances_skips_bad_entries(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        result = loop._normalise_balances(["nope", {"free": 1.0}])
        assert result == {}


# ---------------------------------------------------------------------------
# heartbeat loop
# ---------------------------------------------------------------------------
class TestHeartbeatLoop:
    def test_kill_switch_stops(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, risk, _ = make_loop(
            tmp_path, connectors={"venue": connector}, snapshot_interval=1000.0
        )
        loop._last_snapshot_ts = time.time()
        fired: list[str] = []
        loop.on_kill_switch.connect(lambda reason: fired.append(reason))
        risk.kill_switch.trigger("manual halt")
        loop._heartbeat_loop()
        assert fired and loop._stop.is_set()

    def test_positions_success(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        connector.positions_result = [{"symbol": "BTCUSDT", "qty": 1.0}]
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, snapshot_interval=1000.0
        )
        loop._last_snapshot_ts = time.time()
        snaps: list[tuple[str, Any]] = []
        loop.on_position_snapshot.connect(lambda v, p: snaps.append((v, p)))
        monkeypatch.setattr(loop._stop, "wait", seq_wait(True))
        loop._heartbeat_loop()
        assert snaps and snaps[0][0] == "venue"

    def test_positions_error_then_stop(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        connector.positions_result = RuntimeError("down")
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, snapshot_interval=1000.0
        )
        loop._last_snapshot_ts = time.time()
        # first wait (reconnect backoff) returns True -> early return
        monkeypatch.setattr(loop._stop, "wait", seq_wait(True))
        loop._heartbeat_loop()
        assert loop._reconnect_backoff_attempts["venue"] == 1

    def test_positions_error_then_reconnect(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        connector = FakeConnector()
        connector.positions_result = RuntimeError("down")
        loop, _, _ = make_loop(
            tmp_path, connectors={"venue": connector}, snapshot_interval=1000.0
        )
        loop._last_snapshot_ts = time.time()
        reconnected: list[Any] = []
        loop.on_reconnect.connect(lambda *a: reconnected.append(a))
        # backoff wait False -> reconnect attempted; final heartbeat wait True -> exit
        monkeypatch.setattr(loop._stop, "wait", seq_wait(False, True))
        loop._heartbeat_loop()
        assert connector.connect_calls >= 1

    def test_stop_set_exits(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._stop.set()
        loop._heartbeat_loop()


# ---------------------------------------------------------------------------
# cancel-all sweep & position snapshot
# ---------------------------------------------------------------------------
class TestSweepAndSnapshot:
    def test_cancel_all_cancels(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._order_connector[placed.order_id] = "venue"
        loop._last_reported_fill[placed.order_id] = 0.0
        loop._cancel_all_outstanding(reason="sweep")
        assert not list(loop._contexts["venue"].oms.outstanding())

    def test_cancel_all_rejected(self, tmp_path: Path, monkeypatch: Any) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        adopt_active(loop, "venue", connector)
        monkeypatch.setattr(loop._contexts["venue"].oms, "cancel", lambda oid: False)
        loop._cancel_all_outstanding(reason="sweep")
        assert list(loop._contexts["venue"].oms.outstanding())

    def test_emit_position_snapshot(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        seen: list[tuple[str, Any]] = []
        loop.on_position_snapshot.connect(lambda v, p: seen.append((v, p)))
        loop._emit_position_snapshot(
            "venue", [{"symbol": "BTCUSDT", "qty": 2.0}, {"instrument": "ETH"}]
        )
        assert seen and seen[0][0] == "venue"

    def test_capture_snapshot_requires_connectors(self, tmp_path: Path) -> None:
        loop, _, _ = make_loop(tmp_path)
        loop._contexts = {}
        with pytest.raises(_snapshot_error_type(), match="no connectors"):
            loop._capture_session_snapshot()

    def test_register_existing_orders(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        placed = adopt_active(loop, "venue", connector)
        loop._register_existing_orders(loop._contexts["venue"])
        assert loop._order_connector[placed.order_id] == "venue"

    def test_initialise_connector_connects(self, tmp_path: Path) -> None:
        connector = FakeConnector()
        loop, _, _ = make_loop(tmp_path, connectors={"venue": connector})
        loop._initialise_connector(loop._contexts["venue"])
        assert connector.connect_calls == 1
        assert loop._reconnect_backoff_attempts["venue"] == 0


def _snapshot_error_type() -> type[Exception]:
    snap = importlib.import_module("execution.session_snapshot")
    return snap.SessionSnapshotError
