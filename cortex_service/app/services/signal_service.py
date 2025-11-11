"""Signal computation service layer.

This module provides business logic for signal ensemble computation,
separated from the API layer for better testability and reusability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..config import SignalSettings
from ..core.signals import FeatureObservation, Signal, build_signal_ensemble
from ..errors import SignalComputationError
from ..sync.ensemble import aggregate_strength, kuramoto_order_parameter


@dataclass(frozen=True, slots=True)
class SignalEnsembleResult:
    """Result of signal ensemble computation.
    
    Attributes:
        signals: List of computed signals for each instrument
        ensemble_strength: Aggregate strength across all signals
        synchrony: Kuramoto order parameter measuring phase coherence
    """
    
    signals: Sequence[Signal]
    ensemble_strength: float
    synchrony: float


def compute_signal_ensemble(
    features: Sequence[FeatureObservation],
    settings: SignalSettings,
) -> SignalEnsembleResult:
    """Compute signal ensemble from feature observations.
    
    This is the main entry point for signal computation. It:
    1. Groups features by instrument
    2. Computes signals for each instrument
    3. Calculates ensemble-level metrics (strength and synchrony)
    
    Args:
        features: List of feature observations
        settings: Signal computation parameters
        
    Returns:
        Signal ensemble result with signals and metrics
        
    Raises:
        SignalComputationError: If computation fails
    """
    if not features:
        raise SignalComputationError(
            "Cannot compute signals from empty feature list",
            code="EmptyFeatureList",
        )
    
    try:
        signals = build_signal_ensemble(features, settings)
        
        if not signals:
            raise SignalComputationError(
                "Signal computation produced no results",
                code="NoSignalsProduced",
            )
        
        ensemble_strength = aggregate_strength(signals)
        synchrony = kuramoto_order_parameter(signals)
        
        return SignalEnsembleResult(
            signals=signals,
            ensemble_strength=ensemble_strength,
            synchrony=synchrony,
        )
    except Exception as exc:
        if isinstance(exc, SignalComputationError):
            raise
        raise SignalComputationError(
            f"Signal computation failed: {exc}",
            code="ComputationFailed",
        ) from exc


__all__ = [
    "SignalEnsembleResult",
    "compute_signal_ensemble",
]
