"""AAR (Acceptor of Action Result) - Feedback mechanism for neuro-controllers.

The AAR module provides a formal feedback loop that:
- Captures action events (trade orders, mode changes)
- Stores predictions (expected outcomes)
- Records actual outcomes after execution
- Computes error signals (prediction vs. outcome)
- Feeds back into neuro-controllers for adaptation

Main Components:
    - types: Core data structures (ActionEvent, Prediction, Outcome, ErrorSignal, AAREntry)
    - core: Error computation functions (compute_error, normalize_error)
    - aggregators: Rolling statistics (SlidingWindowAggregator, StrategyAggregator)
    - memory: Storage and tracking (AARTracker)

Example Usage:
    >>> from nak_controller.aar import AARTracker, create_action_event
    >>> from nak_controller.aar.types import Prediction, Outcome
    >>>
    >>> tracker = AARTracker()
    >>>
    >>> # Record action
    >>> action = create_action_event("trade", "momentum_1", {"side": "buy"})
    >>> tracker.record_action(action)
    >>>
    >>> # Record prediction
    >>> pred = Prediction(
    ...     action_id=action.action_id,
    ...     expected_pnl=100.0,
    ...     expected_latency_ms=5.0,
    ... )
    >>> tracker.record_prediction(pred)
    >>>
    >>> # Record outcome after execution
    >>> outcome = Outcome(
    ...     action_id=action.action_id,
    ...     actual_pnl=90.0,
    ...     actual_latency_ms=7.0,
    ... )
    >>> entry = tracker.record_outcome(outcome)
    >>>
    >>> # Use error signal for adaptation
    >>> print(f"Error: {entry.error_signal.normalized_error:.4f}")

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from .aggregators import (
    AggregateStats,
    ModeAggregator,
    SlidingWindowAggregator,
    StrategyAggregator,
)
from .core import (
    absolute_error,
    compute_error,
    error_sign,
    normalize_error,
    relative_error,
)
from .integration import (
    AARAdaptationConfig,
    AARAdaptationResult,
    AARAdaptationState,
    aar_dopamine_modulation,
    aar_serotonin_modulation,
    compute_aar_adaptation,
    compute_risk_reduction,
    should_freeze_adaptation,
    update_adaptation_state,
)
from .memory import AARTracker, create_action_event
from .types import AAREntry, ActionEvent, ErrorSignal, Outcome, Prediction

__all__ = [
    # Types
    "ActionEvent",
    "Prediction",
    "Outcome",
    "ErrorSignal",
    "AAREntry",
    # Core functions
    "absolute_error",
    "relative_error",
    "normalize_error",
    "error_sign",
    "compute_error",
    # Aggregators
    "AggregateStats",
    "SlidingWindowAggregator",
    "StrategyAggregator",
    "ModeAggregator",
    # Integration
    "AARAdaptationConfig",
    "AARAdaptationState",
    "AARAdaptationResult",
    "aar_dopamine_modulation",
    "aar_serotonin_modulation",
    "should_freeze_adaptation",
    "compute_risk_reduction",
    "compute_aar_adaptation",
    "update_adaptation_state",
    # Memory/Tracker
    "AARTracker",
    "create_action_event",
]
