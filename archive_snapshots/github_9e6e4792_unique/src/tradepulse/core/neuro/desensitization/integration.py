from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Literal, Tuple

from .gate import DesensitizationGate


@dataclass(slots=True)
class GateStepIO:
    """Structured output returned when stepping the desensitization gate."""

    shaped_reward: float
    size: float
    temp: float
    state: Dict[str, Dict[str, float]]


def run_gate_step(
    gate: DesensitizationGate,
    *,
    reward: float,
    features: Iterable[float],
    drawdown: float,
    vol: float,
    hpa_tone: float,
    base_temperature: float,
    size_hint: float,
) -> GateStepIO:
    """Convenience wrapper producing a size decision and telemetry."""

    shaped_reward, size_gate, temp_abs, state = gate.step(
        reward,
        features=features,
        drawdown=drawdown,
        vol=vol,
        hpa_tone=hpa_tone,
        base_temperature=base_temperature,
    )
    size = size_hint * size_gate
    state["combined"]["lambda"] = state["combined"].get(
        "lambda_", state["combined"].get("lambda", 0.05)
    )
    return GateStepIO(
        shaped_reward=shaped_reward, size=size, temp=temp_abs, state=state
    )


def apply_to_policy_decision(
    decision: Tuple[Literal["GO", "NO_GO", "HOLD"], float],
    size_gate: float,
) -> Tuple[Literal["GO", "NO_GO", "HOLD"], float]:
    """Apply the derived size gate to an upstream policy decision."""

    action, size_hint = decision
    return action, max(0.0, min(1.0, size_hint * size_gate))
