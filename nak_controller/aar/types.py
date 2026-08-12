# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""AAR (Acceptor of Action Result) type definitions.

This module defines the core data structures for the AAR feedback mechanism
that compares predicted outcomes with actual outcomes to generate error
signals for neuro-controller adaptation.

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ActionEvent:
    """Represents a controlled system action.

    Actions include trade orders, mode changes, risk parameter adjustments,
    and strategy suspension/activation events.

    Attributes:
        action_id: Unique identifier (UUID) for traceability.
        action_type: Category of action ("trade", "mode_change", "risk_adjust").
        strategy_id: Which strategy triggered this action.
        timestamp: Unix timestamp when action was initiated.
        parameters: Action-specific parameters (e.g., side, size, price).
    """

    action_id: str
    action_type: str
    strategy_id: str
    timestamp: float
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Prediction:
    """Represents the expected outcome of an action.

    Predictions are made before or at the time of action execution and
    provide measurable expectations that can be compared against outcomes.

    Attributes:
        action_id: Links to the corresponding ActionEvent.
        expected_pnl: Expected profit/loss from the action.
        expected_latency_ms: Expected execution latency in milliseconds.
        expected_slippage: Expected slippage (price deviation from expected).
        confidence: Model confidence in prediction [0, 1].
        timestamp: When the prediction was made.
    """

    action_id: str
    expected_pnl: float = 0.0
    expected_latency_ms: float = 0.0
    expected_slippage: float = 0.0
    confidence: float = 0.5
    timestamp: float = 0.0


@dataclass(slots=True)
class Outcome:
    """Represents the actual result of an action.

    Outcomes are recorded after action execution completes and provide
    the observed values to compare against predictions.

    Attributes:
        action_id: Links to the corresponding ActionEvent.
        actual_pnl: Realized profit/loss from the action.
        actual_latency_ms: Actual execution latency in milliseconds.
        actual_slippage: Actual slippage observed.
        success: Whether the action completed successfully.
        timestamp: When the outcome was recorded.
    """

    action_id: str
    actual_pnl: float = 0.0
    actual_latency_ms: float = 0.0
    actual_slippage: float = 0.0
    success: bool = True
    timestamp: float = 0.0


@dataclass(slots=True)
class ErrorSignal:
    """Quantified difference between prediction and outcome.

    ErrorSignal provides normalized error metrics that drive controller
    adaptation. The sign convention:
    - sign = +1: Outcome better than predicted
    - sign = -1: Outcome worse than predicted
    - sign = 0: Outcome matches prediction within tolerance

    Attributes:
        action_id: Links to the corresponding ActionEvent.
        absolute_error: |prediction - outcome| (always positive).
        relative_error: (prediction - outcome) / scale.
        sign: Direction indicator (+1, 0, -1).
        normalized_error: Error mapped to [-1, 1] using tanh scaling.
        components: Per-dimension error breakdown.
    """

    action_id: str
    absolute_error: float = 0.0
    relative_error: float = 0.0
    sign: int = 0
    normalized_error: float = 0.0
    components: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class AAREntry:
    """Complete AAR record linking action, prediction, outcome, and error.

    AAREntry is the primary storage unit for the AAR feedback mechanism,
    containing all information needed to analyze prediction accuracy and
    drive controller adaptation.

    Attributes:
        action_id: Unique identifier linking all components.
        action: The original action event.
        prediction: The predicted outcome.
        outcome: The actual outcome.
        error_signal: Computed error between prediction and outcome.
        context_snapshot: System context at action time.
    """

    action_id: str
    action: ActionEvent
    prediction: Prediction
    outcome: Outcome
    error_signal: ErrorSignal
    context_snapshot: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ActionEvent",
    "Prediction",
    "Outcome",
    "ErrorSignal",
    "AAREntry",
]
