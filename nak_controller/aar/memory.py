"""Memory storage for AAR (Acceptor of Action Result).

This module provides storage mechanisms for AAR entries:
- Temporary buffer for in-memory retention
- Indexing by action type, strategy, and time
- Lookup and query functionality

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from .aggregators import AggregateStats, ModeAggregator, StrategyAggregator
from .core import compute_error
from .types import AAREntry, ActionEvent, Outcome, Prediction


@dataclass
class AARTracker:
    """Tracks actions, predictions, and outcomes to compute AAR entries.

    AARTracker maintains the lifecycle of AAR entries:
    1. Record action when initiated
    2. Record prediction (expected outcome)
    3. Record outcome when action completes
    4. Compute error signal and store complete entry

    Attributes:
        max_pending: Maximum number of pending actions (without outcomes).
        max_entries: Maximum number of completed entries to retain.
        pnl_scale: Scale for PnL error computation.
        latency_scale: Scale for latency error computation.
        slippage_scale: Scale for slippage error computation.
    """

    max_pending: int = 1000
    max_entries: int = 10000
    pnl_scale: float = 100.0
    latency_scale: float = 10.0
    slippage_scale: float = 0.001

    _pending_actions: dict[str, ActionEvent] = field(default_factory=dict)
    _pending_predictions: dict[str, Prediction] = field(default_factory=dict)
    _pending_contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _entries: Deque[AAREntry] = field(default_factory=lambda: deque())
    _entries_by_action_id: dict[str, AAREntry] = field(default_factory=dict)
    _strategy_aggregator: StrategyAggregator = field(default_factory=StrategyAggregator)
    _mode_aggregator: ModeAggregator = field(default_factory=ModeAggregator)

    def __post_init__(self) -> None:
        """Initialize with max length constraints."""
        self._entries = deque(maxlen=self.max_entries)
        self._strategy_aggregator = StrategyAggregator()
        self._mode_aggregator = ModeAggregator()

    def record_action(
        self,
        action: ActionEvent,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a new action event.

        Args:
            action: The action event to record.
            context: Optional system context snapshot.

        Raises:
            ValueError: If action_id already exists in pending.
        """
        if action.action_id in self._pending_actions:
            raise ValueError(f"Action {action.action_id} already pending")

        # Enforce max pending limit
        if len(self._pending_actions) >= self.max_pending:
            # Remove oldest pending action
            oldest_id = next(iter(self._pending_actions))
            self._pending_actions.pop(oldest_id, None)
            self._pending_predictions.pop(oldest_id, None)
            self._pending_contexts.pop(oldest_id, None)

        self._pending_actions[action.action_id] = action
        self._pending_contexts[action.action_id] = context or {}

    def record_prediction(self, prediction: Prediction) -> None:
        """Record a prediction for an existing action.

        Args:
            prediction: The prediction to record.

        Raises:
            ValueError: If no action exists for this prediction.
        """
        if prediction.action_id not in self._pending_actions:
            raise ValueError(f"No pending action for prediction {prediction.action_id}")

        self._pending_predictions[prediction.action_id] = prediction

    def record_outcome(
        self,
        outcome: Outcome,
        mode: str = "GREEN",
    ) -> AAREntry | None:
        """Record an outcome and compute the complete AAR entry.

        Args:
            outcome: The outcome to record.
            mode: Current system mode for mode aggregation.

        Returns:
            The completed AAREntry, or None if no matching prediction.

        Raises:
            ValueError: If no action exists for this outcome.
        """
        action_id = outcome.action_id

        if action_id not in self._pending_actions:
            raise ValueError(f"No pending action for outcome {action_id}")

        action = self._pending_actions.pop(action_id)
        context = self._pending_contexts.pop(action_id, {})

        # If no prediction was recorded, create a default one
        if action_id not in self._pending_predictions:
            prediction = Prediction(
                action_id=action_id,
                expected_pnl=0.0,
                expected_latency_ms=0.0,
                expected_slippage=0.0,
                confidence=0.0,
                timestamp=action.timestamp,
            )
        else:
            prediction = self._pending_predictions.pop(action_id)

        # Compute error signal
        error_signal = compute_error(
            prediction,
            outcome,
            context,
            pnl_scale=self.pnl_scale,
            latency_scale=self.latency_scale,
            slippage_scale=self.slippage_scale,
        )

        # Create and store entry
        entry = AAREntry(
            action_id=action_id,
            action=action,
            prediction=prediction,
            outcome=outcome,
            error_signal=error_signal,
            context_snapshot=context,
        )

        self._entries.append(entry)
        self._entries_by_action_id[action_id] = entry

        # Clean up old entries from lookup dict less frequently
        # Only cleanup when significantly over limit to avoid O(n) overhead
        if len(self._entries_by_action_id) > self.max_entries * 1.2:
            # Remove entries not in the deque
            valid_ids = {e.action_id for e in self._entries}
            to_remove = [k for k in self._entries_by_action_id if k not in valid_ids]
            for k in to_remove:
                del self._entries_by_action_id[k]

        # Update aggregators
        self._strategy_aggregator.add(entry)
        self._mode_aggregator.add(entry, mode)

        return entry

    def get_entry(self, action_id: str) -> AAREntry | None:
        """Get a completed entry by action ID.

        Args:
            action_id: The action ID to look up.

        Returns:
            The AAREntry if found, None otherwise.
        """
        return self._entries_by_action_id.get(action_id)

    def get_recent_entries(self, n: int = 10) -> list[AAREntry]:
        """Get the N most recent completed entries.

        Args:
            n: Number of entries to return.

        Returns:
            List of up to N most recent entries (newest first).
        """
        entries_list = list(self._entries)
        return entries_list[-n:][::-1]

    def get_entries_by_strategy(self, strategy_id: str) -> list[AAREntry]:
        """Get all entries for a specific strategy.

        Args:
            strategy_id: The strategy ID to filter by.

        Returns:
            List of entries for the strategy.
        """
        return [e for e in self._entries if e.action.strategy_id == strategy_id]

    def get_entries_by_action_type(self, action_type: str) -> list[AAREntry]:
        """Get all entries for a specific action type.

        Args:
            action_type: The action type to filter by.

        Returns:
            List of entries matching the action type.
        """
        return [e for e in self._entries if e.action.action_type == action_type]

    def get_entries_since(self, timestamp: float) -> list[AAREntry]:
        """Get all entries since a given timestamp.

        Args:
            timestamp: Unix timestamp to filter from.

        Returns:
            List of entries with outcome timestamp >= given timestamp.
        """
        return [e for e in self._entries if e.outcome.timestamp >= timestamp]

    def get_strategy_stats(self, strategy_id: str) -> AggregateStats:
        """Get aggregated stats for a strategy.

        Args:
            strategy_id: The strategy to query.

        Returns:
            AggregateStats for the strategy.
        """
        return self._strategy_aggregator.get_stats(strategy_id)

    def get_mode_stats(self, mode: str) -> AggregateStats:
        """Get aggregated stats for a mode.

        Args:
            mode: The mode to query ("GREEN", "AMBER", "RED").

        Returns:
            AggregateStats for the mode.
        """
        return self._mode_aggregator.get_stats(mode)

    def get_all_strategy_stats(self) -> dict[str, AggregateStats]:
        """Get aggregated stats for all strategies.

        Returns:
            Dictionary mapping strategy IDs to their stats.
        """
        return self._strategy_aggregator.get_all_stats()

    def get_all_mode_stats(self) -> dict[str, AggregateStats]:
        """Get aggregated stats for all modes.

        Returns:
            Dictionary mapping modes to their stats.
        """
        return self._mode_aggregator.get_all_stats()

    def pending_count(self) -> int:
        """Get the number of pending actions without outcomes.

        Returns:
            Number of pending actions.
        """
        return len(self._pending_actions)

    def entry_count(self) -> int:
        """Get the number of completed entries.

        Returns:
            Number of completed entries.
        """
        return len(self._entries)

    def clear(self) -> None:
        """Clear all pending actions and completed entries."""
        self._pending_actions.clear()
        self._pending_predictions.clear()
        self._pending_contexts.clear()
        self._entries.clear()
        self._entries_by_action_id.clear()
        self._strategy_aggregator = StrategyAggregator()
        self._mode_aggregator = ModeAggregator()


def create_action_event(
    action_type: str,
    strategy_id: str,
    parameters: dict[str, Any] | None = None,
    action_id: str | None = None,
) -> ActionEvent:
    """Helper function to create an ActionEvent with auto-generated ID and timestamp.

    Args:
        action_type: Type of action ("trade", "mode_change", "risk_adjust").
        strategy_id: Strategy that triggered this action.
        parameters: Action-specific parameters.
        action_id: Optional explicit ID, otherwise auto-generated.

    Returns:
        A new ActionEvent.
    """
    import uuid

    if action_id is None:
        action_id = str(uuid.uuid4())

    return ActionEvent(
        action_id=action_id,
        action_type=action_type,
        strategy_id=strategy_id,
        timestamp=time.time(),
        parameters=parameters or {},
    )


__all__ = [
    "AARTracker",
    "create_action_event",
]
