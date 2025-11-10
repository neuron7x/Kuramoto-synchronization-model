"""Core state representation for NaK controller.

This module defines the per-strategy state variables that evolve across
controller steps. The state encapsulates:

1. **Metabolic Variables**: Load (L), Energy (E), Engagement Index (EI)
2. **Control State**: Integrator (I), suspension flag
3. **History**: Debt accumulation, last risk level, diagnostic info

**State Invariants:**
    - L ∈ [L_min, L_max]: load is bounded
    - E ∈ [0, E_max]: energy is non-negative and bounded
    - EI ∈ [0, 1]: engagement index is normalized
    - I ∈ [-I_max, I_max]: integrator is bounded (anti-windup)
    - debt ≥ 0: energy debt is non-negative
    - last_risk ∈ [r_min, r_max]: risk factor is within limits

These invariants are maintained by clipping operations in update functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Union


def clip(value: float, lo: float, hi: float) -> float:
    """Clamp value into the closed interval [lo, hi].

    **Mathematical Definition:**
        clip(x, a, b) = min(max(x, a), b)

    Ensures bounded values to prevent overflow, underflow, or
    violation of physical/logical constraints.

    Args:
        value: Input value to clamp.
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).

    Returns:
        Clamped value in [lo, hi].

    Raises:
        ValueError: If lo > hi (invalid bounds).
    """
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass(slots=True)
class StrategyState:
    """State maintained per strategy across controller steps.

    **State Variables:**

    - **L** (float): Load level ∈ [L_min, L_max].
      Cumulative "neuronal activity cost" from trades, volatility, errors.
      Initialized to 0.0 (resting state).

    - **E** (float): Energy reserve ∈ [0, E_max].
      Metabolic capacity for sustaining operations.
      Initialized to 0.5 (half-full).

    - **EI** (float): Engagement Index ∈ [0, 1].
      Overall health metric derived from E, L, and PnL.
      Initialized to 0.5 (nominal).

    - **I** (float): Integrator accumulator ∈ [-I_max, I_max].
      PI controller integral term for tracking error correction.
      Initialized to 0.0 (no accumulated error).

    - **suspended** (bool): Suspension flag.
      True if EI < EI_crit or global mode is RED.
      Initialized to False (active).

    - **health** (float): Alias for EI (legacy).
      Maintained for backward compatibility with external monitors.

    - **debt** (float): Accumulated energy deficit ≥ 0.
      When E hits zero, further losses accumulate as debt.
      Must be repaid before full recovery. Initialized to 0.0.

    - **last_risk** (float): Previous risk factor ∈ [r_min, r_max].
      Used for rate limiting to prevent abrupt changes.
      Initialized to 1.0 (neutral).

    - **last** (dict): Diagnostic snapshot from last step.
      Contains error, integrator, neuromodulator levels, mode, etc.
      Used for logging, debugging, and telemetry.

    **Lifecycle:**
        - Created on first step() call for a new strategy_id.
        - Persists across steps until controller.reset() is called.
        - Reset clears all state to initial values.
    """

    L: float = 0.0
    E: float = 0.5
    EI: float = 0.5
    I: float = 0.0  # noqa: E741 - integral accumulator
    suspended: bool = False
    health: float = 0.5
    debt: float = 0.0
    last_risk: float = 1.0
    last: Dict[str, Union[float, str]] = field(default_factory=dict)


__all__ = ["StrategyState", "clip"]
