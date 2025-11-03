# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Recovery utilities for order ledger and state reconstruction.

This module provides utilities for recovering order management state from
persisted ledgers and snapshots, with optimizations to meet RTO requirements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping

from .order_ledger import OrderLedger, OrderLedgerConfig

__all__ = ["RecoveryStats", "RecoveryManager", "recover_from_ledger"]


@dataclass(slots=True)
class RecoveryStats:
    """Statistics about a recovery operation."""

    total_events: int
    events_replayed: int
    snapshot_used: bool
    snapshot_sequence: int | None
    duration_seconds: float
    corruption_detected: bool
    corruption_details: str | None
    recovery_successful: bool
    final_state: MutableMapping[str, Any] | None


class RecoveryManager:
    """Manages recovery operations with performance tracking."""

    def __init__(
        self,
        ledger: OrderLedger,
        *,
        state_builder: Callable[[MutableMapping[str, Any]], None] | None = None,
    ) -> None:
        """Initialize recovery manager.

        Args:
            ledger: The order ledger to recover from
            state_builder: Optional callback to build application state from events
        """
        self._ledger = ledger
        self._state_builder = state_builder

    def recover(
        self,
        *,
        verify_integrity: bool = True,
        use_snapshot: bool = True,
        max_events: int | None = None,
    ) -> RecoveryStats:
        """Recover state from ledger with performance tracking.

        Args:
            verify_integrity: Whether to verify checksums during replay
            use_snapshot: Whether to use snapshots to accelerate recovery
            max_events: Maximum number of events to replay (for testing)

        Returns:
            RecoveryStats with details about the recovery operation
        """
        start_time = time.perf_counter()

        snapshot_sequence = None
        snapshot_state = None

        # Try to load most recent snapshot if enabled
        if use_snapshot:
            snapshot_state = self._ledger.load_snapshot()
            if snapshot_state is not None:
                sequences = self._ledger.snapshot_sequences()
                if sequences:
                    snapshot_sequence = sequences[-1]

        # Determine starting point for replay
        start_sequence = 1
        if snapshot_sequence is not None and use_snapshot:
            start_sequence = snapshot_sequence + 1

        # Replay events from the starting point
        events_replayed = 0
        final_state = snapshot_state

        try:
            if start_sequence > 1:
                # Replay from after snapshot
                for event in self._ledger.replay_from(start_sequence, verify=verify_integrity):
                    if max_events is not None and events_replayed >= max_events:
                        break

                    # Use state snapshot from event if available
                    if event.state_snapshot is not None:
                        final_state = event.state_snapshot

                    # Call state builder if provided
                    if self._state_builder and event.order_snapshot:
                        self._state_builder(event.order_snapshot)

                    events_replayed += 1
            else:
                # Full replay from beginning
                for event in self._ledger.replay(verify=verify_integrity):
                    if max_events is not None and events_replayed >= max_events:
                        break

                    if event.state_snapshot is not None:
                        final_state = event.state_snapshot

                    if self._state_builder and event.order_snapshot:
                        self._state_builder(event.order_snapshot)

                    events_replayed += 1

            recovery_successful = True
        except ValueError as exc:
            # Corruption detected during replay
            recovery_successful = False
            final_state = None

        duration = time.perf_counter() - start_time

        return RecoveryStats(
            total_events=self._ledger._metadata.event_count,
            events_replayed=events_replayed,
            snapshot_used=snapshot_sequence is not None,
            snapshot_sequence=snapshot_sequence,
            duration_seconds=duration,
            corruption_detected=self._ledger.corruption_detected,
            corruption_details=self._ledger.corruption_details,
            recovery_successful=recovery_successful,
            final_state=final_state,
        )


def recover_from_ledger(
    ledger_path: Path | str,
    *,
    config: OrderLedgerConfig | None = None,
    verify_integrity: bool = True,
    use_snapshot: bool = True,
) -> tuple[OrderLedger, RecoveryStats]:
    """Convenience function to recover an order ledger and return stats.

    Args:
        ledger_path: Path to the ledger file
        config: Optional ledger configuration
        verify_integrity: Whether to verify checksums during recovery
        use_snapshot: Whether to use snapshots to accelerate recovery

    Returns:
        Tuple of (ledger, recovery_stats)
    """
    ledger = OrderLedger(ledger_path, config=config)
    manager = RecoveryManager(ledger)
    stats = manager.recover(verify_integrity=verify_integrity, use_snapshot=use_snapshot)
    return ledger, stats
