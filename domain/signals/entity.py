"""Immutable trading signal entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .value_objects import SignalAction


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    """Immutable provenance metadata describing the originating model."""

    model_id: str
    model_version: str
    model_hash: str
    training_timestamp: datetime

    def __post_init__(self) -> None:  # pragma: no cover - exercised via Signal
        if not self.model_id:
            raise ValueError("model_id must be provided")
        if not self.model_version:
            raise ValueError("model_version must be provided")
        if not self.model_hash:
            raise ValueError("model_hash must be provided")
        if not isinstance(self.training_timestamp, datetime):
            raise TypeError("training_timestamp must be a datetime")
        if self.training_timestamp.tzinfo is None:
            raise ValueError("training_timestamp must be timezone-aware")


@dataclass(slots=True)
class Signal:
    """Immutable trading signal produced by strategies."""

    symbol: str
    action: SignalAction | str
    confidence: float
    model_metadata: ModelMetadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be provided")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        self.action = SignalAction(self.action)
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(self.model_metadata, ModelMetadata):
            raise TypeError("model_metadata must be a ModelMetadata instance")
        if isinstance(self.metadata, Mapping):
            self.metadata = dict(self.metadata)
        elif self.metadata is None:
            self.metadata = {}
        else:
            raise TypeError("metadata must be a mapping")

    def with_confidence(self, confidence: float) -> "Signal":
        """Return a copy with a different confidence score."""

        return Signal(
            symbol=self.symbol,
            action=self.action,
            confidence=confidence,
            model_metadata=self.model_metadata,
            timestamp=self.timestamp,
            rationale=self.rationale,
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly representation."""

        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "confidence": float(self.confidence),
            "model_id": self.model_metadata.model_id,
            "model_version": self.model_metadata.model_version,
            "model_hash": self.model_metadata.model_hash,
            "training_timestamp": self.model_metadata.training_timestamp.isoformat(),
            "timestamp": self.timestamp.isoformat(),
            "rationale": self.rationale,
            "metadata": dict(self.metadata or {}),
        }


__all__ = ["ModelMetadata", "Signal"]
