# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Aggregate neuromodulator signals into a Go/No-Go/Hold decision."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from geosync.core.neuro.numeric_config import STABILITY_EPSILON


class TemperatureBoundsProvider(Protocol):
    """Structural boundary required by ActionGate.

    ActionGate only needs temperature bounds. It MUST NOT depend on a concrete
    dopamine controller implementation, constructor, configuration shape, or
    mutable controller state.
    """

    def temperature_bounds(self) -> tuple[float, float]:
        """Return inclusive lower/upper temperature bounds."""


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
        dopamine_ctrl: TemperatureBoundsProvider,
        *,
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        # Backward-compatible structural provider alias: legacy integration and
        # invariant probes may inspect ``_dopamine``. The type boundary remains
        # structural; no concrete controller import, subclass, or constructor is
        # required by ActionGate.
        self._dopamine = dopamine_ctrl
        self._temperature_bounds = dopamine_ctrl.temperature_bounds
        if logger is None:
            logger = getattr(dopamine_ctrl, "_log", None)
        self._logger = logger or (lambda name, value: None)

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).debug("ActionGate logger failed for %s: %s", name, exc)

    def evaluate(
        self,
        dopamine: DopamineSnapshot,
        *,
        serotonin: Optional[SerotoninSnapshot] = None,
        gaba: Optional[GABASnapshot] = None,
        na_ach: Optional[NAACHSnapshot] = None,
    ) -> GateEvaluation:
        da = float(min(1.0, max(0.0, dopamine.level)))  # INV-DA3: DA ∈ [0,1]
        temperature = float(max(STABILITY_EPSILON, dopamine.temperature))
        go_threshold = min(1.0, max(0.0, dopamine.go_threshold))  # INV-DA3: threshold ∈ [0,1]
        no_go_threshold = min(1.0, max(0.0, dopamine.no_go_threshold))  # INV-DA3: threshold ∈ [0,1]
        hold_threshold = min(1.0, max(0.0, dopamine.hold_threshold))  # INV-DA3: threshold ∈ [0,1]

        hold = not dopamine.release_gate_open or da < hold_threshold
        serotonin_floor = 0.0
        if serotonin is not None:
            hold = hold or serotonin.hold
            serotonin_floor = float(max(0.0, serotonin.temperature_floor))

        inhibition = 0.0
        stdp_dw = 0.0
        if gaba is not None:
            inhibition = min(0.99, max(0.0, gaba.inhibition))  # INV-GABA1: gate ∈ [0,1]
            stdp_dw = float(gaba.stdp_dw)
            if inhibition >= 0.8:
                hold = True

        attention = 1.0
        temp_scale = 1.0
        if na_ach is not None:
            attention = min(
                2.0, max(0.2, na_ach.attention)
            )  # bounds: NA/ACh attention gain ∈ [0.2, 2.0]
            temp_scale = min(
                3.0, max(0.2, na_ach.temperature_scale)
            )  # bounds: temperature scale ∈ [0.2, 3.0]

        score = da * (1.0 - inhibition)
        score *= attention
        score = min(1.0, max(0.0, score))  # INV-DA3: composite score ∈ [0,1]

        # INV-DA3 (ordering): a valid gate needs no_go_threshold ≤ go_threshold so
        # the No-Go band (score < no_go_threshold) and Go band (score > go_threshold)
        # cannot overlap. ActionGate accepts an arbitrary DopamineSnapshot, so —
        # unlike the internal controller path, which pre-orders via
        # check_monotonic_thresholds — the caller may hand us a misordered config.
        # A safety gate must never emit GO under an invalid configuration: fail
        # closed to No-Go rather than let both go and no_go fire on one score.
        thresholds_valid = no_go_threshold <= go_threshold

        go = thresholds_valid and score > go_threshold and not hold
        no_go = (not thresholds_valid) or hold or score < no_go_threshold
        # No-Go dominates a contradictory Go (protective priority). For a valid,
        # ordered config the two are already mutually exclusive when not held, so
        # this only changes behaviour on the misordered (fail-closed) path.
        if no_go:
            decision = "NO_GO"
        elif go:
            decision = "GO"
        else:
            decision = "HOLD"
        # Derive the reported flags from the single decision so a consumer reading
        # .go / .no_go can never observe a state that contradicts .decision.
        go = decision == "GO"
        no_go = decision == "NO_GO"

        temperature *= temp_scale
        if serotonin_floor > 0.0:
            temperature = max(temperature, serotonin_floor)
        t_bounds = self._temperature_bounds()
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
