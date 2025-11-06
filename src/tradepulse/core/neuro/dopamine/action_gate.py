from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from .dopamine_controller import DopamineController


@runtime_checkable
class SerotoninLike(Protocol):
    """Protocol describing the serotonin interface required by the gate."""

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        ...

@dataclass(frozen=True)
class GateEvaluation:
    """Outcome of the action gate evaluation."""

    go: bool
    hold: bool
    no_go: bool
    temperature: float
    dopamine_level: float


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
    ) -> GateEvaluation:
        da = self._dopamine.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        go = self._dopamine.check_invigoration(da)
        hold = False
        if self._serotonin is not None:
            hold = bool(self._serotonin.check_cooldown(serotonin_signal))
        if hold:
            go = False
        no_go = hold or self._dopamine.check_suppress(da)
        temperature = self._dopamine.compute_temperature(da)
        floor = getattr(self._serotonin, "temperature_floor", None)
        if floor is not None:
            temperature = max(temperature, float(floor))
        return GateEvaluation(
            go=go,
            hold=hold,
            no_go=no_go,
            temperature=temperature,
            dopamine_level=da,
        )
