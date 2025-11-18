"""Configuration for the heuristic gate system."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Iterable, Mapping, Tuple

from .types import HeuristicSignals


@dataclass(frozen=True, slots=True)
class HeuristicGateConfig:
    """Immutable configuration for heuristic decision gate.

    Attributes:
        _weights: Weight for each heuristic signal (must sum to 1.0)
        _ranges: Valid ranges for each signal type
        blend_ratio: Ratio for blending base and gate confidence
        _thresholds: Thresholds for FSM state transitions
    """

    _weights: MappingProxyType[str, float]
    _ranges: MappingProxyType[str, Tuple[float, float]]
    blend_ratio: float
    _thresholds: MappingProxyType[str, float]

    @property
    def weights(self) -> Mapping[str, float]:
        """Get signal weights mapping."""
        return self._weights

    @property
    def ranges(self) -> Mapping[str, Tuple[float, float]]:
        """Get signal ranges mapping."""
        return self._ranges

    @property
    def gate_thresholds(self) -> Mapping[str, float]:
        """Get gate threshold mapping."""
        return self._thresholds

    @classmethod
    def default(cls) -> HeuristicGateConfig:
        """Create default configuration with standard parameters.

        Returns:
            Validated default configuration
        """
        weights: Dict[str, float] = {
            "reward_error": 0.30,
            "inhibition_strength": 0.25,
            "risk_score": 0.25,
            "energy_efficiency": 0.20,
        }
        ranges: Dict[str, Tuple[float, float]] = {
            "reward_error": (-1.0, 1.0),
            "inhibition_strength": (0.0, 1.0),
            "risk_score": (0.0, 1.0),
            "energy_efficiency": (0.0, 1.0),
            "prior_confidence": (0.0, 1.0),
        }
        thresholds: Dict[str, float] = {
            "hard_block": 0.2,
            "soft_block": 0.4,
            "soft_allow": 0.6,
            "hard_allow": 0.8,
        }
        return cls(
            _weights=MappingProxyType(dict(weights)),
            _ranges=MappingProxyType(dict(ranges)),
            blend_ratio=0.3,
            _thresholds=MappingProxyType(dict(thresholds)),
        ).validated()

    @classmethod
    def calibrate_from_decisions(
        cls,
        decisions: Iterable[tuple[HeuristicSignals, bool]],
        *,
        blend_ratio: float | None = None,
    ) -> HeuristicGateConfig:
        """Calibrate configuration from historical decision data.

        Args:
            decisions: Iterable of (signals, outcome) pairs for calibration
            blend_ratio: Optional custom blend ratio, uses 0.3 if not provided

        Returns:
            Calibrated configuration

        Note:
            Current implementation uses default weights. Future versions
            may implement statistical calibration based on decision outcomes.
        """
        weights: Dict[str, float] = {
            "reward_error": 0.30,
            "inhibition_strength": 0.25,
            "risk_score": 0.25,
            "energy_efficiency": 0.20,
        }
        ranges: Dict[str, Tuple[float, float]] = {
            "reward_error": (-1.0, 1.0),
            "inhibition_strength": (0.0, 1.0),
            "risk_score": (0.0, 1.0),
            "energy_efficiency": (0.0, 1.0),
            "prior_confidence": (0.0, 1.0),
        }
        thresholds: Dict[str, float] = {
            "hard_block": 0.2,
            "soft_block": 0.4,
            "soft_allow": 0.6,
            "hard_allow": 0.8,
        }
        br = 0.3 if blend_ratio is None else blend_ratio
        return cls(
            _weights=MappingProxyType(dict(weights)),
            _ranges=MappingProxyType(dict(ranges)),
            blend_ratio=br,
            _thresholds=MappingProxyType(dict(thresholds)),
        ).validated()

    def validated(self) -> HeuristicGateConfig:
        """Validate configuration parameters.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If validation fails
        """
        total_weight = sum(self._weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total_weight:.6f}")

        if not (0.0 <= self.blend_ratio <= 1.0):
            raise ValueError("blend_ratio must be in [0.0, 1.0]")

        for name, (low, high) in self._ranges.items():
            if low >= high:
                raise ValueError(f"invalid range for {name}: low={low}, high={high}")

        for key in ("hard_block", "soft_block", "soft_allow", "hard_allow"):
            if key not in self._thresholds:
                raise ValueError(f"missing gate_thresholds.{key}")

        hb = self._thresholds["hard_block"]
        sb = self._thresholds["soft_block"]
        sa = self._thresholds["soft_allow"]
        ha = self._thresholds["hard_allow"]
        if not (0.0 <= hb < sb < sa < ha <= 1.0):
            raise ValueError(f"invalid thresholds ordering: {hb}, {sb}, {sa}, {ha}")

        return self
