# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Fail-Safe Mechanisms for Risk Monitoring.

This module provides fail-safe controls including:
- Kill-switch mechanism for emergency halt
- Trade halt with graceful position unwinding
- Automatic recovery procedures
- Multi-level escalation

Integrates with existing tradepulse/risk/kill_switch.py for unified control.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

__all__ = [
    "FailSafeController",
    "FailSafeState",
    "FailSafeAction",
    "FailSafeLevel",
]

LOGGER = logging.getLogger(__name__)


class FailSafeLevel(str, Enum):
    """Fail-safe escalation levels.

    Attributes:
        NORMAL: Normal operation.
        CAUTION: Reduced trading activity.
        RESTRICTED: Significantly restricted trading.
        HALT: Complete trading halt.
        EMERGENCY: Emergency shutdown with position liquidation.
    """

    NORMAL = "normal"
    CAUTION = "caution"
    RESTRICTED = "restricted"
    HALT = "halt"
    EMERGENCY = "emergency"

    def _order_index(self) -> int:
        """Get the order index for comparison."""
        order = [
            FailSafeLevel.NORMAL,
            FailSafeLevel.CAUTION,
            FailSafeLevel.RESTRICTED,
            FailSafeLevel.HALT,
            FailSafeLevel.EMERGENCY,
        ]
        return order.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, FailSafeLevel):
            return NotImplemented
        return self._order_index() < other._order_index()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, FailSafeLevel):
            return NotImplemented
        return self._order_index() <= other._order_index()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, FailSafeLevel):
            return NotImplemented
        return self._order_index() > other._order_index()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, FailSafeLevel):
            return NotImplemented
        return self._order_index() >= other._order_index()


class FailSafeAction(str, Enum):
    """Actions that can be taken by fail-safe controller."""

    NONE = "none"
    REDUCE_POSITIONS = "reduce_positions"
    CANCEL_PENDING = "cancel_pending"
    CLOSE_POSITIONS = "close_positions"
    HALT_TRADING = "halt_trading"
    EMERGENCY_LIQUIDATION = "emergency_liquidation"


@dataclass(slots=True)
class FailSafeState:
    """Current state of fail-safe controls.

    Attributes:
        level: Current fail-safe level.
        active: Whether fail-safe is currently active.
        reason: Reason for current state.
        activated_at: When current state was activated.
        source: What triggered the fail-safe.
        position_multiplier: Current position size multiplier.
        allow_new_orders: Whether new orders are allowed.
        force_paper_trading: Whether to force paper trading mode.
        pending_actions: Actions pending execution.
        auto_recover_at: When automatic recovery will be attempted.
    """

    level: FailSafeLevel = FailSafeLevel.NORMAL
    active: bool = False
    reason: str = ""
    activated_at: datetime | None = None
    source: str = ""
    position_multiplier: float = 1.0
    allow_new_orders: bool = True
    force_paper_trading: bool = False
    pending_actions: tuple[FailSafeAction, ...] = ()
    auto_recover_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "level": self.level.value,
            "active": self.active,
            "reason": self.reason,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "source": self.source,
            "position_multiplier": self.position_multiplier,
            "allow_new_orders": self.allow_new_orders,
            "force_paper_trading": self.force_paper_trading,
            "pending_actions": [a.value for a in self.pending_actions],
            "auto_recover_at": self.auto_recover_at.isoformat() if self.auto_recover_at else None,
        }


@dataclass(slots=True)
class FailSafeConfig:
    """Configuration for fail-safe controller.

    Attributes:
        caution_position_multiplier: Position multiplier for caution level.
        restricted_position_multiplier: Position multiplier for restricted level.
        auto_recover_delay_minutes: Minutes before attempting auto-recovery.
        escalation_threshold_seconds: Seconds of sustained stress before escalation.
        require_manual_recovery_levels: Levels requiring manual intervention.
        enable_emergency_liquidation: Whether emergency liquidation is enabled.
    """

    caution_position_multiplier: float = 0.7
    restricted_position_multiplier: float = 0.3
    auto_recover_delay_minutes: int = 30
    escalation_threshold_seconds: int = 60
    require_manual_recovery_levels: tuple[FailSafeLevel, ...] = (
        FailSafeLevel.HALT,
        FailSafeLevel.EMERGENCY,
    )
    enable_emergency_liquidation: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "caution_position_multiplier": self.caution_position_multiplier,
            "restricted_position_multiplier": self.restricted_position_multiplier,
            "auto_recover_delay_minutes": self.auto_recover_delay_minutes,
            "escalation_threshold_seconds": self.escalation_threshold_seconds,
            "require_manual_recovery_levels": [level.value for level in self.require_manual_recovery_levels],
            "enable_emergency_liquidation": self.enable_emergency_liquidation,
        }


@dataclass(slots=True)
class _EscalationEvent:
    """Internal tracking for escalation events."""

    timestamp: datetime
    source: str
    reason: str
    target_level: FailSafeLevel


class FailSafeController:
    """Fail-safe controller with kill-switch and trade halt mechanisms.

    Provides multi-level fail-safe controls with automatic and manual
    escalation/de-escalation capabilities.

    Example:
        >>> controller = FailSafeController()
        >>> controller.escalate_to(FailSafeLevel.CAUTION, "High volatility")
        >>> state = controller.get_state()
        >>> print(f"Level: {state.level.value}, Multiplier: {state.position_multiplier}")
    """

    def __init__(
        self,
        config: FailSafeConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
        on_state_change: Callable[[FailSafeState], None] | None = None,
    ) -> None:
        """Initialize the fail-safe controller.

        Args:
            config: Controller configuration.
            time_source: Optional time source for testing.
            on_state_change: Callback for state changes.
        """
        self._config = config or FailSafeConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._on_state_change = on_state_change
        self._lock = threading.RLock()

        # Current state
        self._state = FailSafeState()

        # Escalation tracking
        self._escalation_history: list[_EscalationEvent] = []
        self._stress_start: datetime | None = None

        LOGGER.info(
            "Fail-safe controller initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> FailSafeConfig:
        """Get current configuration."""
        return self._config

    def get_state(self) -> FailSafeState:
        """Get current fail-safe state.

        Returns:
            Current state snapshot.
        """
        with self._lock:
            # Check for auto-recovery
            self._check_auto_recovery()

            return FailSafeState(
                level=self._state.level,
                active=self._state.active,
                reason=self._state.reason,
                activated_at=self._state.activated_at,
                source=self._state.source,
                position_multiplier=self._state.position_multiplier,
                allow_new_orders=self._state.allow_new_orders,
                force_paper_trading=self._state.force_paper_trading,
                pending_actions=self._state.pending_actions,
                auto_recover_at=self._state.auto_recover_at,
            )

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed.

        Returns:
            True if trading is allowed.
        """
        with self._lock:
            return self._state.level < FailSafeLevel.HALT

    def is_new_orders_allowed(self) -> bool:
        """Check if new orders are allowed.

        Returns:
            True if new orders can be placed.
        """
        with self._lock:
            return self._state.allow_new_orders

    def get_position_multiplier(self) -> float:
        """Get current position size multiplier.

        Returns:
            Multiplier to apply to position sizes.
        """
        with self._lock:
            return self._state.position_multiplier

    def escalate_to(
        self,
        level: FailSafeLevel,
        reason: str,
        *,
        source: str = "system",
    ) -> FailSafeState:
        """Escalate to a specific fail-safe level.

        Args:
            level: Target level.
            reason: Reason for escalation.
            source: Source of escalation.

        Returns:
            Updated state.
        """
        with self._lock:
            if level <= self._state.level:
                LOGGER.debug(
                    "Escalation ignored (not higher): %s <= %s",
                    level.value,
                    self._state.level.value,
                )
                return self.get_state()

            return self._transition_to(level, reason, source)

    def activate_kill_switch(
        self,
        reason: str,
        *,
        source: str = "system",
    ) -> FailSafeState:
        """Activate the kill-switch (halt level).

        Args:
            reason: Reason for activation.
            source: Source of activation.

        Returns:
            Updated state.
        """
        with self._lock:
            LOGGER.critical(
                "Kill-switch activated",
                extra={"reason": reason, "source": source},
            )
            return self._transition_to(FailSafeLevel.HALT, reason, source)

    def activate_emergency(
        self,
        reason: str,
        *,
        source: str = "system",
    ) -> FailSafeState:
        """Activate emergency mode with liquidation.

        Args:
            reason: Reason for emergency.
            source: Source of activation.

        Returns:
            Updated state.
        """
        with self._lock:
            if not self._config.enable_emergency_liquidation:
                # Fall back to halt if emergency not enabled
                return self.activate_kill_switch(reason, source=source)

            LOGGER.critical(
                "EMERGENCY MODE ACTIVATED",
                extra={"reason": reason, "source": source},
            )
            return self._transition_to(FailSafeLevel.EMERGENCY, reason, source)

    def deactivate(
        self,
        *,
        source: str = "operator",
        reason: str = "manual_reset",
    ) -> FailSafeState:
        """Deactivate fail-safe and return to normal.

        Args:
            source: Source of deactivation.
            reason: Reason for deactivation.

        Returns:
            Updated state.
        """
        with self._lock:
            # Check if manual recovery is required
            if self._state.level in self._config.require_manual_recovery_levels:
                if source != "operator":
                    LOGGER.warning(
                        "Manual recovery required for level %s",
                        self._state.level.value,
                    )
                    return self.get_state()

            return self._transition_to(FailSafeLevel.NORMAL, reason, source)

    def step_down(
        self,
        *,
        source: str = "system",
        reason: str = "conditions_improved",
    ) -> FailSafeState:
        """Step down one level if conditions allow.

        Args:
            source: Source of step-down.
            reason: Reason for step-down.

        Returns:
            Updated state.
        """
        with self._lock:
            # Check if manual recovery is required
            if self._state.level in self._config.require_manual_recovery_levels:
                if source != "operator":
                    LOGGER.info(
                        "Manual intervention required to step down from %s",
                        self._state.level.value,
                    )
                    return self.get_state()

            level_order = [
                FailSafeLevel.NORMAL,
                FailSafeLevel.CAUTION,
                FailSafeLevel.RESTRICTED,
                FailSafeLevel.HALT,
                FailSafeLevel.EMERGENCY,
            ]
            current_idx = level_order.index(self._state.level)

            if current_idx > 0:
                new_level = level_order[current_idx - 1]
                return self._transition_to(new_level, reason, source)

            return self.get_state()

    def report_stress(
        self,
        stress_level: str,
        *,
        source: str = "stress_detector",
    ) -> FailSafeState:
        """Report stress level for potential escalation.

        Args:
            stress_level: Detected stress level (normal, elevated, high, critical).
            source: Source of the stress report.

        Returns:
            Current state after potential escalation.
        """
        with self._lock:
            now = self._time()

            stress_map = {
                "normal": FailSafeLevel.NORMAL,
                "elevated": FailSafeLevel.CAUTION,
                "high": FailSafeLevel.RESTRICTED,
                "critical": FailSafeLevel.HALT,
            }

            target_level = stress_map.get(stress_level.lower(), FailSafeLevel.NORMAL)

            if target_level == FailSafeLevel.NORMAL:
                self._stress_start = None
                return self.get_state()

            # Track stress duration for escalation
            if self._stress_start is None:
                self._stress_start = now
            else:
                stress_duration = (now - self._stress_start).total_seconds()
                if stress_duration >= self._config.escalation_threshold_seconds:
                    if target_level > self._state.level:
                        return self.escalate_to(
                            target_level,
                            f"Sustained {stress_level} stress for {stress_duration:.0f}s",
                            source=source,
                        )

            return self.get_state()

    def get_pending_actions(self) -> tuple[FailSafeAction, ...]:
        """Get pending fail-safe actions.

        Returns:
            Tuple of pending actions.
        """
        with self._lock:
            return self._state.pending_actions

    def acknowledge_action(self, action: FailSafeAction) -> None:
        """Acknowledge that an action has been executed.

        Args:
            action: The action that was executed.
        """
        with self._lock:
            remaining = tuple(a for a in self._state.pending_actions if a != action)
            self._state.pending_actions = remaining
            LOGGER.info("Action acknowledged: %s", action.value)

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get escalation history.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of escalation events.
        """
        with self._lock:
            events = self._escalation_history[-limit:]
            return [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "source": e.source,
                    "reason": e.reason,
                    "target_level": e.target_level.value,
                }
                for e in events
            ]

    def reset(self) -> None:
        """Reset controller to initial state (for testing)."""
        with self._lock:
            self._state = FailSafeState()
            self._escalation_history.clear()
            self._stress_start = None
            LOGGER.info("Fail-safe controller reset")

    def _transition_to(
        self,
        level: FailSafeLevel,
        reason: str,
        source: str,
    ) -> FailSafeState:
        """Internal state transition."""
        now = self._time()
        previous_level = self._state.level

        # Record history
        self._escalation_history.append(
            _EscalationEvent(
                timestamp=now,
                source=source,
                reason=reason,
                target_level=level,
            )
        )

        # Determine new state parameters
        active = level != FailSafeLevel.NORMAL
        position_multiplier = self._get_position_multiplier_for_level(level)
        allow_new_orders = level < FailSafeLevel.RESTRICTED
        force_paper = level >= FailSafeLevel.CAUTION
        pending_actions = self._get_actions_for_level(level)

        # Determine auto-recovery time
        auto_recover_at: datetime | None = None
        if level not in self._config.require_manual_recovery_levels and active:
            auto_recover_at = now + timedelta(
                minutes=self._config.auto_recover_delay_minutes
            )

        # Update state
        self._state = FailSafeState(
            level=level,
            active=active,
            reason=reason,
            activated_at=now if active else None,
            source=source,
            position_multiplier=position_multiplier,
            allow_new_orders=allow_new_orders,
            force_paper_trading=force_paper,
            pending_actions=pending_actions,
            auto_recover_at=auto_recover_at,
        )

        # Log transition
        if level > previous_level:
            LOGGER.warning(
                "Fail-safe escalated: %s -> %s",
                previous_level.value,
                level.value,
                extra={"reason": reason, "source": source},
            )
        elif level < previous_level:
            LOGGER.info(
                "Fail-safe de-escalated: %s -> %s",
                previous_level.value,
                level.value,
                extra={"reason": reason, "source": source},
            )

        # Notify callback
        if self._on_state_change:
            try:
                self._on_state_change(self._state)
            except Exception:
                LOGGER.exception("State change callback failed")

        return self.get_state()

    def _get_position_multiplier_for_level(self, level: FailSafeLevel) -> float:
        """Get position multiplier for a fail-safe level."""
        if level == FailSafeLevel.NORMAL:
            return 1.0
        elif level == FailSafeLevel.CAUTION:
            return self._config.caution_position_multiplier
        elif level == FailSafeLevel.RESTRICTED:
            return self._config.restricted_position_multiplier
        else:
            return 0.0  # No new positions for HALT and EMERGENCY

    def _get_actions_for_level(self, level: FailSafeLevel) -> tuple[FailSafeAction, ...]:
        """Get required actions for a fail-safe level."""
        if level == FailSafeLevel.NORMAL:
            return ()
        elif level == FailSafeLevel.CAUTION:
            return (FailSafeAction.REDUCE_POSITIONS,)
        elif level == FailSafeLevel.RESTRICTED:
            return (FailSafeAction.REDUCE_POSITIONS, FailSafeAction.CANCEL_PENDING)
        elif level == FailSafeLevel.HALT:
            return (
                FailSafeAction.CANCEL_PENDING,
                FailSafeAction.HALT_TRADING,
            )
        else:  # EMERGENCY
            return (
                FailSafeAction.CANCEL_PENDING,
                FailSafeAction.EMERGENCY_LIQUIDATION,
            )

    def _check_auto_recovery(self) -> None:
        """Check if automatic recovery should be attempted."""
        if not self._state.active:
            return

        if self._state.level in self._config.require_manual_recovery_levels:
            return

        if self._state.auto_recover_at is None:
            return

        if self._time() >= self._state.auto_recover_at:
            LOGGER.info(
                "Attempting automatic recovery from %s",
                self._state.level.value,
            )
            self._transition_to(
                FailSafeLevel.NORMAL,
                "automatic_recovery",
                "auto_recovery",
            )
