"""Risk manager façade exposing kill-switch controls to administrative APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from execution.risk import RiskManager
from src.security import AccessController, AccessDeniedError

__all__ = ["RiskManagerFacade", "KillSwitchState"]


@dataclass(slots=True)
class KillSwitchState:
    """Snapshot of the kill-switch status."""

    engaged: bool
    reason: str
    already_engaged: bool = False


class RiskManagerFacade:
    """Expose kill-switch operations of :class:`execution.risk.RiskManager`."""

    def __init__(
        self,
        risk_manager: RiskManager,
        *,
        access_controller: AccessController | None = None,
    ) -> None:
        self._risk_manager = risk_manager
        self._access_controller = access_controller

    @property
    def risk_manager(self) -> RiskManager:
        """Return the underlying risk manager instance."""

        return self._risk_manager

    def engage_kill_switch(
        self,
        reason: str,
        *,
        actor: str = "system",
        roles: Iterable[str] = (),
    ) -> KillSwitchState:
        """Engage the global kill-switch with the provided reason.

        Raises:
            ValueError: If no reason is supplied while the kill-switch is
                currently disengaged.
        """

        self._require_permission("engage_kill_switch", actor=actor, roles=roles)
        kill_switch = self._risk_manager.kill_switch
        already_engaged = kill_switch.is_triggered()
        previous_reason = kill_switch.reason

        normalised_reason = reason.strip()

        trigger_reason: str | None
        if normalised_reason:
            trigger_reason = normalised_reason
        elif not already_engaged and previous_reason:
            trigger_reason = previous_reason
        elif not already_engaged:
            raise ValueError("reason must be provided when engaging the kill-switch")
        else:
            trigger_reason = None

        if trigger_reason:
            kill_switch.trigger(trigger_reason)

        current_reason = kill_switch.reason or previous_reason or normalised_reason
        return KillSwitchState(
            engaged=kill_switch.is_triggered(),
            reason=current_reason,
            already_engaged=already_engaged,
        )

    def reset_kill_switch(
        self,
        *,
        actor: str = "system",
        roles: Iterable[str] = (),
    ) -> KillSwitchState:
        """Reset the kill-switch state and return the new snapshot."""

        self._require_permission("reset_kill_switch", actor=actor, roles=roles)
        kill_switch = self._risk_manager.kill_switch
        was_engaged = kill_switch.is_triggered()
        previous_reason = kill_switch.reason
        if was_engaged or bool(previous_reason):
            kill_switch.reset()
        return KillSwitchState(
            engaged=kill_switch.is_triggered(),
            reason=previous_reason if was_engaged else "",
            already_engaged=was_engaged,
        )

    def kill_switch_state(
        self,
        *,
        actor: str = "system",
        roles: Iterable[str] = (),
    ) -> KillSwitchState:
        """Return the current kill-switch status."""

        if self._access_controller is not None:
            self._require_permission("read_kill_switch_state", actor=actor, roles=roles)
        kill_switch = self._risk_manager.kill_switch
        return KillSwitchState(
            engaged=kill_switch.is_triggered(),
            reason=kill_switch.reason,
            already_engaged=kill_switch.is_triggered(),
        )

    def update_risk_limits(
        self,
        *,
        actor: str = "system",
        roles: Iterable[str] = (),
        max_notional: float | None = None,
        max_position: float | None = None,
        kill_switch_violation_threshold: int | None = None,
        kill_switch_limit_multiplier: float | None = None,
        kill_switch_rate_limit_threshold: int | None = None,
        max_orders_per_interval: int | None = None,
    ) -> RiskManager:
        """Update risk limits after enforcing authorisation."""

        updates = {
            "max_notional": max_notional,
            "max_position": max_position,
            "kill_switch_violation_threshold": kill_switch_violation_threshold,
            "kill_switch_limit_multiplier": kill_switch_limit_multiplier,
            "kill_switch_rate_limit_threshold": kill_switch_rate_limit_threshold,
            "max_orders_per_interval": max_orders_per_interval,
        }
        filtered = {key: value for key, value in updates.items() if value is not None}
        if not filtered:
            return self._risk_manager
        self._require_permission("modify_risk_limits", actor=actor, roles=roles)
        self._risk_manager.update_limits(**filtered)
        return self._risk_manager

    def apply_neural_directive(
        self,
        *,
        action: str,
        alloc_main: float,
        alloc_alt: float,
        alloc_scale: float,
    ) -> dict[str, float | str]:
        """Forward neural-controller output to the underlying risk manager."""

        return self._risk_manager.apply_neural_directive(
            action=action,
            alloc_main=alloc_main,
            alloc_alt=alloc_alt,
            alloc_scale=alloc_scale,
        )

    def _require_permission(
        self,
        action: str,
        *,
        actor: str,
        roles: Iterable[str],
        optional: bool = False,
    ) -> None:
        controller = self._access_controller
        if controller is None:
            return
        try:
            controller.require(action, actor=actor, roles=roles)
        except AccessDeniedError:
            if optional:
                return
            raise
