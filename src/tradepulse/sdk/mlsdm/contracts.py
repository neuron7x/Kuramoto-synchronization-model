"""Public data contracts for the MLSDM SDK.

This module defines the data structures used by the MLSDM public API.
All contracts are immutable dataclasses designed for safe data exchange
between the SDK and user code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

__all__ = [
    "BiomarkerState",
    "DecisionState",
    "OptimizationResult",
    "ReplayTransition",
    "TrainingStep",
]


@dataclass(frozen=True, slots=True)
class BiomarkerState:
    """Biomarker readings from the FHMC controller.

    Attributes:
        orexin: Arousal/motivation signal in [0, 1]. Higher values indicate
            increased exploration tendency and risk appetite.
        threat: Threat assessment in [0, 1]. Higher values indicate detected
            danger, typically from drawdown, volatility shocks, or regime changes.
        state: Current FHMC state, one of "WAKE" or "SLEEP".
        alpha_history: DFA alpha values computed from recent action series.
        slope_history: Aperiodic slope values from internal latent signals.
    """

    orexin: float
    threat: float
    state: str
    alpha_history: tuple[float, ...] = field(default_factory=tuple)
    slope_history: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DecisionState:
    """Internal decision state for the MLSDM system.

    Attributes:
        free_energy: Current system free energy (lower is better).
        baseline_free_energy: Baseline free energy for relative comparison.
        latency_spike: Ratio of current to baseline latency (1.0 = normal).
        steps_in_crisis: Number of consecutive steps in crisis mode.
        window_seconds: Recommended window for next decision in seconds.
    """

    free_energy: float
    baseline_free_energy: float
    latency_spike: float
    steps_in_crisis: int
    window_seconds: float


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Result of a CFGWO optimization run.

    Attributes:
        best_params: Optimal parameter vector found.
        best_score: Objective value at optimal parameters.
        iterations: Number of optimization iterations performed.
        pack_size: Population size used in the optimizer.
    """

    best_params: np.ndarray
    best_score: float
    iterations: int
    pack_size: int

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "best_params": self.best_params.tolist(),
            "best_score": self.best_score,
            "iterations": self.iterations,
            "pack_size": self.pack_size,
        }


@dataclass(frozen=True, slots=True)
class ReplayTransition:
    """A single experience transition stored in the replay buffer.

    Attributes:
        state: Observation state before the action.
        action: Action taken.
        reward: Reward received.
        next_state: Observation state after the action.
        priority: Priority weight for sampling (higher = more important).
        cp_score: Change-point score at this transition.
    """

    state: np.ndarray
    action: np.ndarray
    reward: float
    next_state: np.ndarray
    priority: float
    cp_score: float


@dataclass(frozen=True, slots=True)
class TrainingStep:
    """Training step output from agent learning.

    Attributes:
        td_error: Temporal difference error.
        orexin: Current orexin value used for exploration scaling.
        threat: Current threat value used for risk adjustment.
        state: Current FHMC state ("WAKE" or "SLEEP").
        timestamp: Timestamp of the training step.
    """

    td_error: float
    orexin: float
    threat: float
    state: str
    timestamp: datetime
