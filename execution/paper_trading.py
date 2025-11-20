"""Paper trading engine with latency simulation and telemetry analysis."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, MutableSequence, Protocol

from analytics.execution_quality import FillSample, implementation_shortfall
from domain import Order, OrderSide, OrderStatus

from .connectors import SimulatedExchangeConnector


@dataclass(slots=True, frozen=True)
class LatencySample:
    """Latency components for a simulated order lifecycle."""

    ack_delay: float
    fill_delay: float

    def __post_init__(self) -> None:
        if self.ack_delay < 0 or self.fill_delay < 0:
            raise ValueError("latency components must be non-negative")

    @property
    def total_delay(self) -> float:
        """Combined acknowledgement and fill delay."""

        return self.ack_delay + self.fill_delay


class LatencyModel(Protocol):
    """Protocol for latency sampling strategies."""

    def sample(self, order: Order) -> LatencySample:
        """Return the latency sample for ``order``."""


@dataclass(slots=True)
class DeterministicLatencyModel:
    """Latency model returning fixed delays for every order."""

    ack_delay: float = 0.0
    fill_delay: float = 0.0

    def __post_init__(self) -> None:
        if self.ack_delay < 0 or self.fill_delay < 0:
            raise ValueError("latency components must be non-negative")

    def sample(self, order: Order) -> LatencySample:  # noqa: D401 - short delegation
        """See :class:`LatencyModel`."""

        return LatencySample(self.ack_delay, self.fill_delay)


@dataclass(slots=True, frozen=True)
class TelemetryEvent:
    """Telemetry event captured during a paper-trading run."""

    timestamp: float
    event: str
    attributes: Mapping[str, object]


@dataclass(slots=True, frozen=True)
class FillEvent:
    """Materialised fill for a simulated order."""

    quantity: float
    price: float
    timestamp: float


@dataclass(slots=True, frozen=True)
class PnLAnalysis:
    """Execution quality insights derived from simulated fills."""

    realized_value: float
    ideal_value: float
    deviation: float
    implementation_shortfall: float


@dataclass(slots=True, frozen=True)
class PaperOrderReport:
    """Comprehensive report for a single paper-traded order."""

    order: Order
    latency: LatencySample
    fills: tuple[FillEvent, ...]
    telemetry: tuple[TelemetryEvent, ...]
    pnl: PnLAnalysis
    stability_issues: tuple[str, ...]

    @property
    def order_id(self) -> str | None:
        """Return the associated order identifier."""

        return self.order.order_id


class PaperTradingEngine:
    """Execute orders against a simulated exchange with latency and telemetry."""

    def __init__(
        self,
        connector: SimulatedExchangeConnector,
        *,
        latency_model: LatencyModel | None = None,
        clock: Callable[[], float] | None = None,
        telemetry_listeners: Iterable[Callable[[TelemetryEvent], None]] | None = None,
    ) -> None:
        self._connector = connector
        self._latency_model = latency_model or DeterministicLatencyModel()
        self._clock = clock or (lambda: 0.0)
        self._listeners: MutableSequence[Callable[[TelemetryEvent], None]] = []
        if telemetry_listeners:
            self._listeners.extend(telemetry_listeners)

    def _record_event(
        self, event: str, timestamp: float, **attributes: object
    ) -> TelemetryEvent:
        payload = TelemetryEvent(
            timestamp=timestamp, event=event, attributes=dict(attributes)
        )
        for listener in self._listeners:
            listener(payload)
        return payload

    def execute_order(
        self,
        order: Order,
        *,
        execution_price: float,
        ideal_price: float | None = None,
        executed_quantity: float | None = None,
        idempotency_key: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> PaperOrderReport:
        """Submit ``order`` to the simulated venue and return an execution report."""

        if execution_price <= 0:
            raise ValueError("execution_price must be positive")
        if ideal_price is not None and ideal_price <= 0:
            raise ValueError("ideal_price must be positive")

        now = float(self._clock())
        latency = self._latency_model.sample(order)
        ack_time = now + latency.ack_delay
        fill_time = ack_time + latency.fill_delay

        telemetry: list[TelemetryEvent] = []
        telemetry.append(
            self._record_event(
                "order.submit",
                now,
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                metadata=dict(metadata or {}),
            )
        )

        placed = self._connector.place_order(order, idempotency_key=idempotency_key)

        remaining_quantity = placed.remaining_quantity
        if remaining_quantity <= 0:
            raise ValueError("cannot execute an order with no remaining quantity")

        if executed_quantity is None:
            executed_quantity = remaining_quantity

        if executed_quantity <= 0 or executed_quantity - remaining_quantity > 1e-9:
            raise ValueError("executed_quantity must be in (0, remaining_quantity]")

        telemetry.append(
            self._record_event(
                "order.ack",
                ack_time,
                order_id=placed.order_id,
                status=placed.status.value,
                ack_delay=latency.ack_delay,
            )
        )

        filled = self._connector.apply_fill(
            placed.order_id or "", executed_quantity, execution_price
        )
        telemetry.append(
            self._record_event(
                "order.fill",
                fill_time,
                order_id=filled.order_id,
                status=filled.status.value,
                fill_delay=latency.fill_delay,
                executed_quantity=executed_quantity,
                execution_price=execution_price,
            )
        )

        final_order = deepcopy(filled)

        if ideal_price is None:
            ideal_price = execution_price

        side_factor = 1.0 if final_order.side is OrderSide.BUY else -1.0
        realized_value = side_factor * executed_quantity * execution_price
        ideal_value = side_factor * executed_quantity * ideal_price
        deviation = realized_value - ideal_value
        shortfall = implementation_shortfall(
            final_order.side.value,
            ideal_price,
            [FillSample(quantity=executed_quantity, price=execution_price)],
        )

        issues: list[str] = []
        if final_order.status is not OrderStatus.FILLED:
            issues.append(
                f"Order {final_order.order_id or '<unknown>'} ended in status {final_order.status.value}"
            )
        if abs(final_order.filled_quantity - executed_quantity) > 1e-9:
            issues.append("Filled quantity does not match executed_quantity")

        fill_event = FillEvent(
            quantity=executed_quantity,
            price=execution_price,
            timestamp=fill_time,
        )

        return PaperOrderReport(
            order=final_order,
            latency=latency,
            fills=(fill_event,),
            telemetry=tuple(telemetry),
            pnl=PnLAnalysis(
                realized_value=realized_value,
                ideal_value=ideal_value,
                deviation=deviation,
                implementation_shortfall=shortfall,
            ),
            stability_issues=tuple(issues),
        )
