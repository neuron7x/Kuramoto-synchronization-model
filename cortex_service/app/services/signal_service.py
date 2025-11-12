"""Service for signal computation business logic."""

from __future__ import annotations

from typing import Iterable

from ..config import SignalSettings
from ..core.signals import FeatureObservation, Signal, build_signal_ensemble
from ..errors import ValidationError
from ..logger import get_logger
from ..metrics import SIGNAL_DISTRIBUTION, SIGNAL_STRENGTH
from ..sync.ensemble import aggregate_strength, kuramoto_order_parameter

logger = get_logger(__name__)


class SignalService:
    """Service layer for signal computation operations."""

    def __init__(self, settings: SignalSettings) -> None:
        """Initialize the signal service.

        Args:
            settings: Signal computation settings
        """
        self._settings = settings

    def compute_signals(
        self, features: Iterable[FeatureObservation]
    ) -> tuple[list[Signal], float, float]:
        """Compute signals from features.

        Args:
            features: Iterator of feature observations

        Returns:
            Tuple of (signals, ensemble_strength, synchrony)

        Raises:
            ValidationError: If features are invalid
        """
        feature_list = list(features)
        if not feature_list:
            raise ValidationError(
                "At least one feature is required", details={"feature_count": 0}
            )

        try:
            signals = build_signal_ensemble(feature_list, self._settings)
            ensemble_strength = aggregate_strength(signals)
            synchrony = kuramoto_order_parameter(signals)

            # Record metrics
            for signal in signals:
                SIGNAL_STRENGTH.observe(signal.strength)
                SIGNAL_DISTRIBUTION.observe(signal.strength)

            logger.debug(
                "Computed signals",
                extra={
                    "signal_count": len(signals),
                    "ensemble_strength": ensemble_strength,
                    "synchrony": synchrony,
                },
            )

            return signals, ensemble_strength, synchrony
        except ValueError as exc:
            raise ValidationError(
                f"Invalid features for signal computation: {exc}"
            ) from exc


__all__ = ["SignalService"]
