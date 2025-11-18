"""Telemetry utilities for heuristic gate decision events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .engine import GateMetrics
    from .types import GateState


def gate_event_payload(
    *,
    gate_state: GateState,
    metrics: GateMetrics | None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build telemetry payload for heuristic gate decision events.

    Args:
        gate_state: Current FSM gate state
        metrics: Gate metrics from decision processing
        extra: Additional context to include in payload

    Returns:
        Dictionary containing telemetry event data
    """
    payload: Dict[str, Any] = {
        "gate_state": gate_state.name,
    }

    if metrics is not None:
        payload.update(
            {
                "gate_confidence": metrics.confidence,
                "gate_data_quality_ok": metrics.data_quality_ok,
                "gate_data_quality_issues": list(metrics.data_quality_issues),
                "gate_decision_impact": metrics.decision_impact,
                "gate_signal_contributions": metrics.signal_contributions,
            }
        )

    if extra:
        payload.update(extra)

    return payload
