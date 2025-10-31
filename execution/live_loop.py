# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Long-running execution loop orchestrating OMS, connectors, and risk controls."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping

from core.utils.metrics import get_metrics_collector
from domain import Order

from .connectors import ExecutionConnector, OrderError, TransientOrderError
from .oms import OMSConfig, OrderManagementSystem
from .risk import RiskManager
from .watchdog import Watchdog


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
        self._stop = threading.Event()
        self._activity = threading.Event()
        self._started = False
        self._kill_notified = False
        self._watchdog: Watchdog | None = None

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

    def submit_order(
        self,
        venue: str,
        order: Order,
        *,
        correlation_id: str,
        latency_trace: Mapping[str, Any] | None = None,
    ) -> Order:
        """Submit an order via the underlying OMS."""

        context = self._contexts.get(venue)
        if context is None:
            raise LookupError(f"Unknown venue: {venue}")
        submitted = context.oms.submit(
            order,
            correlation_id=correlation_id,
            latency_trace=latency_trace,
        )
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
        backoff = self._config.heartbeat_interval
        attempt = 0
        while not self._stop.is_set():
            try:
                context.connector.connect(credentials)
                self._logger.info(
                    "Connector initialised",
                    extra={"event": "live_loop.connector_ready", "venue": context.name},
                )
                return
            except Exception as exc:  # pragma: no cover - rarely triggered in tests
                attempt += 1
                delay = min(
                    self._config.max_backoff, backoff * max(1, 2 ** (attempt - 1))
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

    def _refresh_risk_state_from_connectors(self) -> None:
        hydrator = getattr(self._risk_manager, "hydrate_positions", None)
        if not callable(hydrator):
            return
        snapshot, sources, expected = self._build_risk_snapshot()
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
    ) -> tuple[dict[str, tuple[float, float]], int, int]:
        snapshot: dict[str, tuple[float, float]] = {}
        sources = 0
        expected = 0
        for context in self._contexts.values():
            connector = context.connector
            get_positions = getattr(connector, "get_positions", None)
            if not callable(get_positions):
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
                continue
            sources += 1
            for payload in positions:
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
                price_candidates = [p for p in (existing_price, new_price) if p is not None]
                if price_candidates:
                    combined_notional = max(
                        combined_notional,
                        abs(combined_qty) * price_candidates[-1],
                    )
                if abs(combined_qty) <= 1e-12:
                    snapshot.pop(symbol, None)
                else:
                    snapshot[symbol] = (combined_qty, combined_notional)
        return snapshot, sources, expected

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

    def _fill_polling_loop(self) -> None:
        while not self._stop.is_set():
            for context in self._contexts.values():
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
                        self._last_reported_fill[order.order_id] = (
                            remote.filled_quantity
                        )
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

            if self._stop.wait(self._config.fill_poll_interval):
                return

    def _heartbeat_loop(self) -> None:
        backoff_attempts: MutableMapping[str, int] = defaultdict(int)
        while not self._stop.is_set():
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
                    backoff_attempts[context.name] = 0
                except Exception as exc:
                    attempt = backoff_attempts[context.name] + 1
                    backoff_attempts[context.name] = attempt
                    delay = min(
                        self._config.max_backoff,
                        self._config.heartbeat_interval * (2 ** (attempt - 1)),
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
                        backoff_attempts[context.name] = 0
                        self.on_reconnect.emit(context.name, 0, 0.0, None)
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
