"""Utilities for MLSDM."""

from __future__ import annotations

from .coherence_safety_metrics import (
    CoherenceMetrics,
    compute_all_metrics,
    cosine_coherence,
    memory_coherence,
    safety_score,
    temporal_coherence,
)
from .config_loader import ConfigLoader
from .input_validator import (
    EPS,
    NumericalContractError,
    ensure_dtype,
    safe_unit_normalize,
    sanitize_array,
    validate_finite_array,
)

__all__ = [
    # Config
    "ConfigLoader",
    # Input validation
    "EPS",
    "NumericalContractError",
    "validate_finite_array",
    "safe_unit_normalize",
    "ensure_dtype",
    "sanitize_array",
    # Coherence metrics
    "CoherenceMetrics",
    "cosine_coherence",
    "temporal_coherence",
    "memory_coherence",
    "safety_score",
    "compute_all_metrics",
]
