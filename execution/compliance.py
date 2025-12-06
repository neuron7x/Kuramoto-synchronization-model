"""Pre-trade compliance checks against exchange minimums and risk limits."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Optional

from domain import Order, OrderSide

from .metrics import RiskMetrics, get_risk_metrics
from .normalization import NormalizationError, SymbolNormalizer

LOGGER = logging.getLogger(__name__)

__all__ = [
    "ComplianceViolation",
    "ComplianceReport",
    "ComplianceMonitor",
    "RiskDecision",
    "RiskCompliance",
]


class ComplianceViolation(NormalizationError):
    """Raised when an order violates venue-level minimums."""

    def __init__(
        self, message: str, *, report: "ComplianceReport" | None = None
    ) -> None:
        super().__init__(message)
        self.report = report


@dataclass(slots=True, frozen=True)
class ComplianceReport:
    """Outcome of a pre-trade compliance check."""

    symbol: str
    requested_quantity: float
    requested_price: float | None
    normalized_quantity: float
    normalized_price: float | None
    violations: tuple[str, ...]
    blocked: bool

    def is_clean(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict:
        """Serialize the report to a plain dictionary."""

        return {
            "symbol": self.symbol,
            "requested_quantity": self.requested_quantity,
            "requested_price": self.requested_price,
            "normalized_quantity": self.normalized_quantity,
            "normalized_price": self.normalized_price,
            "violations": list(self.violations),
            "blocked": self.blocked,
        }


class ComplianceMonitor:
    """Validate orders against lot, tick, and notional minimums before routing."""

    def __init__(
        self,
        normalizer: SymbolNormalizer,
        *,
        strict: bool = True,
        auto_round: bool = True,
    ) -> None:
        self._normalizer = normalizer
        self._strict = strict
        self._auto_round = auto_round

    def check(
        self, symbol: str, quantity: float, price: float | None = None
    ) -> ComplianceReport:
        normalized_qty = (
            self._normalizer.round_quantity(symbol, quantity)
            if self._auto_round
            else quantity
        )
        normalized_price = (
            (None if price is None else self._normalizer.round_price(symbol, price))
            if self._auto_round
            else price
        )

        violations: list[str] = []
        violation_exc: NormalizationError | None = None
        try:
            self._normalizer.validate(symbol, normalized_qty, normalized_price)
        except NormalizationError as exc:
            violations.append(str(exc))
            violation_exc = exc

        blocked = bool(violations) and self._strict
        report = ComplianceReport(
            symbol=symbol,
            requested_quantity=float(quantity),
            requested_price=None if price is None else float(price),
            normalized_quantity=float(normalized_qty),
            normalized_price=(
                None if normalized_price is None else float(normalized_price)
            ),
            violations=tuple(violations),
            blocked=blocked,
        )
        if violation_exc is not None and self._strict:
            raise ComplianceViolation(
                str(violation_exc), report=report
            ) from violation_exc
        return report


@dataclass(slots=True, frozen=True)
class RiskDecision:
    """Result of a pre-trade risk compliance check."""

    allowed: bool
    reasons: tuple[str, ...]
    breached_limits: dict[str, float]
    next_reset_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize the decision to a plain dictionary."""
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "breached_limits": dict(self.breached_limits),
            "next_reset_at": (
                self.next_reset_at.isoformat() if self.next_reset_at else None
            ),
        }


@dataclass
class RiskConfig:
    """Configuration for risk compliance checks."""

    kill_switch: bool = False
    max_notional_per_order: float = 0.0
    per_symbol_position_cap_type: str = "units"
    per_symbol_position_cap_default: float = 0.0
    per_symbol_position_cap_overrides: dict[str, float] | None = None
    max_gross_exposure: float = 0.0
    daily_max_drawdown_mode: str = "percent"
    daily_max_drawdown_threshold: float = 0.0
    daily_max_drawdown_window: str = "daily"
    max_open_orders_per_account: int = 0

    def __post_init__(self) -> None:
        if self.per_symbol_position_cap_overrides is None:
            object.__setattr__(self, "per_symbol_position_cap_overrides", {})


class RiskCompliance:
    """Pre-trade and post-trade risk compliance checks with configurable limits."""

    def __init__(
        self,
        config: RiskConfig,
        *,
        metrics: RiskMetrics | None = None,
    ) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._last_trip_reason: Optional[str] = None
        self._last_trip_time: Optional[datetime] = None
        self._daily_high_equity: float = 0.0
        self._daily_reset_time: Optional[datetime] = None
        self._open_orders_count: int = 0
        self._metrics: RiskMetrics | None = metrics or get_risk_metrics()

        self._record_metric(
            lambda collector: collector.record_kill_switch(config.kill_switch)
        )
        self._record_open_orders_metric()

    def set_kill_switch(self, enabled: bool) -> None:
        """Enable or disable the global kill switch."""
        with self._lock:
            self._config = dataclass_replace(self._config, kill_switch=enabled)
            if enabled:
                self._last_trip_reason = "kill_switch_enabled"
                self._last_trip_time = datetime.now(timezone.utc)
            self._record_metric(lambda collector: collector.record_kill_switch(enabled))

    def update_config(self, **updates: object) -> RiskConfig:
        """Apply partial updates to the risk configuration."""

        if not updates:
            return self._config

        valid_fields = set(RiskConfig.__dataclass_fields__)
        unknown = set(updates) - valid_fields
        if unknown:
            raise ValueError(f"Unknown risk configuration keys: {sorted(unknown)}")

        with self._lock:
            self._config = dataclass_replace(self._config, **updates)
            self._record_metric(
                lambda collector: collector.record_kill_switch(self._config.kill_switch)
            )
            return self._config

    def check_order(
        self,
        order: Order,
        market_data: dict[str, float],
        portfolio_state: dict[str, float | dict],
    ) -> RiskDecision:
        """Perform pre-trade compliance check on an order.

        Args:
            order: The order to validate
            market_data: Dict with 'price' key for current market price
            portfolio_state: Dict with 'positions', 'gross_exposure', 'equity', 'peak_equity'

        Returns:
            RiskDecision indicating whether the order is allowed
        """
        with self._lock:
            reasons: list[str] = []
            breached: dict[str, float] = {}
            next_reset: Optional[datetime] = None

            if self._config.kill_switch:
                reasons.append("Kill switch is enabled")
                breached["kill_switch"] = 1.0
                self._last_trip_reason = "kill_switch"
                self._last_trip_time = datetime.now(timezone.utc)
                self._record_rejections(breached, reasons)
                return RiskDecision(
                    allowed=False,
                    reasons=tuple(reasons),
                    breached_limits=breached,
                    next_reset_at=next_reset,
                )

            price = market_data.get("price", order.price)
            if price is None or price <= 0:
                price = 1.0

            notional = abs(price * order.quantity)

            if self._config.max_notional_per_order > 0:
                if notional > self._config.max_notional_per_order:
                    reasons.append(
                        f"Order notional {notional:.2f} exceeds max {self._config.max_notional_per_order:.2f}"
                    )
                    breached["max_notional_per_order"] = notional

            positions = portfolio_state.get("positions", {})
            if isinstance(positions, dict):
                current_position = float(positions.get(order.symbol, 0.0))
            else:
                current_position = 0.0

            side = OrderSide(order.side)
            position_delta = (
                order.quantity if side == OrderSide.BUY else -order.quantity
            )
            new_position = current_position + position_delta

            cap = self._config.per_symbol_position_cap_default
            overrides = self._config.per_symbol_position_cap_overrides or {}
            if order.symbol in overrides:
                cap = overrides[order.symbol]

            if cap > 0:
                if self._config.per_symbol_position_cap_type == "units":
                    if abs(new_position) > cap:
                        reasons.append(
                            f"Position {abs(new_position):.4f} would exceed cap {cap:.4f} for {order.symbol}"
                        )
                        breached["per_symbol_position_cap"] = abs(new_position)
                else:
                    new_notional = abs(new_position * price)
                    if new_notional > cap:
                        reasons.append(
                            f"Position notional {new_notional:.2f} would exceed cap {cap:.2f} for {order.symbol}"
                        )
                        breached["per_symbol_position_cap_notional"] = new_notional

            gross_exposure = float(portfolio_state.get("gross_exposure", 0.0))
            position_notional_before = abs(current_position * price)
            position_notional_after = abs(new_position * price)
            projected_gross = (
                gross_exposure + position_notional_after - position_notional_before
            )
            if self._config.max_gross_exposure > 0:
                if projected_gross > self._config.max_gross_exposure:
                    reasons.append(
                        f"Gross exposure {projected_gross:.2f} would exceed limit {self._config.max_gross_exposure:.2f}"
                    )
                    breached["max_gross_exposure"] = projected_gross

            self._record_metric(
                lambda collector, exposure=projected_gross: collector.record_gross_exposure(
                    exposure
                )
            )

            if self._config.daily_max_drawdown_threshold > 0:
                equity = float(portfolio_state.get("equity", 0.0))
                peak_equity = float(portfolio_state.get("peak_equity", equity))
                drawdown_metric_value: float | None = None
                drawdown_metric_mode = self._config.daily_max_drawdown_mode

                now = datetime.now(timezone.utc)
                if self._daily_reset_time is None or self._should_reset_daily(now):
                    self._daily_high_equity = peak_equity
                    self._daily_reset_time = now
                    next_reset = self._next_daily_reset(now)
                else:
                    if peak_equity > self._daily_high_equity:
                        self._daily_high_equity = peak_equity
                    next_reset = self._next_daily_reset(self._daily_reset_time)

                if self._daily_high_equity > 0:
                    drawdown = (
                        self._daily_high_equity - equity
                    ) / self._daily_high_equity

                    if self._config.daily_max_drawdown_mode == "percent":
                        if drawdown > self._config.daily_max_drawdown_threshold:
                            threshold = self._config.daily_max_drawdown_threshold
                            reasons.append(
                                f"Daily drawdown {drawdown * 100:.2f}% exceeds "
                                f"threshold {threshold * 100:.2f}%"
                            )
                            breached["daily_max_drawdown"] = drawdown
                        drawdown_metric_value = drawdown
                    else:
                        dd_notional = self._daily_high_equity - equity
                        if dd_notional > self._config.daily_max_drawdown_threshold:
                            threshold = self._config.daily_max_drawdown_threshold
                            reasons.append(
                                f"Daily drawdown ${dd_notional:.2f} exceeds "
                                f"threshold ${threshold:.2f}"
                            )
                            breached["daily_max_drawdown_notional"] = dd_notional
                        drawdown_metric_value = dd_notional

                    if drawdown_metric_value is not None:
                        self._record_metric(
                            lambda collector, value=drawdown_metric_value, mode=drawdown_metric_mode: (
                                collector.record_daily_drawdown(value, mode=mode)
                            )
                        )

            if self._config.max_open_orders_per_account > 0:
                if self._open_orders_count >= self._config.max_open_orders_per_account:
                    limit = self._config.max_open_orders_per_account
                    reasons.append(
                        f"Open orders {self._open_orders_count} at or exceeds limit {limit}"
                    )
                    breached["max_open_orders"] = float(self._open_orders_count)

            if reasons:
                self._last_trip_reason = "; ".join(reasons)
                self._last_trip_time = datetime.now(timezone.utc)
                self._record_rejections(breached, reasons)

            return RiskDecision(
                allowed=len(reasons) == 0,
                reasons=tuple(reasons),
                breached_limits=breached,
                next_reset_at=next_reset,
            )

    def register_order_open(self) -> None:
        """Register that an order has been opened."""
        with self._lock:
            self._open_orders_count += 1
            self._record_open_orders_metric()

    def register_order_close(self) -> None:
        """Register that an order has been closed."""
        with self._lock:
            if self._open_orders_count > 0:
                self._open_orders_count -= 1
            self._record_open_orders_metric()

    def get_state(self) -> dict:
        """Get current risk compliance state.

        Returns:
            Dict containing current kill switch state, exposure metrics, and last trip info
        """
        with self._lock:
            return {
                "kill_switch": self._config.kill_switch,
                "max_notional_per_order": self._config.max_notional_per_order,
                "max_gross_exposure": self._config.max_gross_exposure,
                "daily_max_drawdown_threshold": self._config.daily_max_drawdown_threshold,
                "daily_max_drawdown_mode": self._config.daily_max_drawdown_mode,
                "daily_high_equity": self._daily_high_equity,
                "last_trip_reason": self._last_trip_reason,
                "last_trip_time": (
                    self._last_trip_time.isoformat() if self._last_trip_time else None
                ),
                "open_orders_count": self._open_orders_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _record_metric(self, callback: Callable[[RiskMetrics], None]) -> None:
        metrics = self._metrics
        if metrics is None:
            return
        try:
            callback(metrics)
        except Exception:  # pragma: no cover - defensive guardrail
            LOGGER.exception("Failed to record risk compliance metric")

    def _record_open_orders_metric(self) -> None:
        self._record_metric(
            lambda collector, count=self._open_orders_count: collector.record_open_orders(
                count
            )
        )

    def _record_rejections(
        self, breached: Mapping[str, float], reasons: Iterable[str]
    ) -> None:
        labels = list(breached.keys())
        if not labels:
            reason_text = "; ".join(reasons)
            normalised = self._normalise_rejection_reason(reason_text)
            if normalised:
                labels = [normalised]
        for label in labels:
            self._record_metric(
                lambda collector, reason=label: collector.record_rejection(reason)
            )

    @staticmethod
    def _normalise_rejection_reason(reason: str) -> str:
        if not reason:
            return "unspecified"
        cleaned = [ch.lower() if ch.isalnum() else "_" for ch in reason]
        normalised = "".join(cleaned).strip("_")
        while "__" in normalised:
            normalised = normalised.replace("__", "_")
        return normalised or "unspecified"

    def _should_reset_daily(self, now: datetime) -> bool:
        """Check if daily metrics should be reset."""
        if self._daily_reset_time is None:
            return True
        time_since_reset = (now - self._daily_reset_time).total_seconds()
        return time_since_reset >= 86400

    def _next_daily_reset(self, from_time: datetime) -> datetime:
        """Calculate next daily reset time."""
        from datetime import timedelta

        next_day = from_time + timedelta(days=1)
        return datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            0,
            0,
            0,
            tzinfo=timezone.utc,
        )
