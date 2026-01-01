# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Order management system with persistence and idempotent queues."""

from __future__ import annotations

import concurrent.futures
import json
import time
from collections import deque
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Mapping, MutableMapping

from core.utils.metrics import get_metrics_collector
from domain import Order, OrderSide, OrderStatus
from interfaces.execution import RiskController

from .audit import ExecutionAuditLogger, get_execution_audit_logger
from .compliance import ComplianceMonitor, ComplianceReport, ComplianceViolation
from .connectors import ExecutionConnector, OrderError, TransientOrderError
from .order_ledger import OrderLedger
from .order_lifecycle import OrderEvent, OrderLifecycle

DEFAULT_LEDGER_PATH = Path("observability/audit/order-ledger.jsonl")


@dataclass(slots=True)
class QueuedOrder:
    """Order request paired with its idempotency key."""

    correlation_id: str
    order: Order
    attempts: int = 0
    last_error: str | None = None


@dataclass(slots=True)
class OMSConfig:
    """Configuration for :class:`OrderManagementSystem`."""

    state_path: Path
    auto_persist: bool = True
    max_retries: int = 3
    backoff_seconds: float = 0.0
    ledger_path: Path | None = DEFAULT_LEDGER_PATH
    request_timeout: float | None = None
    pre_trade_timeout: float | None = 0.25

    def __post_init__(self) -> None:
        if not isinstance(self.state_path, Path):
            object.__setattr__(self, "state_path", Path(self.state_path))
        if self.max_retries < 1:
            object.__setattr__(self, "max_retries", 1)
        if self.backoff_seconds < 0.0:
            object.__setattr__(self, "backoff_seconds", 0.0)
        if self.request_timeout is not None and self.request_timeout <= 0:
            object.__setattr__(self, "request_timeout", None)
        if self.pre_trade_timeout is not None and self.pre_trade_timeout <= 0:
            object.__setattr__(self, "pre_trade_timeout", None)
        ledger_path = self.ledger_path
        if ledger_path is not None and not isinstance(ledger_path, Path):
            ledger_path = Path(ledger_path)
        if ledger_path == DEFAULT_LEDGER_PATH:
            ledger_path = (
                self.state_path.parent / f"{self.state_path.stem}_ledger.jsonl"
            )
        if ledger_path is not None:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "ledger_path", ledger_path)


class OrderManagementSystem:
    """Queue-based OMS with state recovery."""

    def __init__(
        self,
        connector: ExecutionConnector,
        risk_controller: RiskController,
        config: OMSConfig,
        *,
        compliance_monitor: ComplianceMonitor | None = None,
        audit_logger: ExecutionAuditLogger | None = None,
        lifecycle: OrderLifecycle | None = None,
        risk_compliance: object | None = None,
        circuit_breaker: object | None = None,
    ) -> None:
        self.connector = connector
        self.risk = risk_controller
        self.config = config
        self._compliance = compliance_monitor
        self._risk_compliance = risk_compliance
        self._circuit_breaker = circuit_breaker
        self._queue: Deque[QueuedOrder] = deque()
        self._orders: MutableMapping[str, Order] = {}
        self._processed: Dict[str, str] = {}
        self._correlations: Dict[str, str] = {}
        self._metrics = get_metrics_collector()
        self._ack_timestamps: Dict[str, datetime] = {}
        self._pending: Dict[str, Order] = {}
        self._audit = audit_logger or get_execution_audit_logger()
        self._active_orders: Dict[str, Order] = {}
        self._active_cache: tuple[Order, ...] = ()
        self._active_cache_dirty = False
        self._fingerprints: Dict[str, str] = {}
        self._broker_lookup: Dict[str, str] = {}
        self._lifecycle = lifecycle
        self._lifecycle_sequences: Dict[str, int] = {}
        ledger_path = self.config.ledger_path
        self._ledger = OrderLedger(ledger_path) if ledger_path is not None else None
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    def _state_payload(self) -> dict:
        return {
            "orders": [self._serialize_order(order) for order in self._orders.values()],
            "queue": [
                {
                    "correlation_id": item.correlation_id,
                    "order": self._serialize_order(item.order),
                    "attempts": item.attempts,
                    "last_error": item.last_error,
                }
                for item in self._queue
            ],
            "processed": self._processed,
            "correlations": self._correlations,
            "fingerprints": self._fingerprints,
            "lifecycle_sequences": self._lifecycle_sequences,
        }

    def _persist_state(self) -> None:
        if not self.config.auto_persist:
            return
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._state_payload(), indent=2, sort_keys=True))

    def _load_state(self) -> None:
        path = self.config.state_path
        payload: Mapping[str, object] | None = None
        source = "state_file"
        if path.exists():
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError:
                payload = None
        if payload is None and self._ledger is not None:
            payload = self._ledger.latest_state()
            source = "ledger"
        if payload is None:
            return
        self._apply_state_snapshot(payload, source=source)

    def _apply_state_snapshot(
        self, payload: Mapping[str, object], *, source: str = "manual"
    ) -> None:
        self._orders = {
            order.order_id: order
            for order in self._restore_orders(payload.get("orders", []))
            if order.order_id
        }
        self._queue = deque(
            QueuedOrder(
                item["correlation_id"],
                self._restore_order(item["order"]),
                int(item.get("attempts", 0)),
                (
                    str(item.get("last_error"))
                    if item.get("last_error") is not None
                    else None
                ),
            )
            for item in payload.get("queue", [])
        )
        self._processed = {
            str(k): str(v) for k, v in payload.get("processed", {}).items()
        }
        self._correlations = {
            str(k): str(v) for k, v in payload.get("correlations", {}).items()
        }
        self._pending = {item.correlation_id: item.order for item in self._queue}
        raw_fingerprints = payload.get("fingerprints")
        if isinstance(raw_fingerprints, Mapping):
            self._fingerprints = {
                str(key): str(value) for key, value in raw_fingerprints.items()
            }
        else:
            self._fingerprints = {}
        if not self._fingerprints:
            for item in self._queue:
                self._fingerprints[item.correlation_id] = self._fingerprint(item.order)
            for correlation, order_id in self._processed.items():
                order = self._orders.get(order_id)
                if order is not None:
                    self._fingerprints[correlation] = self._fingerprint(order)
        raw_sequences = payload.get("lifecycle_sequences")
        if isinstance(raw_sequences, Mapping):
            self._lifecycle_sequences = {
                str(key): int(value) for key, value in raw_sequences.items()
            }
        else:
            self._lifecycle_sequences = {}
        self._active_orders = {
            order_id: order
            for order_id, order in self._orders.items()
            if order.is_active
        }
        self._active_cache = tuple(self._active_orders.values())
        self._active_cache_dirty = False
        self._broker_lookup = {
            order.broker_order_id: order_id
            for order_id, order in self._orders.items()
            if order.broker_order_id
        }
        if self._ledger is not None:
            self._record_ledger_event("state_restored", metadata={"source": source})

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def _ensure_lifecycle_sequence(self, order_id: str) -> None:
        if not order_id or order_id in self._lifecycle_sequences:
            return
        sequence = 0
        lifecycle = self._lifecycle
        if lifecycle is not None:
            try:
                history = lifecycle.history(order_id)
            except Exception:  # pragma: no cover - defensive guard
                history = []
            for transition in history:
                if transition.event not in (
                    OrderEvent.FILL_PARTIAL,
                    OrderEvent.FILL_FINAL,
                ):
                    continue
                parts = transition.correlation_id.rsplit(":", 1)
                if len(parts) != 2:
                    continue
                try:
                    candidate = int(parts[1])
                except ValueError:
                    continue
                if candidate > sequence:
                    sequence = candidate
        self._lifecycle_sequences[order_id] = sequence

    def _next_fill_sequence(self, order_id: str) -> int:
        self._ensure_lifecycle_sequence(order_id)
        sequence = self._lifecycle_sequences.get(order_id, 0) + 1
        self._lifecycle_sequences[order_id] = sequence
        return sequence

    def _record_lifecycle_event(
        self,
        order: Order,
        event: OrderEvent,
        *,
        base_correlation: str | None,
        metadata: Mapping[str, object] | None = None,
        correlation_override: str | None = None,
        sequence_hint: int | None = None,
    ) -> None:
        lifecycle = self._lifecycle
        if lifecycle is None:
            return
        order_id = order.order_id or base_correlation or order.broker_order_id
        if order_id is None:
            return
        base = base_correlation or order_id
        correlation = correlation_override
        if correlation is None:
            suffix = event.value
            if sequence_hint is not None:
                suffix = f"{suffix}:{sequence_hint}"
            correlation = f"{base}:{suffix}"
        payload: Dict[str, object] = {
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": float(order.quantity),
            "filled_quantity": float(order.filled_quantity),
            "status": order.status.value,
        }
        if order.iceberg_visible is not None:
            payload["iceberg_visible"] = float(order.iceberg_visible)
        if order.broker_order_id:
            payload["broker_order_id"] = order.broker_order_id
        if order.average_price is not None:
            payload["average_price"] = float(order.average_price)
        if metadata:
            payload.update(metadata)
        lifecycle.apply(order_id, event, correlation_id=correlation, metadata=payload)

    # ------------------------------------------------------------------
    # Serialization helpers
    def _fingerprint(self, order: Order) -> str:
        payload: Dict[str, Any] = {
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "order_type": order.order_type.value,
            "price": None if order.price is None else float(order.price),
            "stop_price": None if order.stop_price is None else float(order.stop_price),
            "iceberg_visible": (
                None if order.iceberg_visible is None else float(order.iceberg_visible)
            ),
        }
        metadata = getattr(order, "metadata", None)
        if metadata is not None:
            payload["metadata"] = metadata
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _serialize_order(order: Order) -> dict:
        data = order.to_dict()
        data["side"] = order.side.value
        data["order_type"] = order.order_type.value
        data["status"] = order.status.value
        return data

    @staticmethod
    def _restore_orders(serialized: Iterable[dict]) -> Iterable[Order]:
        return [OrderManagementSystem._restore_order(item) for item in serialized]

    @staticmethod
    def _restore_order(data: MutableMapping[str, object]) -> Order:
        created_at = datetime.fromisoformat(str(data["created_at"]))
        order = Order(
            symbol=str(data["symbol"]),
            side=str(data["side"]),
            quantity=float(data["quantity"]),
            price=float(data["price"]) if data.get("price") is not None else None,
            order_type=str(data.get("order_type", "market")),
            stop_price=(
                float(data["stop_price"])
                if data.get("stop_price") is not None
                else None
            ),
            iceberg_visible=(
                float(data["iceberg_visible"])
                if data.get("iceberg_visible") is not None
                else None
            ),
            order_id=str(data.get("order_id")) if data.get("order_id") else None,
            broker_order_id=(
                str(data.get("broker_order_id"))
                if data.get("broker_order_id")
                else None
            ),
            status=str(data.get("status", "pending")),
            filled_quantity=float(data.get("filled_quantity", 0.0)),
            average_price=(
                float(data["average_price"])
                if data.get("average_price") is not None
                else None
            ),
            rejection_reason=(
                str(data.get("rejection_reason"))
                if data.get("rejection_reason")
                else None
            ),
            created_at=created_at,
        )
        if data.get("updated_at"):
            object.__setattr__(
                order, "updated_at", datetime.fromisoformat(str(data["updated_at"]))
            )
        return order

    # ------------------------------------------------------------------
    # Queue operations
    def submit(self, order: Order, *, correlation_id: str) -> Order:
        """Submit an order, enforcing idempotency with correlation IDs."""

        fingerprint = self._fingerprint(order)
        existing_fp = self._fingerprints.get(correlation_id)
        if existing_fp is not None and existing_fp != fingerprint:
            raise ValueError("Correlation ID reused with a different order payload")
        if correlation_id in self._processed:
            order_id = self._processed[correlation_id]
            stored = self._orders[order_id]
            if existing_fp is None:
                self._fingerprints[correlation_id] = self._fingerprint(stored)
            return stored
        if correlation_id in self._pending:
            if existing_fp is None:
                self._fingerprints[correlation_id] = fingerprint
            return self._pending[correlation_id]
        self._fingerprints[correlation_id] = fingerprint

        try:
            if self._compliance is not None:
                report = None
                try:
                    report = self._run_pre_trade_check(
                        "compliance",
                        self._compliance.check,
                        order.symbol,
                        order.quantity,
                        order.price,
                    )
                except ComplianceViolation as exc:
                    report = exc.report
                    self._metrics.record_compliance_check(
                        order.symbol,
                        "blocked",
                        () if report is None else report.violations,
                    )
                    self._emit_compliance_audit(order, correlation_id, report, str(exc))
                    self._record_ledger_event(
                        "compliance_blocked",
                        order=order,
                        correlation_id=correlation_id,
                        metadata={
                            "violations": [] if report is None else report.violations,
                            "error": str(exc),
                        },
                    )
                    raise
                except TimeoutError as exc:
                    order.reject("PRE_TRADE_TIMEOUT:compliance")
                    self._metrics.record_compliance_check(
                        order.symbol, "timeout", ()
                    )
                    self._emit_compliance_audit(order, correlation_id, None, str(exc))
                    self._record_ledger_event(
                        "compliance_timeout",
                        order=order,
                        correlation_id=correlation_id,
                        metadata={"error": str(exc)},
                    )
                    raise ComplianceViolation("Compliance check timed out") from exc
                status = "passed" if report is None or report.is_clean() else "warning"
                if report is not None:
                    self._metrics.record_compliance_check(
                        order.symbol,
                        "blocked" if report.blocked else status,
                        report.violations,
                    )
                    self._emit_compliance_audit(order, correlation_id, report, None)
                    if report.blocked:
                        self._record_ledger_event(
                            "compliance_blocked",
                            order=order,
                            correlation_id=correlation_id,
                            metadata={
                                "violations": report.violations,
                                "blocked": True,
                            },
                        )
                        raise ComplianceViolation(
                            "Compliance check blocked order", report=report
                        )

            if self._circuit_breaker is not None:
                if not self._circuit_breaker.can_execute():
                    reason = "Circuit breaker is OPEN"
                    last_trip = self._circuit_breaker.get_last_trip_reason()
                    if last_trip:
                        reason = f"{reason}: {last_trip}"
                    ttl = self._circuit_breaker.get_time_until_recovery()
                    order.reject(reason)
                    self._record_ledger_event(
                        "risk_blocked",
                        order=order,
                        correlation_id=correlation_id,
                        metadata={
                            "reason": reason,
                            "circuit_state": "open",
                            "ttl_seconds": ttl,
                        },
                    )
                    self._emit_risk_audit(
                        order, correlation_id, reason, {"ttl_seconds": ttl}
                    )
                    raise ComplianceViolation(reason)

            if self._risk_compliance is not None:
                reference_price = (
                    order.price
                    if order.price is not None
                    else max(order.average_price or 0.0, 1.0)
                )

                positions = {}
                gross_exposure = 0.0
                equity = 0.0
                peak_equity = 0.0

                if hasattr(self.risk, "current_position"):
                    try:
                        positions = {
                            symbol: self.risk.current_position(symbol)
                            for symbol in [order.symbol]
                        }
                    except Exception:
                        pass

                if hasattr(self.risk, "_gross_notional"):
                    try:
                        gross_exposure = self.risk._gross_notional
                    except Exception:
                        pass

                if hasattr(self.risk, "_balance"):
                    try:
                        equity = self.risk._balance
                        peak_equity = getattr(self.risk, "_peak_equity", equity)
                    except Exception:
                        pass

                portfolio_state = {
                    "positions": positions,
                    "gross_exposure": gross_exposure,
                    "equity": equity,
                    "peak_equity": peak_equity,
                }
                market_data = {"price": reference_price}

                try:
                    risk_decision = self._run_pre_trade_check(
                        "risk_compliance",
                        self._risk_compliance.check_order,
                        order,
                        market_data,
                        portfolio_state,
                    )
                except TimeoutError as exc:
                    order.reject("PRE_TRADE_TIMEOUT:risk_compliance")
                    self._record_ledger_event(
                        "risk_blocked",
                        order=order,
                        correlation_id=correlation_id,
                        metadata={
                            "reason": str(exc),
                            "timeout": True,
                        },
                    )
                    self._emit_risk_audit(
                        order, correlation_id, str(exc), {"timeout": True}
                    )
                    raise ComplianceViolation("Risk compliance timed out") from exc

                if not risk_decision.allowed:
                    order.reject("RISK_LIMIT_BREACH")
                    self._record_ledger_event(
                        "risk_blocked",
                        order=order,
                        correlation_id=correlation_id,
                        metadata={
                            "reasons": risk_decision.reasons,
                            "breached_limits": risk_decision.breached_limits,
                        },
                    )
                    self._emit_risk_audit(
                        order,
                        correlation_id,
                        "; ".join(risk_decision.reasons),
                        risk_decision.breached_limits,
                    )

                    if self._circuit_breaker is not None:
                        for reason in risk_decision.reasons:
                            self._circuit_breaker.record_risk_breach(reason)

                    raise ComplianceViolation(
                        f"Risk limit breach: {'; '.join(risk_decision.reasons)}"
                    )

            reference_price = (
                order.price
                if order.price is not None
                else max(order.average_price or 0.0, 1.0)
            )
            try:
                self._run_pre_trade_check(
                    "risk_validation",
                    self.risk.validate_order,
                    order.symbol,
                    order.side.value,
                    order.quantity,
                    reference_price,
                )
            except TimeoutError as exc:
                order.reject("PRE_TRADE_TIMEOUT:risk_validation")
                self._record_ledger_event(
                    "risk_blocked",
                    order=order,
                    correlation_id=correlation_id,
                    metadata={"reason": str(exc), "timeout": True},
                )
                self._emit_risk_audit(
                    order, correlation_id, str(exc), {"timeout": True}
                )
                raise ComplianceViolation("Risk validation timed out") from exc
        except Exception:
            self._fingerprints.pop(correlation_id, None)
            raise

        queued_order = QueuedOrder(correlation_id, order)
        self._queue.append(queued_order)
        self._pending[correlation_id] = order
        self._persist_state()
        self._record_ledger_event(
            "order_queued",
            order=order,
            correlation_id=correlation_id,
        )
        return order

    def _emit_compliance_audit(
        self,
        order: Order,
        correlation_id: str,
        report: ComplianceReport | None,
        error: str | None,
    ) -> None:
        payload = {
            "event": "compliance_check",
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "price": None if order.price is None else float(order.price),
            "correlation_id": correlation_id,
            "error": error,
        }
        if report is not None:
            payload["report"] = report.to_dict()
            if report.blocked:
                status = "blocked"
            elif report.is_clean():
                status = "passed"
            else:
                status = "warning"
        else:
            payload["report"] = None
            status = "blocked" if error else "passed"
        payload["status"] = status
        self._audit.emit(payload)

    def _emit_risk_audit(
        self,
        order: Order,
        correlation_id: str,
        reason: str,
        breached_limits: dict,
    ) -> None:
        """Emit structured audit log for risk rejection."""
        payload = {
            "event": "risk_check",
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "price": None if order.price is None else float(order.price),
            "order_id": order.order_id,
            "correlation_id": correlation_id,
            "status": "blocked",
            "reason": reason,
            "breached_limits": breached_limits,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._audit.emit(payload)

    def _run_pre_trade_check(
        self, label: str, func: Callable[..., object], *args: object, **kwargs: object
    ) -> object:
        timeout = self.config.pre_trade_timeout
        if not timeout:
            return func(*args, **kwargs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"{label} check exceeded {timeout:.3f}s timeout"
                ) from exc

    def _place_order_with_timeout(self, order: Order, correlation_id: str) -> Order:
        timeout = self.config.request_timeout
        if not timeout:
            return self.connector.place_order(order, idempotency_key=correlation_id)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.connector.place_order,
                order,
                idempotency_key=correlation_id,
            )
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Connector request exceeded {timeout:.3f}s timeout"
                ) from exc

    def process_next(self) -> Order:
        if not self._queue:
            raise LookupError("No orders pending")
        item = self._queue[0]
        retryable: tuple[type[Exception], ...] = (
            TransientOrderError,
            TimeoutError,
            ConnectionError,
        )
        max_retries = max(1, int(self.config.max_retries))
        while True:
            item.attempts += 1
            try:
                start = time.perf_counter()
                submitted = self._place_order_with_timeout(
                    item.order, item.correlation_id
                )
                ack_latency = time.perf_counter() - start
            except retryable as exc:
                item.last_error = str(exc)
                if item.attempts >= max_retries:
                    self._queue.popleft()
                    self._pending.pop(item.correlation_id, None)
                    item.order.reject(str(exc))
                    self._record_lifecycle_event(
                        item.order,
                        OrderEvent.REJECT,
                        base_correlation=item.correlation_id,
                        metadata={
                            "reason": str(exc),
                            "attempts": item.attempts,
                            "transient": True,
                        },
                    )
                    self._persist_state()
                    self._record_ledger_event(
                        "order_rejected",
                        order=item.order,
                        correlation_id=item.correlation_id,
                        metadata={
                            "reason": str(exc),
                            "attempts": item.attempts,
                            "transient": True,
                        },
                    )
                    return item.order
                backoff = max(0.0, float(self.config.backoff_seconds))
                self._persist_state()
                self._record_ledger_event(
                    "order_retry_scheduled",
                    order=item.order,
                    correlation_id=item.correlation_id,
                    metadata={
                        "attempts": item.attempts,
                        "error": str(exc),
                        "backoff_seconds": backoff * item.attempts,
                    },
                )
                if backoff:
                    time.sleep(backoff * item.attempts)
                continue
            except OrderError as exc:
                self._queue.popleft()
                self._pending.pop(item.correlation_id, None)
                item.order.reject(str(exc))
                self._record_lifecycle_event(
                    item.order,
                    OrderEvent.REJECT,
                    base_correlation=item.correlation_id,
                    metadata={"reason": str(exc)},
                )
                self._persist_state()
                self._record_ledger_event(
                    "order_rejected",
                    order=item.order,
                    correlation_id=item.correlation_id,
                    metadata={"reason": str(exc)},
                )
                return item.order
            break
        self._queue.popleft()
        self._pending.pop(item.correlation_id, None)
        if submitted.order_id is None:
            raise RuntimeError("Connector returned order without ID")
        self._orders[submitted.order_id] = submitted
        self._processed[item.correlation_id] = submitted.order_id
        self._correlations[submitted.order_id] = item.correlation_id
        if submitted.broker_order_id:
            self._broker_lookup[submitted.broker_order_id] = submitted.order_id
        self._ensure_lifecycle_sequence(submitted.order_id)
        base_correlation = item.correlation_id
        self._record_lifecycle_event(
            submitted,
            OrderEvent.SUBMIT,
            base_correlation=base_correlation,
            metadata={"attempts": item.attempts},
        )
        self._record_lifecycle_event(
            submitted,
            OrderEvent.ACK,
            base_correlation=base_correlation,
            metadata={"attempts": item.attempts, "ack_latency": ack_latency},
        )
        fingerprint = self._fingerprints.get(item.correlation_id)
        updated_fingerprint = self._fingerprint(submitted)
        if fingerprint != updated_fingerprint:
            self._fingerprints[item.correlation_id] = updated_fingerprint
        self._update_active_order(submitted.order_id, submitted)
        if self._metrics.enabled:
            exchange = getattr(
                self.connector, "name", self.connector.__class__.__name__.lower()
            )
            self._metrics.record_order_ack_latency(
                exchange, submitted.symbol, max(0.0, ack_latency)
            )
            self._ack_timestamps[submitted.order_id] = datetime.now(timezone.utc)
        self._persist_state()
        self._record_ledger_event(
            "order_acknowledged",
            order=submitted,
            correlation_id=item.correlation_id,
            metadata={"attempts": item.attempts, "ack_latency": ack_latency},
        )
        return submitted

    def process_all(self) -> None:
        while self._queue:
            self.process_next()

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def cancel(self, order_id: str) -> bool:
        if order_id not in self._orders:
            return False
        cancelled = self.connector.cancel_order(order_id)
        if cancelled:
            order = self._orders[order_id]
            order.cancel()
            self._ack_timestamps.pop(order_id, None)
            self._update_active_order(order_id, order)
            self._record_lifecycle_event(
                order,
                OrderEvent.CANCEL,
                base_correlation=self._correlations.get(order_id),
            )
            self._lifecycle_sequences.pop(order_id, None)
            self._persist_state()
            self._record_ledger_event(
                "order_cancelled",
                order=self._orders[order_id],
                correlation_id=self._correlations.get(order_id),
            )
        return cancelled

    def register_fill(
        self,
        order_id: str,
        quantity: float,
        price: float,
        correlation_id: str | None = None,
    ) -> Order:
        order = self._orders[order_id]
        previous_status = order.status
        previous_filled = order.filled_quantity
        order.record_fill(quantity, price)
        self._ensure_lifecycle_sequence(order_id)
        self._update_active_order(order_id, order)
        self.risk.register_fill(order.symbol, order.side.value, quantity, price)
        if self._metrics.enabled:
            exchange = getattr(
                self.connector, "name", self.connector.__class__.__name__.lower()
            )
            now = datetime.now(timezone.utc)
            ack_ts = self._ack_timestamps.get(order_id)
            if ack_ts is not None:
                latency = max(0.0, (now - ack_ts).total_seconds())
                self._metrics.record_order_fill_latency(exchange, order.symbol, latency)
            signal_origin = getattr(order, "created_at", None)
            signal_latency = None
            if isinstance(signal_origin, datetime):
                if signal_origin.tzinfo is None:
                    signal_origin = signal_origin.replace(tzinfo=timezone.utc)
                signal_latency = max(0.0, (now - signal_origin).total_seconds())
            if signal_latency is not None:
                metadata = getattr(order, "metadata", None)
                strategy = "unspecified"
                if isinstance(metadata, dict):
                    strategy = str(metadata.get("strategy") or strategy)
                else:
                    strategy = str(getattr(order, "strategy", strategy))
                self._metrics.record_signal_to_fill_latency(
                    strategy,
                    exchange,
                    order.symbol,
                    signal_latency,
                )
            self._ack_timestamps.pop(order_id, None)
        base_correlation = self._correlations.get(order_id)
        sequence = self._next_fill_sequence(order_id)
        sequence_hint = None if correlation_id is not None else sequence
        event = (
            OrderEvent.FILL_FINAL
            if order.status is OrderStatus.FILLED
            else OrderEvent.FILL_PARTIAL
        )
        metadata: Dict[str, object] = {
            "fill_quantity": float(quantity),
            "fill_price": float(price),
            "cumulative_filled": float(order.filled_quantity),
        }
        if previous_status is not order.status:
            metadata["previous_status"] = previous_status.value
        if order.status is OrderStatus.FILLED:
            metadata["completed"] = True
        if order.filled_quantity > previous_filled + 1e-9:
            metadata["delta_filled"] = float(order.filled_quantity - previous_filled)
        self._record_lifecycle_event(
            order,
            event,
            base_correlation=base_correlation,
            metadata=metadata,
            correlation_override=correlation_id,
            sequence_hint=sequence_hint,
        )
        if order.status is OrderStatus.FILLED:
            self._lifecycle_sequences.pop(order_id, None)
        self._persist_state()
        self._record_ledger_event(
            "order_fill_recorded",
            order=order,
            correlation_id=self._correlations.get(order_id),
            metadata={"fill_quantity": quantity, "fill_price": price},
        )
        return order

    def sync_remote_state(self, order: Order) -> Order:
        """Synchronize terminal state reported by the venue without reissuing API calls."""

        if order.order_id is None:
            raise ValueError("order must include an order_id to sync state")

        stored = self._orders.get(order.order_id)
        if stored is None:
            raise LookupError(f"Unknown order_id: {order.order_id}")

        previous_status = stored.status
        previous_filled = stored.filled_quantity
        stored.status = OrderStatus(order.status)
        stored.filled_quantity = float(order.filled_quantity)
        stored.average_price = (
            float(order.average_price) if order.average_price is not None else None
        )
        stored.rejection_reason = order.rejection_reason
        stored.updated_at = getattr(order, "updated_at", stored.updated_at)

        if not stored.is_active:
            self._ack_timestamps.pop(order.order_id, None)
        self._update_active_order(order.order_id, stored)
        if stored.broker_order_id:
            self._broker_lookup[stored.broker_order_id] = stored.order_id

        base_correlation = self._correlations.get(order.order_id)
        if (
            stored.status is OrderStatus.CANCELLED
            and previous_status is not OrderStatus.CANCELLED
        ):
            self._record_lifecycle_event(
                stored,
                OrderEvent.CANCEL,
                base_correlation=base_correlation,
                metadata={"source": "sync_remote_state"},
            )
            self._lifecycle_sequences.pop(order.order_id, None)
        elif (
            stored.status is OrderStatus.REJECTED
            and previous_status is not OrderStatus.REJECTED
        ):
            metadata: Dict[str, object] = {"source": "sync_remote_state"}
            if stored.rejection_reason:
                metadata["reason"] = stored.rejection_reason
            self._record_lifecycle_event(
                stored,
                OrderEvent.REJECT,
                base_correlation=base_correlation,
                metadata=metadata,
            )
            self._lifecycle_sequences.pop(order.order_id, None)
        else:
            if stored.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                if stored.filled_quantity > previous_filled + 1e-9 or (
                    stored.status is OrderStatus.FILLED
                    and previous_status is not OrderStatus.FILLED
                ):
                    self._ensure_lifecycle_sequence(order.order_id)
                    sequence = self._next_fill_sequence(order.order_id)
                    fill_event = (
                        OrderEvent.FILL_FINAL
                        if stored.status is OrderStatus.FILLED
                        else OrderEvent.FILL_PARTIAL
                    )
                    price_reference = (
                        order.average_price
                        if order.average_price is not None
                        else order.price
                    )
                    metadata = {
                        "source": "sync_remote_state",
                        "cumulative_filled": float(stored.filled_quantity),
                        "delta_filled": float(
                            max(0.0, stored.filled_quantity - previous_filled)
                        ),
                    }
                    if price_reference is not None:
                        metadata["reference_price"] = float(price_reference)
                    self._record_lifecycle_event(
                        stored,
                        fill_event,
                        base_correlation=base_correlation,
                        metadata=metadata,
                        sequence_hint=sequence,
                    )
                    if stored.status is OrderStatus.FILLED:
                        self._lifecycle_sequences.pop(order.order_id, None)

        self._persist_state()
        self._record_ledger_event(
            "order_state_synced",
            order=stored,
            correlation_id=self._correlations.get(order.order_id),
        )
        return stored

    def reload(self) -> None:
        """Reload state from disk (used after restart)."""

        self._queue.clear()
        self._orders.clear()
        self._processed.clear()
        self._ack_timestamps.clear()
        self._pending.clear()
        self._correlations.clear()
        self._active_orders.clear()
        self._active_cache = ()
        self._active_cache_dirty = False
        self._fingerprints.clear()
        self._broker_lookup.clear()
        self._lifecycle_sequences.clear()
        self._load_state()
        self._record_ledger_event("state_reloaded", metadata={"source": "reload"})

    def _record_ledger_event(
        self,
        event: str,
        *,
        order: Order | Mapping[str, object] | None = None,
        correlation_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if self._ledger is None:
            return
        order_payload: Mapping[str, object] | None
        if isinstance(order, Order):
            order_payload = order.to_dict()
        else:
            order_payload = order
        self._ledger.append(
            event,
            order=order_payload,
            correlation_id=correlation_id,
            metadata=metadata,
            state_snapshot=self._state_payload(),
        )

    # ------------------------------------------------------------------
    # Recovery helpers
    def correlation_for(self, order_id: str) -> str | None:
        """Return the correlation ID originally associated with *order_id*."""

        return self._correlations.get(order_id)

    def order_for_broker(self, broker_order_id: str) -> Order | None:
        """Return the internal order correlated with *broker_order_id* if known."""

        order_id = self._broker_lookup.get(broker_order_id)
        if order_id is None:
            return None
        return self._orders.get(order_id)

    def adopt_open_order(
        self, order: Order, *, correlation_id: str | None = None
    ) -> None:
        """Adopt an externally recovered order into the OMS state."""

        if order.order_id is None:
            raise ValueError("order must have an order_id to be adopted")
        correlation = correlation_id or f"recovered-{order.order_id}"
        self._orders[order.order_id] = order
        self._processed[correlation] = order.order_id
        self._correlations[order.order_id] = correlation
        self._fingerprints[correlation] = self._fingerprint(order)
        if order.broker_order_id:
            self._broker_lookup[order.broker_order_id] = order.order_id
        self._ensure_lifecycle_sequence(order.order_id)
        lifecycle = self._lifecycle
        recorded_events: set[OrderEvent] = set()
        if lifecycle is not None:
            try:
                history = lifecycle.history(order.order_id)
            except Exception:  # pragma: no cover - defensive guard
                history = []
            recorded_events = {transition.event for transition in history}
        lifecycle_metadata = {"source": "adopt_open_order"}
        if OrderEvent.SUBMIT not in recorded_events:
            self._record_lifecycle_event(
                order,
                OrderEvent.SUBMIT,
                base_correlation=correlation,
                metadata=lifecycle_metadata,
            )
        if OrderEvent.ACK not in recorded_events:
            self._record_lifecycle_event(
                order,
                OrderEvent.ACK,
                base_correlation=correlation,
                metadata=lifecycle_metadata,
            )
        if order.status is OrderStatus.PARTIALLY_FILLED:
            sequence = self._next_fill_sequence(order.order_id)
            metadata = {
                "source": "adopt_open_order",
                "synthetic": True,
                "cumulative_filled": float(order.filled_quantity),
            }
            if order.average_price is not None:
                metadata["average_price"] = float(order.average_price)
            self._record_lifecycle_event(
                order,
                OrderEvent.FILL_PARTIAL,
                base_correlation=correlation,
                metadata=metadata,
                sequence_hint=sequence,
            )
        elif order.status is OrderStatus.FILLED:
            sequence = self._next_fill_sequence(order.order_id)
            metadata = {
                "source": "adopt_open_order",
                "synthetic": True,
                "cumulative_filled": float(order.filled_quantity),
                "completed": True,
            }
            if order.average_price is not None:
                metadata["average_price"] = float(order.average_price)
            self._record_lifecycle_event(
                order,
                OrderEvent.FILL_FINAL,
                base_correlation=correlation,
                metadata=metadata,
                sequence_hint=sequence,
            )
            self._lifecycle_sequences.pop(order.order_id, None)
        self._update_active_order(order.order_id, order)
        self._persist_state()
        hydrator = getattr(self.risk, "hydrate_positions", None)
        if callable(hydrator):
            side_sign = 1.0 if order.side is OrderSide.BUY else -1.0
            qty = float(order.filled_quantity)
            price = order.average_price or order.price or 0.0
            notional = abs(qty * price)
            hydrator({order.symbol: (side_sign * qty, notional)})

    def requeue_order(self, order_id: str, *, correlation_id: str | None = None) -> str:
        """Re-enqueue an order whose venue state was lost or invalidated."""

        if order_id not in self._orders:
            raise LookupError(f"Unknown order_id: {order_id}")
        original = self._orders.pop(order_id)
        self._update_active_order(order_id, None)
        if original.broker_order_id:
            self._broker_lookup.pop(original.broker_order_id, None)
        self._lifecycle_sequences.pop(order_id, None)
        correlation = correlation_id or self._correlations.pop(order_id, None)
        if correlation is None:
            correlation = f"requeue-{order_id}"
        self._processed.pop(correlation, None)
        resubmittable = replace(
            original,
            order_id=None,
            broker_order_id=None,
            status=OrderStatus.PENDING,
            filled_quantity=0.0,
            average_price=None,
            rejection_reason=None,
        )
        queued = QueuedOrder(correlation, resubmittable)
        self._queue.appendleft(queued)
        self._pending[correlation] = resubmittable
        self._fingerprints[correlation] = self._fingerprint(resubmittable)
        self._ack_timestamps.pop(order_id, None)
        self._persist_state()
        return correlation

    def outstanding(self) -> Iterable[Order]:
        if self._active_cache_dirty:
            self._active_cache = tuple(self._active_orders.values())
            self._active_cache_dirty = False
        return self._active_cache

    def latest_ledger_sequence(self) -> int | None:
        """Return the latest ledger event sequence number, or None if no ledger."""
        if self._ledger is None:
            return None
        latest = self._ledger.latest_event(verify=False)
        return latest.sequence if latest else 0

    def replay_ledger_from(
        self, sequence: int, *, verify: bool = True
    ) -> Iterable[Any]:  # Returns OrderLedgerEvent
        """Replay ledger events starting from given sequence, or empty if no ledger."""
        if self._ledger is None:
            return iter([])
        return self._ledger.replay_from(sequence, verify=verify)

    def _update_active_order(self, order_id: str | None, order: Order | None) -> None:
        if order_id is None:
            return
        if order is not None and order.is_active:
            current = self._active_orders.get(order_id)
            if current is not order:
                self._active_orders[order_id] = order
                self._active_cache_dirty = True
        else:
            if self._active_orders.pop(order_id, None) is not None:
                self._active_cache_dirty = True


__all__ = [
    "QueuedOrder",
    "OMSConfig",
    "OrderManagementSystem",
]
