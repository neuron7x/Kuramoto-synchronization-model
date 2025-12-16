# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Multi-Level Synaptic Memory for MLSDM.

This module implements a three-level synaptic memory system with decay rates
(λ) controlling how quickly each level forgets information. Inspired by
biological memory consolidation processes.

Numerical Contract:
    - All input vectors must be finite (no NaN/Inf)
    - λ hierarchy must be enforced: λ3 <= λ2 <= λ1
    - strict_mode=True (default): raise on invalid data
    - strict_mode=False: sanitize with zeros and log warning

Memory Levels:
    - L1: Short-term memory (fastest decay, λ1 close to 1)
    - L2: Medium-term memory (moderate decay)
    - L3: Long-term memory (slowest decay, λ3 smallest)

References:
    - docs/NUMERICAL_CONTRACTS.md for numerical specifications
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    from ..utils.input_validator import (
        EPS,
        NumericalContractError,
        validate_finite_array,
    )
except ImportError:
    from src.tradepulse.sdk.mlsdm.utils.input_validator import (
        EPS,
        NumericalContractError,
        validate_finite_array,
    )

__all__ = [
    "MultiLevelSynapticMemory",
    "MemoryState",
    "LambdaHierarchyError",
]

logger = logging.getLogger(__name__)


class LambdaHierarchyError(ValueError):
    """Raised when λ decay rates violate the required hierarchy.

    The hierarchy λ3 <= λ2 <= λ1 must be maintained for correct
    memory consolidation behavior.
    """

    def __init__(
        self, lambda_l1: float, lambda_l2: float, lambda_l3: float
    ) -> None:
        self.lambda_l1 = lambda_l1
        self.lambda_l2 = lambda_l2
        self.lambda_l3 = lambda_l3
        super().__init__(
            f"λ hierarchy violation: requires λ3 <= λ2 <= λ1, "
            f"got λ1={lambda_l1:.4f}, λ2={lambda_l2:.4f}, λ3={lambda_l3:.4f}"
        )


@dataclass(frozen=True, slots=True)
class MemoryState:
    """Snapshot of the multi-level memory state.

    Attributes:
        l1: Level 1 (short-term) memory vector.
        l2: Level 2 (medium-term) memory vector.
        l3: Level 3 (long-term) memory vector.
        update_count: Total number of updates applied.
    """

    l1: np.ndarray
    l2: np.ndarray
    l3: np.ndarray
    update_count: int = 0


@dataclass
class MultiLevelSynapticMemory:
    """Three-level synaptic memory with exponential decay.

    Each memory level maintains a running exponential average of input events,
    with different decay rates controlling the timescale of memory retention.

    The update rule for each level is:
        L_i(t+1) = λ_i * L_i(t) + (1 - λ_i) * event

    where λ_i is the decay rate for level i.

    Attributes:
        dim: Dimensionality of memory vectors.
        lambda_l1: Decay rate for L1 (short-term). Range: (0, 1].
        lambda_l2: Decay rate for L2 (medium-term). Range: (0, 1].
        lambda_l3: Decay rate for L3 (long-term). Range: (0, 1].
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Invariants:
        - lambda_l3 <= lambda_l2 <= lambda_l1 (hierarchy)
        - All lambda values in (0, 1]
        - All memory vectors are finite

    Example:
        >>> import numpy as np
        >>> memory = MultiLevelSynapticMemory(dim=128)
        >>> event = np.random.randn(128)
        >>> memory.update(event)
        >>> state = memory.get_state()
        >>> state.l1.shape
        (128,)
    """

    dim: int
    lambda_l1: float = 0.99
    lambda_l2: float = 0.95
    lambda_l3: float = 0.90
    strict_mode: bool = True

    # Internal state (not part of init signature)
    _l1: np.ndarray = field(init=False, repr=False)
    _l2: np.ndarray = field(init=False, repr=False)
    _l3: np.ndarray = field(init=False, repr=False)
    _update_count: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        """Validate parameters and initialize memory vectors."""
        # Validate dimension
        if self.dim <= 0:
            raise ValueError(f"dim must be positive, got {self.dim}")

        # Validate lambda ranges
        for name, value in [
            ("lambda_l1", self.lambda_l1),
            ("lambda_l2", self.lambda_l2),
            ("lambda_l3", self.lambda_l3),
        ]:
            if not (0 < value <= 1):
                raise ValueError(
                    f"{name} must be in (0, 1], got {value}"
                )

        # Validate lambda hierarchy: λ3 <= λ2 <= λ1
        if not (self.lambda_l3 <= self.lambda_l2 <= self.lambda_l1):
            raise LambdaHierarchyError(
                self.lambda_l1, self.lambda_l2, self.lambda_l3
            )

        # Initialize memory vectors to zeros
        self._l1 = np.zeros(self.dim, dtype=np.float64)
        self._l2 = np.zeros(self.dim, dtype=np.float64)
        self._l3 = np.zeros(self.dim, dtype=np.float64)
        self._update_count = 0

        logger.debug(
            "MultiLevelSynapticMemory initialized: dim=%d, λ=(%.3f, %.3f, %.3f), strict=%s",
            self.dim,
            self.lambda_l1,
            self.lambda_l2,
            self.lambda_l3,
            self.strict_mode,
        )

    def update(self, event: np.ndarray) -> None:
        """Update all memory levels with a new event.

        Applies exponential moving average update to each level:
            L_i = λ_i * L_i + (1 - λ_i) * event

        Args:
            event: Input event vector. Must match self.dim and be finite.

        Raises:
            NumericalContractError: If event contains NaN/Inf in strict_mode.
            ValueError: If event dimension doesn't match.

        Note:
            In non-strict mode, NaN/Inf values are replaced with zeros
            before updating.
        """
        if not isinstance(event, np.ndarray):
            event = np.asarray(event, dtype=np.float64)

        # Validate dimensions
        if event.shape != (self.dim,):
            raise ValueError(
                f"event dimension mismatch: expected ({self.dim},), got {event.shape}"
            )

        # Validate finiteness (raises in strict_mode, sanitizes otherwise)
        event = validate_finite_array(
            event,
            "event",
            strict_mode=self.strict_mode,
        )

        # Ensure correct dtype
        if event.dtype != np.float64:
            event = event.astype(np.float64, copy=False)

        # Update each memory level with exponential decay
        # L_i = λ_i * L_i + (1 - λ_i) * event
        self._l1 = self.lambda_l1 * self._l1 + (1 - self.lambda_l1) * event
        self._l2 = self.lambda_l2 * self._l2 + (1 - self.lambda_l2) * event
        self._l3 = self.lambda_l3 * self._l3 + (1 - self.lambda_l3) * event

        self._update_count += 1

    def get_state(self) -> MemoryState:
        """Get current memory state as immutable snapshot.

        Returns:
            MemoryState containing copies of all memory levels.
        """
        return MemoryState(
            l1=self._l1.copy(),
            l2=self._l2.copy(),
            l3=self._l3.copy(),
            update_count=self._update_count,
        )

    def get_combined(self, weights: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
        """Get weighted combination of all memory levels.

        Args:
            weights: Tuple of (w1, w2, w3) weights for each level.

        Returns:
            Combined memory vector: w1*L1 + w2*L2 + w3*L3
        """
        w1, w2, w3 = weights
        return w1 * self._l1 + w2 * self._l2 + w3 * self._l3

    def reset(self) -> None:
        """Reset all memory levels to zeros."""
        self._l1.fill(0.0)
        self._l2.fill(0.0)
        self._l3.fill(0.0)
        self._update_count = 0
        logger.debug("MultiLevelSynapticMemory reset")

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> MultiLevelSynapticMemory:
        """Create memory from configuration dictionary.

        Args:
            config: Configuration with keys:
                - dim: int, vector dimension
                - lambda_l1, lambda_l2, lambda_l3: float, decay rates
                - strict_mode: bool, validation mode

        Returns:
            Configured MultiLevelSynapticMemory instance.

        Example:
            >>> config = {"dim": 64, "lambda_l1": 0.98, "lambda_l2": 0.92, "lambda_l3": 0.85}
            >>> memory = MultiLevelSynapticMemory.from_config(config)
        """
        return cls(
            dim=config.get("dim", 128),
            lambda_l1=config.get("lambda_l1", 0.99),
            lambda_l2=config.get("lambda_l2", 0.95),
            lambda_l3=config.get("lambda_l3", 0.90),
            strict_mode=config.get("strict_mode", True),
        )
