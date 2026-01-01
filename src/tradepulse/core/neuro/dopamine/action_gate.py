"""Aggregate neuromodulator signals into a Go/No-Go/Hold decision."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON

from .dopamine_controller import DopamineController


@dataclass(frozen=True)
class DopamineSnapshot:
    level: float
    temperature: float
    go_threshold: float
    hold_threshold: float
    no_go_threshold: float
    release_gate_open: bool


@dataclass(frozen=True)
class SerotoninSnapshot:
    level: float
    hold: bool
    temperature_floor: float


@dataclass(frozen=True)
class GABASnapshot:
    inhibition: float
    stdp_dw: float


@dataclass(frozen=True)
class NAACHSnapshot:
    arousal: float
    attention: float
    risk_multiplier: float
    temperature_scale: float


@dataclass(frozen=True)
class GateEvaluation:
    decision: str
    score: float
    go: bool
    hold: bool
    no_go: bool
    temperature: float
    dopamine_level: float


class ActionGate:
    """Fuse dopamine, serotonin, GABA, and NA/ACh modulators."""

    def __init__(
        self,
        dopamine_ctrl: DopamineController,
        *,
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._dopamine = dopamine_ctrl
        if logger is None:
            logger = getattr(dopamine_ctrl, "_log", None)
        self._logger = logger or (lambda name, value: None)

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).debug(
                "ActionGate logger failed for %s: %s", name, exc
            )

    def evaluate(
        self,
        dopamine: DopamineSnapshot,
        *,
        serotonin: Optional[SerotoninSnapshot] = None,
        gaba: Optional[GABASnapshot] = None,
        na_ach: Optional[NAACHSnapshot] = None,
    ) -> GateEvaluation:
        da = float(min(1.0, max(0.0, dopamine.level)))
        temperature = float(max(STABILITY_EPSILON, dopamine.temperature))
        go_threshold = min(1.0, max(0.0, dopamine.go_threshold))
        no_go_threshold = min(1.0, max(0.0, dopamine.no_go_threshold))
        hold_threshold = min(1.0, max(0.0, dopamine.hold_threshold))

        hold = not dopamine.release_gate_open or da < hold_threshold
        serotonin_floor = 0.0
        if serotonin is not None:
            hold = hold or serotonin.hold
            serotonin_floor = float(max(0.0, serotonin.temperature_floor))

        inhibition = 0.0
        stdp_dw = 0.0
        if gaba is not None:
            inhibition = min(0.99, max(0.0, gaba.inhibition))
            stdp_dw = float(gaba.stdp_dw)
            if inhibition >= 0.8:
                hold = True

        attention = 1.0
        temp_scale = 1.0
        if na_ach is not None:
            attention = min(2.0, max(0.2, na_ach.attention))
            temp_scale = min(3.0, max(0.2, na_ach.temperature_scale))

        score = da * (1.0 - inhibition)
        score *= attention
        score = min(1.0, max(0.0, score))

        go = score > go_threshold and not hold
        no_go = hold or score < no_go_threshold
        decision = "HOLD"
        if go:
            decision = "GO"
        elif no_go:
            decision = "NO_GO"

        temperature *= temp_scale
        if serotonin_floor > 0.0:
            temperature = max(temperature, serotonin_floor)
        t_bounds = self._dopamine.temperature_bounds()
        temperature = min(t_bounds[1], max(t_bounds[0], temperature))

        self._log("tacl.bg.score", score)
        self._log("tacl.bg.route", 1.0 if go else 0.0)
        self._log(
            "tacl.ag.decision",
            {
                "GO": 2.0,
                "HOLD": 1.0,
                "NO_GO": 0.0,
            }[decision],
        )
        if gaba is not None:
            self._log("tacl.gaba.stdp_dw", stdp_dw)

        return GateEvaluation(
            decision=decision,
            score=score,
            go=go,
            hold=hold,
            no_go=no_go,
            temperature=temperature,
            dopamine_level=da,
        )
