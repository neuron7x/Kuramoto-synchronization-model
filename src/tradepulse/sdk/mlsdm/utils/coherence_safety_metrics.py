# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Coherence and safety metrics for MLSDM with numerical guarantees.

This module provides metrics for assessing vector coherence and safety
in the MLSDM system, with strict numerical stability guarantees.

Numerical Contract:
    - All outputs are finite (never NaN/Inf)
    - Coherence metrics return values in [0, 1]
    - Empty inputs return documented default values
    - Zero vectors are handled safely without division-by-zero

Metrics:
    - cosine_coherence: Cosine similarity between vectors
    - temporal_coherence: Coherence across a time window
    - memory_coherence: Coherence between memory levels
    - safety_score: Combined safety metric

References:
    - docs/NUMERICAL_CONTRACTS.md for numerical specifications
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np

try:
    from .input_validator import EPS, sanitize_array, validate_finite_array
except ImportError:
    from src.tradepulse.sdk.mlsdm.utils.input_validator import (
        EPS,
        sanitize_array,
        validate_finite_array,
    )

__all__ = [
    "CoherenceMetrics",
    "cosine_coherence",
    "temporal_coherence",
    "memory_coherence",
    "safety_score",
    "compute_all_metrics",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoherenceMetrics:
    """Container for coherence and safety metrics.

    All values are guaranteed to be finite and in [0, 1] range.

    Attributes:
        cosine: Cosine coherence between current and reference.
        temporal: Temporal coherence across window.
        memory: Memory level coherence.
        safety: Combined safety score.
    """

    cosine: float
    temporal: float
    memory: float
    safety: float

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "cosine": self.cosine,
            "temporal": self.temporal,
            "memory": self.memory,
            "safety": self.safety,
        }


def _safe_norm(vec: np.ndarray, eps: float = EPS) -> float:
    """Compute L2 norm with safety floor.

    Args:
        vec: Input vector.
        eps: Minimum norm value returned.

    Returns:
        max(||vec||, eps)
    """
    norm = float(np.linalg.norm(vec))
    return max(norm, eps)


def _safe_normalize(vec: np.ndarray, eps: float = EPS) -> np.ndarray:
    """Normalize vector to unit length, safely.

    Returns zero vector for zero/near-zero inputs.

    Args:
        vec: Input vector.
        eps: Threshold for zero detection.

    Returns:
        Unit-normalized vector or zeros.
    """
    norm = float(np.linalg.norm(vec))
    if norm < eps:
        return np.zeros_like(vec)
    return vec / norm


def cosine_coherence(
    vec_a: np.ndarray,
    vec_b: np.ndarray,
    *,
    strict_mode: bool = True,
) -> float:
    """Compute cosine coherence (similarity) between two vectors.

    The cosine coherence is defined as (1 + cos(θ)) / 2, scaled to [0, 1]:
        - 1.0: vectors are identical (θ = 0)
        - 0.5: vectors are orthogonal (θ = π/2)
        - 0.0: vectors are opposite (θ = π)

    Args:
        vec_a: First vector.
        vec_b: Second vector. Must have same shape as vec_a.
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Returns:
        Coherence value in [0, 1]. Returns 0.5 for zero vectors.

    Raises:
        NumericalContractError: If vectors contain NaN/Inf in strict_mode.
        ValueError: If vectors have different shapes.

    Examples:
        >>> import numpy as np
        >>> cosine_coherence(np.array([1, 0]), np.array([1, 0]))
        1.0
        >>> cosine_coherence(np.array([1, 0]), np.array([-1, 0]))
        0.0
        >>> cosine_coherence(np.array([1, 0]), np.array([0, 1]))
        0.5
    """
    vec_a = np.asarray(vec_a, dtype=np.float64)
    vec_b = np.asarray(vec_b, dtype=np.float64)

    if vec_a.shape != vec_b.shape:
        raise ValueError(
            f"Shape mismatch: vec_a {vec_a.shape} != vec_b {vec_b.shape}"
        )

    # Validate finiteness
    vec_a = validate_finite_array(vec_a, "vec_a", strict_mode=strict_mode)
    vec_b = validate_finite_array(vec_b, "vec_b", strict_mode=strict_mode)

    # Handle zero vectors - return neutral coherence
    norm_a = float(np.linalg.norm(vec_a))
    norm_b = float(np.linalg.norm(vec_b))

    if norm_a < EPS or norm_b < EPS:
        logger.debug("Zero vector detected, returning neutral coherence 0.5")
        return 0.5

    # Compute cosine similarity: dot(a, b) / (||a|| * ||b||)
    dot_product = float(np.dot(vec_a, vec_b))
    cos_sim = dot_product / (norm_a * norm_b)

    # Clamp to [-1, 1] to handle numerical errors
    cos_sim = float(np.clip(cos_sim, -1.0, 1.0))

    # Scale to [0, 1]: coherence = (1 + cos_sim) / 2
    coherence = (1.0 + cos_sim) / 2.0

    # Final bounds check (should be unnecessary but ensures contract)
    return float(np.clip(coherence, 0.0, 1.0))


def temporal_coherence(
    window: Sequence[np.ndarray],
    *,
    strict_mode: bool = True,
) -> float:
    """Compute temporal coherence across a window of vectors.

    Measures how consistent vectors are over time by computing average
    pairwise cosine coherence between consecutive vectors.

    Args:
        window: Sequence of vectors (at least 2). Empty or single-element
            windows return 1.0 (maximum coherence by convention).
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Returns:
        Coherence value in [0, 1].
        - Empty window: returns 1.0
        - Single vector: returns 1.0
        - Multiple vectors: average consecutive coherence

    Examples:
        >>> import numpy as np
        >>> # Identical vectors = max coherence
        >>> v = np.array([1.0, 0.0])
        >>> temporal_coherence([v, v, v])
        1.0
        >>> # Empty window
        >>> temporal_coherence([])
        1.0
    """
    if len(window) < 2:
        # Convention: single or empty window has maximum coherence
        return 1.0

    coherences = []
    for i in range(len(window) - 1):
        vec_a = np.asarray(window[i], dtype=np.float64)
        vec_b = np.asarray(window[i + 1], dtype=np.float64)

        # Validate each vector
        vec_a = validate_finite_array(
            vec_a, f"window[{i}]", strict_mode=strict_mode
        )
        vec_b = validate_finite_array(
            vec_b, f"window[{i+1}]", strict_mode=strict_mode
        )

        coh = cosine_coherence(vec_a, vec_b, strict_mode=False)
        coherences.append(coh)

    if not coherences:
        return 1.0

    mean_coherence = float(np.mean(coherences))
    return float(np.clip(mean_coherence, 0.0, 1.0))


def memory_coherence(
    l1: np.ndarray,
    l2: np.ndarray,
    l3: np.ndarray,
    *,
    weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
    strict_mode: bool = True,
) -> float:
    """Compute coherence between memory levels.

    Measures alignment between short-term (L1), medium-term (L2), and
    long-term (L3) memory by weighted average of pairwise coherences.

    Args:
        l1: Level 1 (short-term) memory vector.
        l2: Level 2 (medium-term) memory vector.
        l3: Level 3 (long-term) memory vector.
        weights: Tuple of weights for (L1-L2, L2-L3, L1-L3) pairs.
            Must sum to 1.0.
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Returns:
        Weighted coherence in [0, 1].

    Examples:
        >>> import numpy as np
        >>> v = np.array([1.0, 0.0, 0.0])
        >>> memory_coherence(v, v, v)  # All identical
        1.0
    """
    l1 = np.asarray(l1, dtype=np.float64)
    l2 = np.asarray(l2, dtype=np.float64)
    l3 = np.asarray(l3, dtype=np.float64)

    # Validate all vectors
    l1 = validate_finite_array(l1, "l1", strict_mode=strict_mode)
    l2 = validate_finite_array(l2, "l2", strict_mode=strict_mode)
    l3 = validate_finite_array(l3, "l3", strict_mode=strict_mode)

    # Compute pairwise coherences
    coh_12 = cosine_coherence(l1, l2, strict_mode=False)
    coh_23 = cosine_coherence(l2, l3, strict_mode=False)
    coh_13 = cosine_coherence(l1, l3, strict_mode=False)

    # Weighted average
    w1, w2, w3 = weights
    total_weight = w1 + w2 + w3
    if total_weight < EPS:
        return 0.5  # Neutral if no weights

    weighted_coh = (w1 * coh_12 + w2 * coh_23 + w3 * coh_13) / total_weight

    return float(np.clip(weighted_coh, 0.0, 1.0))


def safety_score(
    current: np.ndarray,
    reference: np.ndarray | None = None,
    *,
    max_deviation: float = 10.0,
    strict_mode: bool = True,
) -> float:
    """Compute safety score based on vector magnitude and deviation.

    The safety score indicates how "safe" the current state is:
    - 1.0: perfectly safe (small magnitude, close to reference)
    - 0.0: maximum danger (large deviation)

    Args:
        current: Current state vector.
        reference: Optional reference/baseline vector. If None, uses zeros.
        max_deviation: Maximum expected deviation for normalization.
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Returns:
        Safety score in [0, 1].

    Examples:
        >>> import numpy as np
        >>> safety_score(np.zeros(3))  # Zero vector = max safety
        1.0
        >>> safety_score(np.array([10.0, 0.0, 0.0]), max_deviation=10.0)
        0.0
    """
    current = np.asarray(current, dtype=np.float64)
    current = validate_finite_array(current, "current", strict_mode=strict_mode)

    if reference is None:
        reference = np.zeros_like(current)
    else:
        reference = np.asarray(reference, dtype=np.float64)
        reference = validate_finite_array(
            reference, "reference", strict_mode=strict_mode
        )

    if current.shape != reference.shape:
        raise ValueError(
            f"Shape mismatch: current {current.shape} != reference {reference.shape}"
        )

    # Compute deviation from reference
    deviation = float(np.linalg.norm(current - reference))

    # Normalize by max_deviation and convert to safety score
    # safety = 1 - (deviation / max_deviation), clamped to [0, 1]
    if max_deviation < EPS:
        max_deviation = EPS

    normalized_deviation = deviation / max_deviation
    safety = 1.0 - min(normalized_deviation, 1.0)

    return float(np.clip(safety, 0.0, 1.0))


def compute_all_metrics(
    current: np.ndarray,
    reference: np.ndarray | None = None,
    window: Sequence[np.ndarray] | None = None,
    memory_levels: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
    *,
    strict_mode: bool = True,
) -> CoherenceMetrics:
    """Compute all coherence and safety metrics.

    Convenience function that computes all metrics in one call.

    Args:
        current: Current state vector.
        reference: Reference vector for cosine coherence. Uses zeros if None.
        window: Vector window for temporal coherence. Uses empty if None.
        memory_levels: (L1, L2, L3) tuple for memory coherence. Uses zeros if None.
        strict_mode: If True, raise on NaN/Inf. If False, sanitize.

    Returns:
        CoherenceMetrics with all values guaranteed in [0, 1].
    """
    current = np.asarray(current, dtype=np.float64)
    current = validate_finite_array(current, "current", strict_mode=strict_mode)

    # Cosine coherence with reference
    if reference is None:
        reference = np.zeros_like(current)
    cos_coh = cosine_coherence(current, reference, strict_mode=False)

    # Temporal coherence
    if window is None or len(window) == 0:
        temp_coh = 1.0
    else:
        temp_coh = temporal_coherence(window, strict_mode=False)

    # Memory coherence
    if memory_levels is None:
        mem_coh = 1.0
    else:
        l1, l2, l3 = memory_levels
        mem_coh = memory_coherence(l1, l2, l3, strict_mode=False)

    # Safety score
    safe = safety_score(current, reference, strict_mode=False)

    return CoherenceMetrics(
        cosine=cos_coh,
        temporal=temp_coh,
        memory=mem_coh,
        safety=safe,
    )
