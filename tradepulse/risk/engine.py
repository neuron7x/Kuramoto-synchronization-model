# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Central risk engine with unified risk assessment API.

This module provides the authoritative risk assessment layer for all order
flow in TradePulse. Every order must pass through the risk engine before
execution, ensuring consistent risk controls across all environment modes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol

from .config import RiskEngineConfig, load_risk_config
from .environment import EnvironmentConfig, EnvironmentMode, get_current_mode
from .kill_switch import SafetyController, get_safety_controller

__all__ = [
    "CentralRiskEngine",
    "RiskDecision",
    "RiskStatus",
    "RiskViolation",
    "OrderContext",
    "PortfolioState",
    "MarketState",
]

LOGGER = logging.getLogger(__name__)

# Risk status thresholds as fraction of max daily loss percent
CRITICAL_THRESHOLD_FACTOR = 0.8  # 80% of max = critical
WARNING_THRESHOLD_FACTOR = 0.5  # 50% of max = warning
SAFE_MODE_TRIGGER_FACTOR = 0.7  # 70% of max triggers safe mode


class RiskViolation(str, Enum):
    """Types of risk violations that can occur."""

    KILL_SWITCH_ACTIVE = "kill_switch_active"
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    NOTIONAL_LIMIT_EXCEEDED = "notional_limit_exceeded"
    DAILY_LOSS_LIMIT_EXCEEDED = "daily_loss_limit_exceeded"
    EXPOSURE_LIMIT_EXCEEDED = "exposure_limit_exceeded"
    LEVERAGE_LIMIT_EXCEEDED = "leverage_limit_exceeded"
    ORDER_RATE_EXCEEDED = "order_rate_exceeded"
    SAFE_MODE_RESTRICTION = "safe_mode_restriction"
    RISK_ENGINE_DISABLED = "risk_engine_disabled"
    ENVIRONMENT_NOT_ALLOWED = "environment_not_allowed"


class RiskStatus(str, Enum):
    """Overall risk status of the portfolio."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    HALTED = "halted"


@dataclass(slots=True, frozen=True)
class RiskDecision:
    """Result of a risk assessment.

    Attributes:
        allowed: Whether the order is allowed.
        violations: List of violations if not allowed.
        adjusted_quantity: Adjusted quantity if position limits apply.
        risk_status: Current overall risk status.
        message: Human-readable explanation.
        metadata: Additional context about the decision.
    """

    allowed: bool
    violations: tuple[RiskViolation, ...] = ()
    adjusted_quantity: float | None = None
    risk_status: RiskStatus = RiskStatus.OK
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "allowed": self.allowed,
            "violations": [v.value for v in self.violations],
            "adjusted_quantity": self.adjusted_quantity,
            "risk_status": self.risk_status.value,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class OrderContext:
    """Context for an order being assessed.

    Attributes:
        symbol: Trading symbol.
        side: Order side ("buy" or "sell").
        quantity: Order quantity.
        price: Order price (or market price for market orders).
        order_type: Type of order (market, limit, etc.).
    """

    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str = "market"

    def __post_init__(self) -> None:
        self.side = self.side.lower()
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"Invalid side: {self.side}")
        if self.quantity < 0:
            raise ValueError("Quantity must be non-negative")
        if self.price <= 0:
            raise ValueError("Price must be positive")


@dataclass(slots=True)
class PortfolioState:
    """Current portfolio state for risk assessment.

    Attributes:
        positions: Current positions by symbol.
        equity: Current account equity.
        peak_equity: Peak equity (for drawdown calculation).
        daily_pnl: PnL since start of day.
        total_exposure: Total portfolio exposure (notional).
        margin_used: Current margin utilization.
    """

    positions: dict[str, float] = field(default_factory=dict)
    equity: float = 0.0
    peak_equity: float = 0.0
    daily_pnl: float = 0.0
    total_exposure: float = 0.0
    margin_used: float = 0.0

    def get_position(self, symbol: str) -> float:
        """Get position for a symbol."""
        return self.positions.get(symbol, 0.0)

    def get_drawdown(self) -> float:
        """Calculate current drawdown as a fraction."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)


@dataclass(slots=True)
class MarketState:
    """Current market state for risk assessment.

    Attributes:
        prices: Current prices by symbol.
        volatilities: Volatility estimates by symbol.
        liquidity_scores: Liquidity scores by symbol.
    """

    prices: dict[str, float] = field(default_factory=dict)
    volatilities: dict[str, float] = field(default_factory=dict)
    liquidity_scores: dict[str, float] = field(default_factory=dict)

    def get_price(self, symbol: str, default: float = 0.0) -> float:
        """Get price for a symbol."""
        return self.prices.get(symbol, default)


class MetricsCollector(Protocol):
    """Protocol for metrics collection."""

    def record_risk_decision(
        self,
        symbol: str,
        allowed: bool,
        violations: list[str],
    ) -> None:
        """Record a risk decision."""
        ...

    def record_blocked_order(self, symbol: str, reason: str) -> None:
        """Record a blocked order."""
        ...


class CentralRiskEngine:
    """Central risk engine for TradePulse.

    This engine provides unified risk assessment for all order flow,
    ensuring consistent risk controls regardless of environment mode.
    """

    def __init__(
        self,
        config: RiskEngineConfig | None = None,
        *,
        safety_controller: SafetyController | None = None,
        metrics_collector: MetricsCollector | None = None,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        """Initialize the risk engine.

        Args:
            config: Risk engine configuration.
            safety_controller: Safety controller instance.
            metrics_collector: Metrics collector for instrumentation.
            time_source: Time source for rate limiting.
        """
        self._config = config or load_risk_config()
        self._safety = safety_controller or get_safety_controller()
        self._metrics = metrics_collector
        self._time = time_source or time.time
        self._lock = threading.RLock()

        # Rate limiting state
        self._order_timestamps: deque[float] = deque()
        self._hourly_order_count = 0
        self._last_hour_reset = self._time()

        # Tracking state
        self._daily_loss = 0.0
        self._consecutive_losses = 0
        self._last_daily_reset: datetime | None = None

        LOGGER.info(
            "Central risk engine initialized",
            extra={
                "event": "risk_engine.initialized",
                "config": self._config.to_dict(),
            },
        )

    @property
    def config(self) -> RiskEngineConfig:
        """Get the current configuration."""
        return self._config

    def update_config(self, config: RiskEngineConfig) -> None:
        """Update the risk engine configuration.

        Args:
            config: New configuration.
        """
        with self._lock:
            self._config = config
            LOGGER.info(
                "Risk engine configuration updated",
                extra={
                    "event": "risk_engine.config_updated",
                    "config": config.to_dict(),
                },
            )

    def assess_order(
        self,
        order: OrderContext,
        portfolio_state: PortfolioState,
        market_state: MarketState,
    ) -> RiskDecision:
        """Assess whether an order should be allowed.

        This is the primary entry point for risk assessment. Every order
        must pass through this method before execution.

        Args:
            order: Order context to assess.
            portfolio_state: Current portfolio state.
            market_state: Current market state.

        Returns:
            RiskDecision indicating whether the order is allowed.
        """
        with self._lock:
            violations: list[RiskViolation] = []
            metadata: dict[str, Any] = {}

            # Check environment mode
            env_mode = get_current_mode()
            env_config = EnvironmentConfig.for_mode(env_mode)

            # 1. Kill-switch check (highest priority)
            if self._safety.is_kill_switch_active():
                violations.append(RiskViolation.KILL_SWITCH_ACTIVE)
                return self._create_decision(
                    allowed=False,
                    violations=violations,
                    status=RiskStatus.HALTED,
                    message=f"Kill-switch active: {self._safety.state.kill_switch_reason}",
                    order=order,
                    metadata={
                        "kill_switch_reason": self._safety.state.kill_switch_reason
                    },
                )

            # 2. Check if risk checks are enabled
            if not self._config.enable_risk_checks:
                if env_mode == EnvironmentMode.LIVE:
                    # In LIVE mode, risk checks must be enabled
                    violations.append(RiskViolation.RISK_ENGINE_DISABLED)
                    return self._create_decision(
                        allowed=False,
                        violations=violations,
                        status=RiskStatus.CRITICAL,
                        message="Risk engine disabled in LIVE mode is not allowed",
                        order=order,
                    )
                # In other modes, allow without checks
                return self._create_decision(
                    allowed=True,
                    violations=[],
                    status=RiskStatus.OK,
                    message="Risk checks disabled",
                    order=order,
                )

            # 3. Check environment constraints
            if (
                not env_config.allow_real_orders
                and env_mode != EnvironmentMode.BACKTEST
            ):
                # Paper mode - allow but note it's simulated
                metadata["simulated"] = True

            # 4. Safe mode adjustments
            position_multiplier = 1.0
            if self._safety.is_safe_mode_active():
                position_multiplier = self._safety.get_position_multiplier()
                metadata["safe_mode_active"] = True
                metadata["position_multiplier"] = position_multiplier

            # 5. Rate limit check
            if not self._check_rate_limits():
                violations.append(RiskViolation.ORDER_RATE_EXCEEDED)

            # 6. Position limit check
            adjusted_quantity = order.quantity * position_multiplier
            symbol_limits = self._config.get_symbol_limits(order.symbol)
            current_position = portfolio_state.get_position(order.symbol)

            side_sign = 1.0 if order.side == "buy" else -1.0
            new_position = current_position + side_sign * adjusted_quantity

            if abs(new_position) > symbol_limits.max_position_size:
                violations.append(RiskViolation.POSITION_LIMIT_EXCEEDED)
                metadata["current_position"] = current_position
                metadata["requested_position"] = new_position
                metadata["max_position"] = symbol_limits.max_position_size

            # 7. Notional limit check
            notional = adjusted_quantity * order.price
            if notional > self._config.max_notional_per_order:
                violations.append(RiskViolation.NOTIONAL_LIMIT_EXCEEDED)
                metadata["notional"] = notional
                metadata["max_notional"] = self._config.max_notional_per_order

            # 8. Daily loss check
            self._update_daily_tracking()
            daily_loss_limit = self._config.max_daily_loss
            daily_loss_pct_limit = self._config.max_daily_loss_percent

            if portfolio_state.daily_pnl <= -daily_loss_limit:
                violations.append(RiskViolation.DAILY_LOSS_LIMIT_EXCEEDED)
                metadata["daily_pnl"] = portfolio_state.daily_pnl
                metadata["max_daily_loss"] = daily_loss_limit

            if portfolio_state.peak_equity > 0:
                drawdown = portfolio_state.get_drawdown()
                if drawdown > daily_loss_pct_limit:
                    violations.append(RiskViolation.DAILY_LOSS_LIMIT_EXCEEDED)
                    metadata["drawdown"] = drawdown
                    metadata["max_drawdown_pct"] = daily_loss_pct_limit

            # 9. Total exposure check
            new_exposure = portfolio_state.total_exposure + notional
            if new_exposure > self._config.max_total_exposure:
                violations.append(RiskViolation.EXPOSURE_LIMIT_EXCEEDED)
                metadata["current_exposure"] = portfolio_state.total_exposure
                metadata["new_exposure"] = new_exposure
                metadata["max_exposure"] = self._config.max_total_exposure

            # 10. Leverage check
            if portfolio_state.equity > 0:
                leverage = new_exposure / portfolio_state.equity
                if leverage > self._config.max_leverage:
                    violations.append(RiskViolation.LEVERAGE_LIMIT_EXCEEDED)
                    metadata["leverage"] = leverage
                    metadata["max_leverage"] = self._config.max_leverage

            # Determine overall status
            status = RiskStatus.OK
            if violations:
                if RiskViolation.KILL_SWITCH_ACTIVE in violations:
                    status = RiskStatus.HALTED
                elif any(
                    v in violations
                    for v in [
                        RiskViolation.DAILY_LOSS_LIMIT_EXCEEDED,
                        RiskViolation.EXPOSURE_LIMIT_EXCEEDED,
                    ]
                ):
                    status = RiskStatus.CRITICAL
                else:
                    status = RiskStatus.WARNING

            # Check if we should trigger kill-switch
            self._check_auto_kill_switch(portfolio_state)

            # Record rate limit
            if not violations:
                self._record_order()

            allowed = len(violations) == 0
            message = self._build_message(violations, metadata)

            return self._create_decision(
                allowed=allowed,
                violations=violations,
                status=status,
                message=message,
                order=order,
                adjusted_quantity=(
                    adjusted_quantity if position_multiplier < 1.0 else None
                ),
                metadata=metadata,
            )

    def assess_after_trade(self, portfolio_state: PortfolioState) -> RiskStatus:
        """Assess portfolio risk status after a trade.

        This should be called after each trade to update risk tracking
        and potentially trigger safety mechanisms.

        Args:
            portfolio_state: Current portfolio state.

        Returns:
            Current risk status.
        """
        with self._lock:
            # Update loss tracking
            if portfolio_state.daily_pnl < self._daily_loss:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0
            self._daily_loss = portfolio_state.daily_pnl

            # Check for automatic safety triggers
            self._check_auto_kill_switch(portfolio_state)
            self._check_auto_safe_mode(portfolio_state)

            # Determine status
            drawdown = portfolio_state.get_drawdown()
            if self._safety.is_kill_switch_active():
                return RiskStatus.HALTED
            elif (
                drawdown
                > self._config.max_daily_loss_percent * CRITICAL_THRESHOLD_FACTOR
            ):
                return RiskStatus.CRITICAL
            elif (
                drawdown
                > self._config.max_daily_loss_percent * WARNING_THRESHOLD_FACTOR
            ):
                return RiskStatus.WARNING
            return RiskStatus.OK

    def get_status(self) -> dict[str, Any]:
        """Get current risk engine status.

        Returns:
            Dictionary with current status information.
        """
        with self._lock:
            return {
                "enabled": self._config.enable_risk_checks,
                "kill_switch_active": self._safety.is_kill_switch_active(),
                "safe_mode_active": self._safety.is_safe_mode_active(),
                "position_multiplier": self._safety.get_position_multiplier(),
                "daily_loss": self._daily_loss,
                "consecutive_losses": self._consecutive_losses,
                "orders_this_minute": len(self._order_timestamps),
                "orders_this_hour": self._hourly_order_count,
                "environment_mode": get_current_mode().value,
            }

    def reset_daily_tracking(self) -> None:
        """Reset daily tracking (called at start of day)."""
        with self._lock:
            self._daily_loss = 0.0
            self._consecutive_losses = 0
            self._last_daily_reset = datetime.now(timezone.utc)
            LOGGER.info(
                "Daily risk tracking reset",
                extra={"event": "risk_engine.daily_reset"},
            )

    def _check_rate_limits(self) -> bool:
        """Check if order rate limits are exceeded.

        Returns:
            True if within limits, False if exceeded.
        """
        now = self._time()

        # Clean old timestamps
        minute_ago = now - 60
        while self._order_timestamps and self._order_timestamps[0] < minute_ago:
            self._order_timestamps.popleft()

        # Check minute limit
        if len(self._order_timestamps) >= self._config.max_orders_per_minute:
            return False

        # Check hour limit (reset counter if more than 1 hour since last reset)
        if now - self._last_hour_reset > 3600:
            self._hourly_order_count = 0
            self._last_hour_reset = now

        if self._hourly_order_count >= self._config.max_orders_per_hour:
            return False

        return True

    def _record_order(self) -> None:
        """Record an order for rate limiting."""
        now = self._time()
        self._order_timestamps.append(now)
        self._hourly_order_count += 1

    def _update_daily_tracking(self) -> None:
        """Update daily tracking, resetting if needed."""
        now = datetime.now(timezone.utc)
        if self._last_daily_reset is None:
            self._last_daily_reset = now
            return

        # Reset at midnight UTC
        if now.date() > self._last_daily_reset.date():
            self.reset_daily_tracking()

    def _check_auto_kill_switch(self, portfolio_state: PortfolioState) -> None:
        """Check if kill-switch should be automatically triggered."""
        if self._safety.is_kill_switch_active():
            return

        # Check loss threshold
        if portfolio_state.daily_pnl <= -self._config.kill_switch_loss_threshold:
            self._safety.activate_kill_switch(
                reason=f"Daily loss threshold exceeded: {portfolio_state.daily_pnl:.2f}",
                source="risk_engine",
            )
            return

        # Check consecutive losses
        if self._consecutive_losses >= self._config.kill_switch_loss_streak:
            self._safety.activate_kill_switch(
                reason=f"Consecutive loss streak: {self._consecutive_losses}",
                source="risk_engine",
            )

    def _check_auto_safe_mode(self, portfolio_state: PortfolioState) -> None:
        """Check if safe mode should be automatically triggered."""
        if self._safety.is_safe_mode_active():
            return

        drawdown = portfolio_state.get_drawdown()
        warning_threshold = (
            self._config.max_daily_loss_percent * SAFE_MODE_TRIGGER_FACTOR
        )

        if drawdown > warning_threshold:
            self._safety.activate_safe_mode(
                reason=f"Drawdown warning threshold: {drawdown:.1%}",
                source="risk_engine",
                position_multiplier=self._config.safe_mode_position_multiplier,
            )

    def _create_decision(
        self,
        *,
        allowed: bool,
        violations: list[RiskViolation],
        status: RiskStatus,
        message: str,
        order: OrderContext,
        adjusted_quantity: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RiskDecision:
        """Create a risk decision and record metrics."""
        decision = RiskDecision(
            allowed=allowed,
            violations=tuple(violations),
            adjusted_quantity=adjusted_quantity,
            risk_status=status,
            message=message,
            metadata=metadata or {},
        )

        # Log the decision
        log_extra = {
            "event": "risk_engine.decision",
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "allowed": allowed,
            "status": status.value,
            "violations": [v.value for v in violations],
        }

        if allowed:
            LOGGER.debug("Order allowed", extra=log_extra)
        else:
            LOGGER.warning("Order blocked", extra=log_extra)

        # Record metrics
        if self._metrics:
            try:
                self._metrics.record_risk_decision(
                    order.symbol,
                    allowed,
                    [v.value for v in violations],
                )
                if not allowed:
                    self._metrics.record_blocked_order(
                        order.symbol,
                        violations[0].value if violations else "unknown",
                    )
            except Exception:
                LOGGER.exception("Failed to record risk metrics")

        return decision

    def _build_message(
        self,
        violations: list[RiskViolation],
        metadata: dict[str, Any],
    ) -> str:
        """Build a human-readable message for the decision."""
        if not violations:
            return "Order allowed"

        messages = []
        for violation in violations:
            if violation == RiskViolation.KILL_SWITCH_ACTIVE:
                reason = metadata.get("kill_switch_reason", "unknown")
                messages.append(f"Kill-switch active: {reason}")
            elif violation == RiskViolation.POSITION_LIMIT_EXCEEDED:
                max_pos = metadata.get("max_position", "N/A")
                messages.append(f"Position limit exceeded (max: {max_pos})")
            elif violation == RiskViolation.NOTIONAL_LIMIT_EXCEEDED:
                max_notional = metadata.get("max_notional", "N/A")
                messages.append(f"Notional limit exceeded (max: {max_notional})")
            elif violation == RiskViolation.DAILY_LOSS_LIMIT_EXCEEDED:
                messages.append("Daily loss limit exceeded")
            elif violation == RiskViolation.EXPOSURE_LIMIT_EXCEEDED:
                messages.append("Total exposure limit exceeded")
            elif violation == RiskViolation.LEVERAGE_LIMIT_EXCEEDED:
                max_lev = metadata.get("max_leverage", "N/A")
                messages.append(f"Leverage limit exceeded (max: {max_lev})")
            elif violation == RiskViolation.ORDER_RATE_EXCEEDED:
                messages.append("Order rate limit exceeded")
            else:
                messages.append(violation.value)

        return "; ".join(messages)
