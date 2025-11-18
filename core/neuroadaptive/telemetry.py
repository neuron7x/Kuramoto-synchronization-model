"""Telemetry utilities for neuroadaptive decision events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .engine import NeuroMetrics
    from .types import NeuroGateState


def neuro_event_payload(
    *,
    gate_state: NeuroGateState,
    metrics: NeuroMetrics | None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build telemetry payload for neuroadaptive decision events.

    Args:
        gate_state: Current FSM gate state
        metrics: Neuro metrics from decision processing
        extra: Additional context to include in payload

    Returns:
        Dictionary containing telemetry event data
    """
    base: Dict[str, Any] = {
        "gate_state": gate_state.name,
    }

    if metrics:
        base.update(
            {
                "neuro_confidence": metrics.confidence,
                "neuro_data_quality_ok": metrics.data_quality_ok,
                "neuro_data_quality_issues": list(metrics.data_quality_issues),
                "neuro_decision_impact": metrics.decision_impact,
                "neuro_signal_contributions": metrics.signal_contributions,
            }
        )

    if extra:
        base.update(extra)

    return base
