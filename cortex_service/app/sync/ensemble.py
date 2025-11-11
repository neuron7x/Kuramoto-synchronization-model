"""Synchronization utilities for the signal ensemble.

This module provides ensemble-level metrics for signal aggregation,
including phase coherence and aggregate strength measurements.
"""

from __future__ import annotations

import cmath
from typing import Sequence

from ..core.signals import Signal


def kuramoto_order_parameter(signals: Sequence[Signal]) -> float:
    """Compute the Kuramoto order parameter for the signal ensemble.
    
    The Kuramoto order parameter measures phase synchronization across
    signals, with values ranging from 0 (no synchronization) to 1
    (perfect synchronization).
    
    This metric is numerically stable and uses complex exponentials
    to compute the phase coherence:
    
        r = |1/N * Σ exp(i*θ_k)| where θ_k is signal strength
    
    Args:
        signals: Sequence of signals to analyze
        
    Returns:
        Kuramoto order parameter in [0, 1]
    """
    if not signals:
        return 0.0
    
    # Interpret signal strength as phase (numerically stable)
    phases = [signal.strength for signal in signals]
    
    # Compute complex sum and magnitude (vector aggregation)
    complex_sum = sum(cmath.exp(1j * phase) for phase in phases)
    
    # Normalize by number of signals
    return abs(complex_sum) / len(phases)


def aggregate_strength(signals: Sequence[Signal]) -> float:
    """Compute the mean strength across all signals.
    
    Provides a simple aggregate measure of signal conviction
    for monitoring and gating decisions.
    
    Args:
        signals: Sequence of signals to aggregate
        
    Returns:
        Mean signal strength
    """
    if not signals:
        return 0.0
    
    # Use numerically stable summation (Kahan not needed for typical sizes)
    return sum(signal.strength for signal in signals) / len(signals)


__all__ = ["aggregate_strength", "kuramoto_order_parameter"]
