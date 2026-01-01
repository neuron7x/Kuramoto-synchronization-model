# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Long-running execution loop orchestrating OMS, connectors, and risk controls."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import random
import threading
import time
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence

from core.utils.metrics import get_metrics_collector
from domain import Order, OrderStatus

from .connectors import ExecutionConnector, OrderError, TransientOrderError
from .oms import OMSConfig, OrderManagementSystem
from .order_ledger import OrderLedger
from .order_lifecycle import IdempotentSubmitter, OMSState
from .risk import RiskManager
from .session_snapshot import (
    ExecutionMode,
    SessionSnapshotError,
    SessionSnapshotter,
)
from .watchdog import Watchdog


def _full_jitter_backoff(base: float, attempt: int, cap: float) -> float:
    """
    Calculate exponential backoff with full jitter.

    Returns a random delay between 0 and min(cap, base * 2^attempt).

    Args:
        base: Base delay in seconds
        attempt: Attempt number (0-indexed)
        cap: Maximum delay cap

    Returns:
        Delay in seconds with full jitter
    """
    return float(random.uniform(0.0, min(cap, base * (2 ** max(0, attempt)))))


def _snapshot_timestamp(path: Path) -> float:
    """Return the timestamp embedded in an OMS snapshot filename.

    Falls back to file modification time when the filename does not conform to
    the expected ``oms_snapshot_{ts}.json`` pattern.
    """
    stem_parts = path.stem.rsplit("_", 1)
    if len(stem_parts) < 2:
        return path.stat().st_mtime
    try:
        return float(stem_parts[-1])
    except ValueError:
        return path.stat().st_mtime


class Signal:
    """Lightweight observer primitive for lifecycle events."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        """Register a callback invoked on :meth:`emit`."""

        self._subscribers.append(handler)

    def emit(self, *args, **kwargs) -> None:
        """Fire the signal, invoking all subscribed handlers."""

        for handler in list(self._subscribers):
            try:
                handler(*args, **kwargs)
            except Exception:  # pragma: no cover - defensive logging path
                logging.getLogger(__name__).exception(
                    "Signal handler failed", extra={"event": "signal.error"}
                )


@dataclass(slots=True)
class LiveLoopConfig:
    """Runtime configuration for :class:`LiveExecutionLoop`."""

    state_dir: Path | str
    submission_interval: float = 0.25
    fill_poll_interval: float = 1.0
    heartbeat_interval: float = 10.0
    max_backoff: float = 60.0
    snapshot_interval: float = 30.0
    pre_action_timeout: float | None = 0.2
    pre_action_fallback_mode: str = "conservative"
    credentials: Mapping[str, Mapping[str, str]] | None = None
    ledger_dir: Path | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state_dir, Path):
            object.__setattr__(self, "state_dir", Path(self.state_dir))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        object.__setattr__(
            self,
            "submission_interval",
            max(0.01, float(self.submission_interval)),
        )
        object.__setattr__(
            self,
            "fill_poll_interval",
            max(0.1, float(self.fill_poll_interval)),
        )
        object.__setattr__(
            self,
            "heartbeat_interval",
            max(0.5, float(self.heartbeat_interval)),
        )
        object.__setattr__(
            self,
            "max_backoff",
            max(self.heartbeat_interval, float(self.max_backoff)),
        )
        object.__setattr__(
            self,
            "snapshot_interval",
            max(1.0, float(self.snapshot_interval)),
        )
        if self.pre_action_timeout is not None and self.pre_action_timeout <= 0:
            object.__setattr__(self, "pre_action_timeout", None)
        ledger_dir = self.ledger_dir
        if ledger_dir is None:
            ledger_dir = self.state_dir
        elif not isinstance(ledger_dir, Path):
            ledger_dir = Path(ledger_dir)
        ledger_dir.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "ledger_dir", ledger_dir)


@dataclass(slots=True)
class _VenueContext:
    name: str
    connector: ExecutionConnector
    oms: OrderManagementSystem
    config: OMSConfig


class LiveExecutionLoop:
    """Manage the lifecycle of live trading execution components."""

    def __init__(
        self,
        connectors: Mapping[str, ExecutionConnector],
        risk_manager: RiskManager,
        *,
        config: LiveLoopConfig,
        session_snapshotter: SessionSnapshotter | None = None,
        pre_action_filter: object | None = None,
    ) -> None:
        if not connectors:
            raise ValueError("at least one connector must be provided")

        self._logger = logging.getLogger(__name__)
        self._config = config
        self._risk_manager = risk_manager
        self._metrics = get_metrics_collector()
        self._contexts: Dict[str, _VenueContext] = {}
        self._order_connector: Dict[str, str] = {}
        self._last_reported_fill: Dict[str, float] = {}
        self._last_stream_event: Dict[str, float] = {}
        self._stop = threading.Event()
        self._activity = threading.Event()
        self._started = False
        self._kill_notified = False
        self._watchdog: Watchdog | None = None
        self._pre_action_filter = pre_action_filter
        self._strategy_mode = "normal"
        self._previous_strategy_mode: str | None = None
        self._session_snapshotter = session_snapshotter or SessionSnapshotter(
            config.state_dir / "session_snapshots",
            mode=ExecutionMode.LIVE,
            risk_manager=self._risk_manager,
        )
        self._pre_session_positions: Dict[str, Sequence[Mapping[str, object]]] = {}
        self._pre_session_position_issues: Dict[str, Sequence[str]] = {}
        self._market_state: Dict[str, Dict[str, Any]] = defaultdict(dict)

        # NEW: Production-hardening lifecycle components
        self._order_ledger = OrderLedger(config.ledger_dir / "order_ledger.jsonl")
        self._oms_state = OMSState()
        self._idempotent_submitter = IdempotentSubmitter()
        self._last_snapshot_ts = 0.0
        self._reconnect_backoff_attempts: Dict[str, int] = defaultdict(int)

        # Try to restore from last snapshot
        self._restore_snapshot_if_present()

        for name, connector in connectors.items():
            state_path = self._config.state_dir / f"{name}_oms.json"
            ledger_path = self._config.ledger_dir / f"{name}_ledger.jsonl"
            oms_config = OMSConfig(state_path=state_path, ledger_path=ledger_path)
            oms = OrderManagementSystem(connector, self._risk_manager, oms_config)
            self._contexts[name] = _VenueContext(name, connector, oms, oms_config)

        # Lifecycle hooks exposed to operators/integration points
        self.on_kill_switch = Signal()
        self.on_reconnect = Signal()
        self.on_position_snapshot = Signal()

    # ------------------------------------------------------------------
    # Public API
    @property
    def started(self) -> bool:
        """Return ``True`` when the live loop has been started."""

        return self._started

    def watchdog_snapshot(self) -> dict[str, object] | None:
        """Return diagnostic data from the underlying watchdog."""

        if self._watchdog is None:
            return None
        return self._watchdog.snapshot()

    def start(self, cold_start: bool) -> None:
        """Start background workers and hydrate state."""

        if self._started:
            raise RuntimeError("LiveExecutionLoop already started")
        self._logger.info(
            "Starting live execution loop",
            extra={"event": "live_loop.start", "cold_start": cold_start},
        )
        self._stop.clear()
        self._activity.clear()
        self._kill_notified = False

        for context in self._contexts.values():
            self._initialise_connector(context)
            context.oms.reload()
            self._register_existing_orders(context)
            if not cold_start:
                self._reconcile_state(context)

        self._refresh_risk_state_from_connectors()

        try:
            self._capture_session_snapshot()
        except SessionSnapshotError as exc:
            self._logger.error(
                "Failed to capture session snapshot",
                extra={
                    "event": "live_loop.snapshot_failed",
                    "error": str(exc),
                },
            )
            for context in self._contexts.values():
                with suppress(Exception):
                    context.connector.disconnect()
            raise RuntimeError(
                "Cannot start live execution loop without a valid session snapshot"
            ) from exc

        self._watchdog = Watchdog(
            name="execution-live-loop",
            heartbeat_interval=self._config.heartbeat_interval,
        )
        self._watchdog.register("order-submission", self._order_submission_loop)
        self._watchdog.register("fill-poller", self._fill_polling_loop)
        self._watchdog.register("heartbeat", self._heartbeat_loop)
        self._started = True

    def shutdown(self) -> None:
        """Stop all background workers and disconnect from venues."""

        if not self._started:
            return
        self._logger.info(
            "Shutting down live execution loop", extra={"event": "live_loop.shutdown"}
        )
        self._stop.set()
        self._activity.set()
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None
        for context in self._contexts.values():
            try:
                context.connector.disconnect()
            except Exception:  # pragma: no cover - defensive
                self._logger.exception(
                    "Failed to disconnect connector",
                    extra={
                        "event": "live_loop.disconnect_error",
                        "venue": context.name,
                    },
                )
        self._started = False

    def submit_order(self, venue: str, order: Order, *, correlation_id: str) -> Order:
        """Submit an order via the underlying OMS."""

        context = self._contexts.get(venue)
        if context is None:
            raise LookupError(f"Unknown venue: {venue}")
        if self._pre_action_filter is not None:
            decision = self._evaluate_pre_action(venue, order)
            if decision["safe_mode"]:
                self._apply_strategy_mode(
                    decision.get("policy_override") or "conservative",
                    reason=";".join(decision["reasons"]),
                )
            if decision["rollback"]:
                self._trigger_emergency_rollback(
                    reason=";".join(decision["reasons"])
                )
            if not decision["allowed"]:
                reason = ";".join(decision["reasons"])
                order.reject(f"pre_action_blocked:{reason}")
                self._logger.warning(
                    "Pre-action filter blocked order",
                    extra={
                        "event": "live_loop.pre_action_blocked",
                        "venue": venue,
                        "symbol": order.symbol,
                        "correlation_id": correlation_id,
                        "reason": reason,
                    },
                )
                return order
        submitted = context.oms.submit(order, correlation_id=correlation_id)
        self._activity.set()
        self._logger.debug(
            "Order enqueued",
            extra={
                "event": "live_loop.order_enqueued",
                "venue": venue,
                "symbol": order.symbol,
                "correlation_id": correlation_id,
            },
        )
        return submitted

    def cancel_order(self, order_id: str, *, venue: str | None = None) -> bool:
        """Cancel an order and update local lifecycle tracking."""

        context = self._resolve_context_for_order(order_id, venue=venue)
        if context is None:
            self._logger.warning(
                "Cancel requested for unknown order",
                extra={
                    "event": "live_loop.cancel_unknown",
                    "order_id": order_id,
                    "venue": venue,
                },
            )
            return False

        try:
            cancelled = context.oms.cancel(order_id)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.exception(
                "Failed to cancel order",
                extra={
                    "event": "live_loop.cancel_error",
                    "venue": context.name,
                    "order_id": order_id,
                    "error": str(exc),
                },
            )
            return False

        if cancelled:
            self._order_connector.pop(order_id, None)
            self._last_reported_fill.pop(order_id, None)
            self._logger.info(
                "Order cancelled",
                extra={
                    "event": "live_loop.order_cancelled",
                    "venue": context.name,
                    "order_id": order_id,
                },
            )
        else:
            self._logger.warning(
                "Order cancellation rejected by venue",
                extra={
                    "event": "live_loop.cancel_rejected",
                    "venue": context.name,
                    "order_id": order_id,
                },
            )
        return cancelled

    def _apply_strategy_mode(self, mode: str, *, reason: str) -> None:
        if not mode or mode == self._strategy_mode:
            return
        self._previous_strategy_mode = self._strategy_mode
        self._strategy_mode = mode
        self._logger.warning(
            "Strategy mode switched",
            extra={
                "event": "live_loop.strategy_mode_switch",
                "from": self._previous_strategy_mode,
                "to": self._strategy_mode,
                "reason": reason,
            },
        )

    def _trigger_emergency_rollback(self, *, reason: str) -> None:
        self._logger.error(
            "Emergency rollback triggered",
            extra={
                "event": "live_loop.emergency_rollback",
                "reason": reason,
                "strategy_mode": self._strategy_mode,
            },
        )
        self._cancel_all_outstanding(reason=reason)
        if self._previous_strategy_mode is not None:
            restored = self._previous_strategy_mode
            self._previous_strategy_mode = None
            self._strategy_mode = restored
            self._logger.warning(
                "Strategy mode rolled back",
                extra={
                    "event": "live_loop.strategy_mode_rollback",
                    "restored": restored,
                    "reason": reason,
            },
        )

    def _call_pre_action_filter(self, context: dict[str, object]) -> object:
        if self._pre_action_filter is None:
            raise RuntimeError("Pre-action filter not configured")
        timeout = self._config.pre_action_timeout
        if not timeout:
            return self._pre_action_filter.check(context)  # type: ignore[attr-defined]
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._pre_action_filter.check, context  # type: ignore[attr-defined]
            )
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"pre_action_filter exceeded {timeout:.3f}s timeout"
                ) from exc

    def _evaluate_pre_action(self, venue: str, order: Order) -> dict[str, object]:
        context = self._build_pre_action_context(venue, order)
        try:
            decision = self._call_pre_action_filter(context)
        except TimeoutError as exc:
            self._logger.warning(
                "Pre-action filter timed out; entering safe mode",
                extra={
                    "event": "live_loop.pre_action_timeout",
                    "venue": venue,
                    "symbol": order.symbol,
                    "timeout": self._config.pre_action_timeout,
                    "error": str(exc),
                },
            )
            return {
                "allowed": False,
                "reasons": ("pre_action_timeout",),
                "safe_mode": True,
                "rollback": False,
                "policy_override": self._config.pre_action_fallback_mode,
            }
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.exception(
                "Pre-action filter failed",
                extra={
                    "event": "live_loop.pre_action_error",
                    "venue": venue,
                    "symbol": order.symbol,
                    "error": str(exc),
                },
            )
            return {
                "allowed": True,
                "reasons": ("filter_error",),
                "safe_mode": False,
                "rollback": False,
                "policy_override": None,
            }
        if isinstance(decision, Mapping):
            allowed = bool(decision.get("allowed", True))
            reasons = decision.get("reasons", ()) or ()
            safe_mode = bool(decision.get("safe_mode", False))
            rollback = bool(decision.get("rollback", False))
            policy_override = decision.get("policy_override")
        else:
            allowed = bool(getattr(decision, "allowed", True))
            reasons = getattr(decision, "reasons", ()) or ()
            safe_mode = bool(getattr(decision, "safe_mode", False))
            rollback = bool(getattr(decision, "rollback", False))
            policy_override = getattr(decision, "policy_override", None)
        if isinstance(reasons, str):
            reasons = (reasons,)
        else:
            reasons = tuple(reasons)
        return {
            "allowed": allowed,
            "reasons": reasons,
            "safe_mode": safe_mode,
            "rollback": rollback,
            "policy_override": policy_override,
        }

    def _build_pre_action_context(self, venue: str, order: Order) -> dict[str, object]:
        venue_state = self._market_state.get(venue, {})
        return {
            "venue": venue,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "price": order.price,
            "volatility": self._coerce_float(venue_state.get("volatility")),
            "liquidity": self._coerce_float(venue_state.get("liquidity")),
            "latency_ms": self._coerce_float(
                venue_state.get("latency_ms") or venue_state.get("latency")
            ),
            "policy_deviation": self._coerce_float(
                venue_state.get("policy_deviation")
            ),
            "policy_mode": self._strategy_mode,
            "timestamp": time.time(),
            "metadata": {"market_state_keys": tuple(venue_state.keys())},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    def _restore_snapshot_if_present(self) -> None:
        """
        Restore the last OMS snapshot if available; otherwise start with empty state.

        On restore, replays the ledger from the last offset to catch up with any
        events that occurred after the snapshot was taken.
        """
        try:
            snapshot_dir = self._config.state_dir / "oms_snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            for tmp in snapshot_dir.glob("oms_snapshot_[0-9]*.tmp"):
                with suppress(OSError):
                    tmp.unlink()

            files = sorted(
                snapshot_dir.glob("oms_snapshot_[0-9]*.json"), key=_snapshot_timestamp
            )
            if not files:
                self._logger.info("No OMS snapshot found; starting with empty state")
                return

            last_snapshot: Path | None = None
            payload: dict[str, object] | None = None
            for candidate in reversed(files):
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                    last_snapshot = candidate
                    break
                except (
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    FileNotFoundError,
                    PermissionError,
                    IsADirectoryError,
                ):
                    self._logger.warning(
                        "Skipping corrupt OMS snapshot",
                        extra={
                            "event": "live_loop.snapshot_corrupt",
                            "path": str(candidate),
                        },
                    )
                    continue

            if last_snapshot is None:
                self._logger.info("No valid OMS snapshot found; starting fresh")
                return

            self._logger.info(
                f"Restoring OMS snapshot from {last_snapshot.name}",
                extra={
                    "event": "live_loop.snapshot_restore",
                    "path": str(last_snapshot),
                },
            )

            oms_data = payload.get("oms")
            if oms_data:
                self._oms_state = OMSState.restore(oms_data)

            last_offset = int(payload.get("ledger_offset", 0))
            if last_offset:
                self._oms_state.set_ledger_offset(last_offset)
                # Replay ledger from last_offset to catch up
                # Aggregate replay from all venue OMS ledgers
                for context in self._contexts.values():
                    for record in context.oms.replay_ledger_from(
                        last_offset + 1, verify=False
                    ):
                        evt = (
                            record.event
                            if hasattr(record, "event")
                            else record.get("event") or {}
                        )
                        # Pass sequence number to track ledger offset
                        seq = record.sequence if hasattr(record, "sequence") else None
                        self._oms_state.apply(evt, sequence=seq)

                self._logger.info(
                    f"Replayed ledger from offset {last_offset}",
                    extra={"event": "live_loop.ledger_replay", "offset": last_offset},
                )
        except Exception as exc:
            self._logger.warning(
                f"Failed to restore snapshot: {exc}",
                extra={"event": "live_loop.snapshot_restore_failed", "error": str(exc)},
            )

    def _persist_oms_snapshot_if_needed(self) -> None:
        """
        Periodically persist an OMS snapshot with ledger offset.

        Snapshots include the ledger offset, OMS state, and a checksum for integrity.
        """
        now = time.time()
        if now - self._last_snapshot_ts < self._config.snapshot_interval:
            return

        try:
            snapshot_dir = self._config.state_dir / "oms_snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            # Get current ledger offset from venue OMS ledgers
            # Use the maximum sequence across all venue ledgers
            current_ledger_offset = 0
            for context in self._contexts.values():
                latest_seq = context.oms.latest_ledger_sequence()
                if latest_seq and latest_seq > current_ledger_offset:
                    current_ledger_offset = latest_seq

            # Sync OMS state's ledger offset
            if current_ledger_offset > 0:
                self._oms_state.set_ledger_offset(current_ledger_offset)

            payload = {
                "mode": "live",
                "ts": now,
                "ledger_offset": current_ledger_offset,
                "oms": self._oms_state.snapshot(),
            }

            # Optional: add checksum
            checksum = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            payload["checksum"] = f"sha256:{checksum}"

            fname = snapshot_dir / f"oms_snapshot_{int(now)}.json"
            tmp_path = fname.with_suffix(fname.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
                fh.flush()
                os.fsync(fh.fileno())
            tmp_path.replace(fname)

            self._last_snapshot_ts = now
            self._logger.debug(
                f"Persisted OMS snapshot to {fname.name}",
                extra={"event": "live_loop.snapshot_persisted", "path": str(fname)},
            )

            # Clean up old snapshots (keep last 5)
            all_snapshots = list(snapshot_dir.glob("oms_snapshot_*.json"))
            if len(all_snapshots) > 5:
                all_snapshots.sort(key=_snapshot_timestamp)
                for old_snapshot in all_snapshots[:-5]:
                    try:
                        old_snapshot.unlink()
                    except Exception as exc:
                        self._logger.debug(
                            "Failed to remove old snapshot",
                            extra={
                                "event": "live_loop.snapshot_cleanup_failed",
                                "path": str(old_snapshot),
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
        except Exception as exc:
            self._logger.debug(
                f"Snapshot persistence failed: {exc}",
                extra={"event": "live_loop.snapshot_persist_failed", "error": str(exc)},
            )

    def _reconcile_open_orders(self, context: _VenueContext) -> None:
        """
        Reconcile venue-open orders with OMS state by adopting unknown orders.

        This is called on restart/reconnect to ensure all venue-open orders are
        tracked in the local OMS state.
        """
        try:
            open_orders = list(context.connector.open_orders())
        except Exception as exc:
            self._logger.warning(
                f"Failed to fetch open orders for {context.name}: {exc}",
                extra={
                    "event": "live_loop.reconcile_open_failed",
                    "venue": context.name,
                    "error": str(exc),
                },
            )
            return

        # Adopt orders into OMS state
        self._oms_state.adopt(context.name, open_orders)

        if open_orders:
            self._logger.info(
                f"Adopted {len(open_orders)} open orders from {context.name}",
                extra={
                    "event": "live_loop.adopt_orders",
                    "venue": context.name,
                    "count": len(open_orders),
                },
            )

    # ------------------------------------------------------------------
    # Internal helpers
    def _resolve_context_for_order(
        self, order_id: str, *, venue: str | None = None
    ) -> _VenueContext | None:
        if venue is not None:
            return self._contexts.get(venue)

        mapped = self._order_connector.get(order_id)
        if mapped is not None:
            context = self._contexts.get(mapped)
            if context is not None:
                return context

        for context in self._contexts.values():
            for order in context.oms.outstanding():
                if order.order_id == order_id:
                    self._order_connector[order_id] = context.name
                    return context
        return None

    def _initialise_connector(self, context: _VenueContext) -> None:
        credentials = None
        if self._config.credentials is not None:
            credentials = self._config.credentials.get(context.name)

        attempt = 0
        while not self._stop.is_set():
            try:
                context.connector.connect(credentials)
                self._logger.info(
                    "Connector initialised",
                    extra={"event": "live_loop.connector_ready", "venue": context.name},
                )
                # Reset backoff counter on successful connection
                self._reconnect_backoff_attempts[context.name] = 0
                return
            except Exception as exc:  # pragma: no cover - rarely triggered in tests
                attempt += 1
                self._reconnect_backoff_attempts[context.name] = attempt
                # Use full jitter backoff
                delay = _full_jitter_backoff(
                    self._config.heartbeat_interval,
                    attempt - 1,
                    self._config.max_backoff,
                )
                self._logger.warning(
                    "Connector initialisation failed",
                    extra={
                        "event": "live_loop.connector_retry",
                        "venue": context.name,
                        "attempt": attempt,
                        "delay": delay,
                        "error": str(exc),
                    },
                )
                self.on_reconnect.emit(context.name, attempt, delay, exc)
                if self._stop.wait(delay):
                    return

    def _register_existing_orders(self, context: _VenueContext) -> None:
        for order in context.oms.outstanding():
            if order.order_id is None:
                continue
            self._order_connector[order.order_id] = context.name
            self._last_reported_fill[order.order_id] = order.filled_quantity

    def _reconcile_state(self, context: _VenueContext) -> None:
        # First, reconcile open orders with OMS state
        self._reconcile_open_orders(context)

        try:
            venue_orders = {
                order.order_id: order
                for order in context.connector.open_orders()
                if order.order_id is not None
            }
        except Exception as exc:
            self._logger.warning(
                "Failed to fetch open orders during reconciliation",
                extra={
                    "event": "live_loop.reconcile_failed",
                    "venue": context.name,
                    "error": str(exc),
                },
            )
            return

        managed_orders = {
            order.order_id: order
            for order in context.oms.outstanding()
            if order.order_id is not None and order.is_active
        }

        missing_on_venue = set(managed_orders) - set(venue_orders)
        orphan_on_oms = set(venue_orders) - set(managed_orders)

        state_changed = False

        for order_id in missing_on_venue:
            try:
                correlation = context.oms.requeue_order(order_id)
                self._logger.warning(
                    "Re-queued order missing on venue",
                    extra={
                        "event": "live_loop.requeue_order",
                        "venue": context.name,
                        "order_id": order_id,
                        "correlation_id": correlation,
                    },
                )
                self._activity.set()
                state_changed = True
            except LookupError:
                continue

        for order_id in orphan_on_oms:
            order = venue_orders[order_id]
            correlation = (
                context.oms.correlation_for(order_id) or f"recovered-{order_id}"
            )
            context.oms.adopt_open_order(order, correlation_id=correlation)
            self._order_connector[order_id] = context.name
            self._last_reported_fill[order_id] = order.filled_quantity
            # Sync with global OMS state
            self._oms_state.apply(
                {
                    "type": "adopt",
                    "venue": context.name,
                    "order": {"order_id": order_id, "_obj": order},
                    "ts": time.time(),
                }
            )
            self._logger.warning(
                "Adopted orphan order from venue",
                extra={
                    "event": "live_loop.adopt_order",
                    "venue": context.name,
                    "order_id": order_id,
                    "correlation_id": correlation,
                },
            )
            state_changed = True

        if state_changed:
            self._refresh_risk_state_from_connectors()

    def _capture_session_snapshot(self) -> None:
        connectors = {
            name: context.connector for name, context in self._contexts.items()
        }
        if not connectors:
            raise SessionSnapshotError("no connectors configured for snapshot")
        preloaded: dict[str, tuple[Sequence[Mapping[str, object]], Sequence[str]]] = {}
        for name in connectors:
            positions = self._pre_session_positions.get(name, ())
            issues = self._pre_session_position_issues.get(name, ())
            preloaded[name] = (positions, issues)
        self._session_snapshotter.capture(connectors, preloaded=preloaded)

    def _refresh_risk_state_from_connectors(self) -> None:
        hydrator = getattr(self._risk_manager, "hydrate_positions", None)
        if not callable(hydrator):
            return
        (
            snapshot,
            sources,
            expected,
            raw_positions,
            position_errors,
        ) = self._build_risk_snapshot()
        self._pre_session_positions = raw_positions
        self._pre_session_position_issues = position_errors
        if sources == 0:
            return
        try:
            replace = expected > 0 and sources == expected
            hydrator(snapshot, replace=replace)
        except Exception as exc:  # pragma: no cover - defensive logging path
            self._logger.warning(
                "Failed to hydrate risk state from connectors",
                extra={
                    "event": "live_loop.risk_hydration_failed",
                    "error": str(exc),
                },
            )

    def _build_risk_snapshot(
        self,
    ) -> tuple[
        dict[str, tuple[float, float]],
        int,
        int,
        dict[str, Sequence[Mapping[str, object]]],
        dict[str, Sequence[str]],
    ]:
        snapshot: dict[str, tuple[float, float]] = {}
        sources = 0
        expected = 0
        raw_positions: dict[str, list[Mapping[str, object]]] = {}
        issues: dict[str, list[str]] = {}
        for context in self._contexts.values():
            connector = context.connector
            get_positions = getattr(connector, "get_positions", None)
            if not callable(get_positions):
                issues.setdefault(context.name, []).append("positions_unsupported")
                continue
            expected += 1
            try:
                positions = get_positions()
            except Exception as exc:
                self._logger.warning(
                    "Failed to fetch positions for risk hydration",
                    extra={
                        "event": "live_loop.positions_failed",
                        "venue": context.name,
                        "error": str(exc),
                    },
                )
                issues.setdefault(context.name, []).append(
                    f"positions_unavailable:{type(exc).__name__}:{exc}".rstrip(":")
                )
                continue
            sources += 1
            positions_list = list(positions)
            normalised_positions = [
                payload for payload in positions_list if isinstance(payload, Mapping)
            ]
            if normalised_positions:
                raw_positions[context.name] = normalised_positions
            for payload in positions_list:
                parsed = self._parse_position_payload(payload)
                if parsed is None:
                    continue
                symbol, quantity, notional = parsed
                existing = snapshot.get(symbol)
                if existing is None:
                    if abs(quantity) <= 1e-12 and notional <= 0.0:
                        continue
                    snapshot[symbol] = (quantity, notional)
                    continue
                combined_qty = existing[0] + quantity
                combined_notional = max(existing[1], notional)
                existing_price = (
                    existing[1] / abs(existing[0])
                    if abs(existing[0]) > 1e-12 and existing[1] > 0.0
                    else None
                )
                new_price = (
                    notional / abs(quantity)
                    if abs(quantity) > 1e-12 and notional > 0.0
                    else None
                )
                price_candidates = [
                    p for p in (existing_price, new_price) if p is not None
                ]
                if price_candidates:
                    combined_notional = max(
                        combined_notional,
                        abs(combined_qty) * price_candidates[-1],
                    )
                if abs(combined_qty) <= 1e-12:
                    snapshot.pop(symbol, None)
                else:
                    snapshot[symbol] = (combined_qty, combined_notional)
        return snapshot, sources, expected, raw_positions, issues

    @staticmethod
    def _parse_position_payload(
        payload: Mapping[str, object] | object,
    ) -> tuple[str, float, float] | None:
        if not isinstance(payload, Mapping):
            return None
        symbol = str(payload.get("symbol") or payload.get("instrument") or "").strip()
        if not symbol:
            return None

        def _first(keys: Iterable[str]) -> float | None:
            for key in keys:
                if key not in payload:
                    continue
                try:
                    return float(payload[key])
                except (TypeError, ValueError):
                    continue
            return None

        net_qty = _first(["net_quantity", "net_qty", "net_position", "quantity", "qty"])
        if net_qty is None:
            long_qty = _first(["long_quantity", "long_qty"])
            short_qty = _first(["short_quantity", "short_qty"])
            if long_qty is None and short_qty is None:
                return None
            net_qty = (long_qty or 0.0) - (short_qty or 0.0)

        avg_price = _first(["mark_price", "average_price", "avg_price", "price"])
        if avg_price is None:
            if net_qty > 0:
                avg_price = _first(["long_average_price", "long_avg_price"])
            elif net_qty < 0:
                avg_price = _first(["short_average_price", "short_avg_price"])

        long_qty = _first(["long_quantity", "long_qty"])
        long_avg = _first(["long_average_price", "long_avg_price"])
        short_qty = _first(["short_quantity", "short_qty"])
        short_avg = _first(["short_average_price", "short_avg_price"])

        if avg_price is None:
            candidates = []
            if long_qty and long_avg:
                candidates.append(abs(long_qty * long_avg))
            if short_qty and short_avg:
                candidates.append(abs(short_qty * short_avg))
            notional = max(candidates) if candidates else 0.0
        else:
            notional = abs(net_qty) * abs(avg_price)
            if notional <= 0 and long_qty and long_avg:
                notional = abs(long_qty * long_avg)
            if notional <= 0 and short_qty and short_avg:
                notional = max(notional, abs(short_qty * short_avg))

        if abs(net_qty) <= 1e-12 and notional <= 0.0:
            return None
        return symbol, float(net_qty), float(notional)

    def _order_submission_loop(self) -> None:
        while not self._stop.is_set():
            processed_any = False
            for context in self._contexts.values():
                try:
                    with self._metrics.measure_order_placement(
                        context.name,
                        "*",
                        "batch",
                    ):
                        order = context.oms.process_next()
                except LookupError:
                    continue
                except Exception as exc:  # pragma: no cover - logged for visibility
                    self._logger.exception(
                        "Order processing failed",
                        extra={
                            "event": "live_loop.process_error",
                            "venue": context.name,
                            "error": str(exc),
                        },
                    )
                    continue

                processed_any = True
                if order.order_id is not None:
                    self._order_connector[order.order_id] = context.name
                    self._last_reported_fill[order.order_id] = order.filled_quantity
                    try:
                        self._metrics.record_order_placed(
                            context.name,
                            order.symbol,
                            order.order_type.value,
                            order.status.value,
                        )
                    except Exception:  # pragma: no cover - defensive
                        self._logger.exception(
                            "Failed to record metrics",
                            extra={
                                "event": "live_loop.metrics_error",
                                "venue": context.name,
                            },
                        )
                self._logger.info(
                    "Order processed",
                    extra={
                        "event": "live_loop.order_processed",
                        "venue": context.name,
                        "order_id": order.order_id,
                        "status": order.status.value,
                    },
                )

            if not processed_any:
                if self._stop.wait(self._config.submission_interval):
                    return
                self._activity.clear()

    def _poll_outstanding_orders(self, context: _VenueContext) -> None:
        outstanding = list(context.oms.outstanding())
        for order in outstanding:
            if order.order_id is None or not order.is_active:
                continue
            try:
                remote = context.connector.fetch_order(order.order_id)
            except OrderError as exc:
                self._logger.warning(
                    "Failed to fetch order state",
                    extra={
                        "event": "live_loop.fetch_failed",
                        "venue": context.name,
                        "order_id": order.order_id,
                        "error": str(exc),
                    },
                )
                continue
            except (TransientOrderError, ConnectionError, TimeoutError) as exc:
                self._logger.warning(
                    "Transient error while polling order",
                    extra={
                        "event": "live_loop.poll_retry",
                        "venue": context.name,
                        "order_id": order.order_id,
                        "error": str(exc),
                    },
                )
                continue

            last = self._last_reported_fill.get(order.order_id, 0.0)
            delta = max(0.0, remote.filled_quantity - last)
            if delta > 0:
                price = remote.average_price or remote.price or 0.0
                if price <= 0:
                    price = 1.0
                context.oms.register_fill(order.order_id, delta, price)
                self._last_reported_fill[order.order_id] = remote.filled_quantity
                self._logger.info(
                    "Registered fill",
                    extra={
                        "event": "live_loop.register_fill",
                        "venue": context.name,
                        "order_id": order.order_id,
                        "fill_qty": delta,
                    },
                )

            if not remote.is_active:
                try:
                    context.oms.sync_remote_state(remote)
                except LookupError:
                    self._logger.warning(
                        "Remote order missing from OMS during sync",
                        extra={
                            "event": "live_loop.sync_missing",
                            "venue": context.name,
                            "order_id": order.order_id,
                        },
                    )
                self._order_connector.pop(order.order_id, None)
                self._last_reported_fill.pop(order.order_id, None)

    def _fill_polling_loop(self) -> None:
        while not self._stop.is_set():
            for context in self._contexts.values():
                if self._process_stream_events(context):
                    continue
                self._poll_outstanding_orders(context)

            if self._stop.wait(self._config.fill_poll_interval):
                return

    def _process_stream_events(self, context: _VenueContext) -> bool:
        connector = context.connector
        next_event = getattr(connector, "next_event", None)
        if not callable(next_event):
            return False

        processed = False
        while not self._stop.is_set():
            try:
                event = next_event(timeout=0.0)
            except TypeError:
                return False
            if event is None:
                break
            processed = True
            self._last_stream_event[context.name] = monotonic()
            try:
                self._handle_stream_event(context, event)
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception(
                    "Failed to process stream event",
                    extra={
                        "event": "live_loop.stream_error",
                        "venue": context.name,
                        "error": str(exc),
                    },
                )
        if processed:
            return True

        health_check = getattr(connector, "stream_is_healthy", None)
        if callable(health_check):
            healthy = bool(health_check())
            if not healthy:
                self._logger.warning(
                    "Stream unhealthy; falling back to REST polling",
                    extra={
                        "event": "live_loop.stream_unhealthy",
                        "venue": context.name,
                    },
                )
                return False

            last_seen = self._last_stream_event.get(context.name)
            if last_seen is None:
                return True  # Trust healthy stream even if no events seen yet

            silence = monotonic() - last_seen
            if silence >= self._config.fill_poll_interval:
                self._logger.info(
                    "Stream healthy but idle; polling outstanding orders",
                    extra={
                        "event": "live_loop.stream_idle",
                        "venue": context.name,
                        "idle_for": round(silence, 3),
                    },
                )
                return False

            return True
        return False

    def _handle_stream_event(
        self, context: _VenueContext, event: Mapping[str, Any]
    ) -> None:
        event_type = str(event.get("type") or "").lower()
        if not event_type:
            return

        if event_type == "fill":
            order_id = str(
                event.get("order_id")
                or event.get("client_order_id")
                or event.get("i")
                or ""
            ).strip()
            if not order_id:
                return
            quantity = self._coerce_float(
                event.get("filled_qty")
                or event.get("fill_qty")
                or event.get("last_qty")
                or event.get("quantity")
            )
            price = self._coerce_float(
                event.get("fill_price")
                or event.get("price")
                or event.get("avg_price")
                or event.get("average_price")
            )
            if quantity is not None and quantity > 0:
                fill_price = price if price and price > 0 else 1.0
                try:
                    context.oms.register_fill(order_id, quantity, fill_price)
                    self._last_reported_fill[order_id] = (
                        self._last_reported_fill.get(order_id, 0.0) + quantity
                    )
                except KeyError:
                    self._logger.warning(
                        "Stream reported fill for unknown order",
                        extra={
                            "event": "live_loop.stream_unknown_fill",
                            "venue": context.name,
                            "order_id": order_id,
                        },
                    )
            cumulative = self._coerce_float(
                event.get("cumulative_qty")
                or event.get("cummulative_qty")
                or event.get("filled_quantity")
                or event.get("cumulative_filled")
            )
            avg_price = self._coerce_float(
                event.get("average_price")
                or event.get("avg_price")
                or event.get("fill_price")
                or event.get("price")
            )
            status = self._map_stream_status(event.get("status"))
            if status is not None or cumulative is not None or avg_price is not None:
                self._apply_stream_status(
                    context, order_id, status, cumulative, avg_price
                )
            return

        if event_type in {"balance", "account"}:
            balances = self._normalise_balances(event.get("balances") or event)
            if balances:
                venue_state = self._market_state.setdefault(context.name, {})
                venue_state["balances"] = balances
            return

        if event_type in {"book", "order_book", "ticker"}:
            symbol = str(
                event.get("symbol") or event.get("product_id") or event.get("s") or ""
            ).upper()
            if symbol:
                venue_state = self._market_state.setdefault(context.name, {})
                books = venue_state.setdefault("order_book", {})
                entry: dict[str, float] = books.setdefault(symbol, {})
                for source, target in {
                    "bid": "bid",
                    "best_bid": "bid",
                    "bid_price": "bid",
                    "b": "bid",
                    "ask": "ask",
                    "best_ask": "ask",
                    "ask_price": "ask",
                    "a": "ask",
                    "bid_qty": "bid_qty",
                    "ask_qty": "ask_qty",
                    "bid_size": "bid_qty",
                    "ask_size": "ask_qty",
                }.items():
                    value = self._coerce_float(event.get(source))
                    if value is not None:
                        entry[target] = value
            return

        if event_type in {"trade", "last_trade"}:
            symbol = str(
                event.get("symbol") or event.get("product_id") or event.get("s") or ""
            ).upper()
            price = self._coerce_float(event.get("price") or event.get("trade_price"))
            quantity = self._coerce_float(event.get("quantity") or event.get("size"))
            if symbol and price is not None:
                venue_state = self._market_state.setdefault(context.name, {})
                trades = venue_state.setdefault("trades", {})
                trade_payload: dict[str, float] = {"price": price}
                if quantity is not None:
                    trade_payload["quantity"] = quantity
                trades[symbol] = trade_payload
            return

    @staticmethod
    def _map_stream_status(status: Any) -> OrderStatus | None:
        if status is None:
            return None
        raw = str(status).strip().lower()
        mapping = {
            "filled": OrderStatus.FILLED,
            "fill": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "partial_fill": OrderStatus.PARTIALLY_FILLED,
            "new": OrderStatus.OPEN,
            "open": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return mapping.get(raw)

    def _apply_stream_status(
        self,
        context: _VenueContext,
        order_id: str,
        status: OrderStatus | None,
        cumulative: float | None,
        average_price: float | None,
    ) -> None:
        if not order_id:
            return
        orders = getattr(context.oms, "_orders", {})
        original = orders.get(order_id)
        if original is None:
            return
        updated = replace(original)
        if cumulative is not None and cumulative >= 0:
            updated.filled_quantity = min(float(updated.quantity), float(cumulative))
        if average_price is not None and average_price > 0:
            updated.average_price = average_price
        if status is OrderStatus.CANCELLED:
            updated.cancel()
        elif status is not None:
            updated.status = status
        try:
            context.oms.sync_remote_state(updated)
        except LookupError:
            return
        if cumulative is not None:
            self._last_reported_fill[order_id] = float(updated.filled_quantity)
        if not updated.is_active:
            self._order_connector.pop(order_id, None)
            self._last_reported_fill.pop(order_id, None)

    def _normalise_balances(self, balances: Any) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        items: Iterable[Any]
        if isinstance(balances, Mapping):
            items = balances.values()
        elif isinstance(balances, (list, tuple)):
            items = balances
        else:
            return result
        for entry in items:
            if not isinstance(entry, Mapping):
                continue
            asset = (
                str(
                    entry.get("asset")
                    or entry.get("currency")
                    or entry.get("symbol")
                    or entry.get("code")
                    or entry.get("a")
                    or ""
                )
                .strip()
                .upper()
            )
            if not asset:
                continue
            free = self._extract_balance_value(
                entry, "free", "available", "available_balance"
            )
            locked = self._extract_balance_value(
                entry, "locked", "hold", "locked_balance"
            )
            delta = self._extract_balance_value(
                entry, "delta", "change", "balance_delta"
            )
            payload: dict[str, float] = {}
            if free is not None:
                payload["free"] = free
            if locked is not None:
                payload["locked"] = locked
            if delta is not None:
                payload["delta"] = delta
            total = self._coerce_float(entry.get("balance") or entry.get("total"))
            if total is None and free is not None and locked is not None:
                total = free + locked
            if total is not None:
                payload["total"] = total
            if payload:
                result[asset] = payload
        return result

    def _extract_balance_value(
        self, entry: Mapping[str, Any], *keys: str
    ) -> float | None:
        for key in keys:
            value = entry.get(key)
            if isinstance(value, Mapping):
                candidate = value.get("value")
                if candidate is not None:
                    value = candidate
            amount = self._coerce_float(value)
            if amount is not None:
                return amount
        return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            # Periodically persist OMS snapshot
            self._persist_oms_snapshot_if_needed()

            if (
                self._risk_manager.kill_switch.is_triggered()
                and not self._kill_notified
            ):
                reason = self._risk_manager.kill_switch.reason
                self._logger.error(
                    "Kill-switch triggered, stopping live loop",
                    extra={"event": "live_loop.kill_switch", "reason": reason},
                )
                self.on_kill_switch.emit(reason)
                self._kill_notified = True
                self._cancel_all_outstanding(reason="kill-switch")
                self._stop.set()
                break

            for context in self._contexts.values():
                try:
                    positions = context.connector.get_positions()
                    self._emit_position_snapshot(context.name, positions)
                    self._reconnect_backoff_attempts[context.name] = 0
                except Exception as exc:
                    attempt = self._reconnect_backoff_attempts.get(context.name, 0) + 1
                    self._reconnect_backoff_attempts[context.name] = attempt
                    # Use full jitter backoff
                    delay = _full_jitter_backoff(
                        self._config.heartbeat_interval,
                        attempt - 1,
                        self._config.max_backoff,
                    )
                    self._logger.warning(
                        "Heartbeat failure",
                        extra={
                            "event": "live_loop.heartbeat_retry",
                            "venue": context.name,
                            "attempt": attempt,
                            "delay": delay,
                            "error": str(exc),
                        },
                    )
                    self.on_reconnect.emit(context.name, attempt, delay, exc)
                    if self._stop.wait(delay):
                        return
                    try:
                        credentials = None
                        if self._config.credentials is not None:
                            credentials = self._config.credentials.get(context.name)
                        context.connector.connect(credentials)
                        self._logger.info(
                            "Reconnected after heartbeat failure",
                            extra={
                                "event": "live_loop.reconnected",
                                "venue": context.name,
                                "attempt": attempt,
                            },
                        )
                        self._reconnect_backoff_attempts[context.name] = 0
                        self.on_reconnect.emit(context.name, 0, 0.0, None)
                        # After reconnect, reconcile open orders
                        self._reconcile_open_orders(context)
                    except Exception as reconnect_exc:  # pragma: no cover - defensive
                        self._logger.exception(
                            "Reconnection attempt failed",
                            extra={
                                "event": "live_loop.reconnect_error",
                                "venue": context.name,
                                "error": str(reconnect_exc),
                            },
                        )

            if self._stop.wait(self._config.heartbeat_interval):
                return

    def _cancel_all_outstanding(self, *, reason: str | None = None) -> None:
        """Best-effort cancellation sweep for all active orders."""

        for context in self._contexts.values():
            outstanding = list(context.oms.outstanding())
            for order in outstanding:
                if order.order_id is None:
                    continue
                try:
                    cancelled = context.oms.cancel(order.order_id)
                except Exception as exc:  # pragma: no cover - defensive
                    self._logger.exception(
                        "Failed to cancel order during sweep",
                        extra={
                            "event": "live_loop.cancel_sweep_error",
                            "venue": context.name,
                            "order_id": order.order_id,
                            "reason": reason,
                            "error": str(exc),
                        },
                    )
                    continue

                if cancelled:
                    self._order_connector.pop(order.order_id, None)
                    self._last_reported_fill.pop(order.order_id, None)
                    self._logger.warning(
                        "Outstanding order cancelled",
                        extra={
                            "event": "live_loop.cancel_sweep",
                            "venue": context.name,
                            "order_id": order.order_id,
                            "reason": reason,
                        },
                    )
                else:
                    self._logger.warning(
                        "Cancellation sweep rejected order",
                        extra={
                            "event": "live_loop.cancel_sweep_rejected",
                            "venue": context.name,
                            "order_id": order.order_id,
                            "reason": reason,
                        },
                    )

    def _emit_position_snapshot(
        self, venue: str, positions: Iterable[Mapping[str, object]]
    ) -> None:
        positions_list = list(positions)
        for position in positions_list:
            symbol = str(
                position.get("symbol") or position.get("instrument") or "unknown"
            )
            try:
                quantity = float(position.get("qty") or position.get("quantity") or 0.0)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                quantity = 0.0
            try:
                self._metrics.set_open_positions(venue, symbol, quantity)
            except Exception:  # pragma: no cover - defensive
                self._logger.exception(
                    "Failed to record position metric",
                    extra={
                        "event": "live_loop.position_metric_error",
                        "venue": venue,
                        "symbol": symbol,
                    },
                )

        self.on_position_snapshot.emit(venue, positions_list)


__all__ = ["LiveExecutionLoop", "LiveLoopConfig"]
