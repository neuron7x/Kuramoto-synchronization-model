from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from .dopamine_controller import DopamineController
from .ddm_adapter import DDMThresholds


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
    """Coordinate dopamine Go/Hold/No-Go signals with serotonin vetoes and DDM thresholds."""

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
        thresholds: Optional[DDMThresholds] = None,
        release_gate_open: Optional[bool] = None,
    ) -> GateEvaluation:
        """Return Go/Hold/No-Go decision given dopamine, serotonin and optional DDM thresholds."""
        da = self._dopamine.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = min(1.0, max(0.0, da))

        cfg = self._dopamine.config
        go_threshold = float(cfg["invigoration_threshold"])
        no_go_threshold = float(cfg["no_go_threshold"])
        hold_threshold = float(cfg.get("hold_threshold", 0.5))
        temperature_scale = 1.0
        if thresholds is not None:
            go_threshold = thresholds.go_threshold
            no_go_threshold = thresholds.no_go_threshold
            hold_threshold = thresholds.hold_threshold
            temperature_scale = thresholds.temperature_scale

        go_threshold = min(1.0, max(0.0, go_threshold))
        no_go_threshold = min(1.0, max(0.0, no_go_threshold))
        hold_threshold = min(1.0, max(0.0, hold_threshold))

        release_gate = True if release_gate_open is None else bool(release_gate_open)
        hold = not release_gate or da < hold_threshold

        if self._serotonin is not None:
            hold = hold or bool(self._serotonin.check_cooldown(serotonin_signal))

        go = da > go_threshold and not hold
        no_go = hold or da < no_go_threshold

        temperature = self._dopamine.compute_temperature(da)
        temperature *= temperature_scale
        t_min, t_max = self._dopamine.temperature_bounds()
        temperature = min(t_max, max(t_min, temperature))
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
