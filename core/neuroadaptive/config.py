"""Configuration for the neuroadaptive decision system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(slots=True)
class NeuroAdaptiveConfig:
    """Configuration for neuroadaptive decision engine.

    Attributes:
        weights: Weight for each neuromodulator signal (must sum to 1.0)
        ranges: Valid ranges for each signal type
        ema_alpha: Exponential moving average alpha parameter
        gate_thresholds: Thresholds for FSM state transitions
        blend_ratio: Ratio for blending base and neuro confidence
    """

    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "dopamine_rpe": 0.30,
            "serotonin_veto": 0.25,
            "threat_score": 0.25,
            "energy_efficiency": 0.20,
        }
    )
    ranges: Dict[str, Tuple[float, float]] = field(
        default_factory=lambda: {
            "dopamine_rpe": (-1.0, 1.0),
            "serotonin_veto": (0.0, 1.0),
            "threat_score": (0.0, 1.0),
            "energy_efficiency": (0.0, 1.0),
            "prior_confidence": (0.0, 1.0),
        }
    )
    ema_alpha: float = 0.5
    gate_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "hard_block": 0.2,
            "soft_block": 0.4,
            "soft_allow": 0.6,
            "hard_allow": 0.8,
        }
    )
    blend_ratio: float = 0.3

    def validated(self) -> NeuroAdaptiveConfig:
        """Validate configuration parameters.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If validation fails
        """
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total_weight:.6f}")

        if not (0.0 < self.ema_alpha <= 1.0):
            raise ValueError("ema_alpha must be in (0.0, 1.0]")

        if not (0.0 <= self.blend_ratio <= 1.0):
            raise ValueError("blend_ratio must be in [0.0, 1.0]")

        for name, (low, high) in self.ranges.items():
            if low >= high:
                raise ValueError(f"invalid range for {name}: low={low}, high={high}")

        for key in ("hard_block", "soft_block", "soft_allow", "hard_allow"):
            if key not in self.gate_thresholds:
                raise ValueError(f"missing gate_thresholds.{key}")

        return self
