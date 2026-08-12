"""Engine interface for CoherenceBridge signal providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SignalEngine(ABC):
    """Interface that GeoSync physics kernel must implement."""

    @property
    @abstractmethod
    def instruments(self) -> list[str]:
        """Return list of active instruments."""
        ...

    @abstractmethod
    def get_signal(self, instrument: str) -> dict[str, object] | None:
        """
        Return current signal for instrument.

        Must return dict with keys:
            timestamp_ns: int (UTC nanoseconds)
            instrument: str
            gamma: float
            order_parameter_R: float
            ricci_curvature: float
            lyapunov_max: float
            regime: str (COHERENT|METASTABLE|DECOHERENT|CRITICAL|UNKNOWN)
            regime_confidence: float
            regime_duration_s: float
            signal_strength: float
            risk_scalar: float
            sequence_number: int (monotonically increasing per instrument)

        Return None if instrument not available.
        """
        ...
