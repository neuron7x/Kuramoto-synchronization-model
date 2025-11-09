from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable

try:
    from core.neuro.serotonin.serotonin_controller import CooldownStatus
except Exception:  # pragma: no cover - optional serotonin dependency for typing.
    @dataclass
    class CooldownStatus:  # type: ignore[override]
        hold: bool = False
        tonic_trigger: bool = False
        gate_trigger: bool = False
        phasic_trigger: bool = False
        accepted: bool = True
        serotonin_level: float = 0.0

from .ddm_adapter import DDMAdjustment, adapt_ddm_parameters

from .dopamine_controller import DopamineController


@runtime_checkable
class SerotoninLike(Protocol):
    """Protocol describing the serotonin interface required by the gate."""

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        ...

    def cooldown_status(self, serotonin_signal: Optional[float] = None) -> "CooldownStatus":
        ...

@dataclass(frozen=True)
class GateEvaluation:
    """Outcome of the action gate evaluation."""

    go: bool
    hold: bool
    no_go: bool
    temperature: float
    dopamine_level: float
    hold_reason: Optional[str] = None
    ddm_adjustment: Optional[DDMAdjustment] = None
    extras: Dict[str, float] | None = None


class ActionGate:
    """Coordinate dopamine Go/No-Go signals with serotonin HOLD vetoes."""

    def __init__(
        self,
        dopamine_ctrl: DopamineController,
        serotonin_ctrl: Optional[SerotoninLike] = None,
    ) -> None:
        self._dopamine = dopamine_ctrl
        self._serotonin = serotonin_ctrl

    def evaluate(
        self,
        dopamine_signal: Optional[float] = None,
        serotonin_signal: Optional[float] = None,
        *,
        ddm_base_drift: Optional[float] = None,
        ddm_base_boundary: Optional[float] = None,
        ddm_kwargs: Optional[Dict[str, float]] = None,
    ) -> GateEvaluation:
        da = self._dopamine.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        go = self._dopamine.check_invigoration(da)
        hold = False
        hold_reason: Optional[str] = None
        serotonin_level = None
        if self._serotonin is not None:
            status: Optional[CooldownStatus] = None
            if hasattr(self._serotonin, "cooldown_status"):
                status = self._serotonin.cooldown_status(serotonin_signal)
                serotonin_level = float(getattr(status, "serotonin_level", serotonin_signal or 0.0))
                hold = bool(status.hold)
                if status.hold:
                    channels = []
                    if getattr(status, "tonic_trigger", False):
                        channels.append("tonic")
                    if getattr(status, "gate_trigger", False):
                        channels.append("gate")
                    if getattr(status, "phasic_trigger", False):
                        channels.append("phasic")
                    hold_reason = ",".join(channels) or "serotonin"
                elif not getattr(status, "accepted", True):
                    hold_reason = "guard_rejected"
            else:  # pragma: no cover - legacy serotonin interface.
                hold = bool(self._serotonin.check_cooldown(serotonin_signal))
                serotonin_level = serotonin_signal if serotonin_signal is not None else getattr(self._serotonin, "serotonin_level", 0.0)
            if hold:
                go = False
        no_go = hold or self._dopamine.check_suppress(da)
        temperature = self._dopamine.compute_temperature(da)
        floor = getattr(self._serotonin, "temperature_floor", None)
        if floor is not None:
            temperature = max(temperature, float(floor))

        ddm_adjustment: Optional[DDMAdjustment] = None
        if ddm_base_drift is not None and ddm_base_boundary is not None:
            kwargs = dict(ddm_kwargs or {})
            serotonin_factor = serotonin_signal if serotonin_signal is not None else (serotonin_level if serotonin_level is not None else 0.0)
            kwargs.setdefault("serotonin_hold", float(serotonin_factor) if hold else 0.0)
            ddm_adjustment = adapt_ddm_parameters(
                dopamine_level=da,
                base_drift=float(ddm_base_drift),
                base_boundary=float(ddm_base_boundary),
                **kwargs,
            )

        extras: Dict[str, float] = {
            "tonic_level": float(self._dopamine.tonic_level),
            "phasic_level": float(self._dopamine.phasic_level),
            "tonic_to_phasic_ratio": float(getattr(self._dopamine, "tonic_to_phasic_ratio", 0.0)),
        }
        if serotonin_level is not None:
            extras["serotonin_level"] = float(serotonin_level)

        return GateEvaluation(
            go=go,
            hold=hold,
            no_go=no_go,
            temperature=temperature,
            dopamine_level=da,
            hold_reason=hold_reason,
            ddm_adjustment=ddm_adjustment,
            extras=extras if extras else None,
        )
