"""Immutable trading signal entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .value_objects import SignalAction


@dataclass(slots=True)
class Signal:
    """Immutable trading signal produced by strategies."""

    symbol: str
    action: SignalAction | str
    confidence: float
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
            timestamp=self.timestamp,
            rationale=self.rationale,
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly representation."""
        # action is converted to SignalAction in __post_init__, but mypy sees the union type
        action_value = (
            self.action.value if isinstance(self.action, SignalAction) else self.action
        )
        return {
            "symbol": self.symbol,
            "action": action_value,
            "confidence": float(self.confidence),
            "timestamp": self.timestamp.isoformat(),
            "rationale": self.rationale,
            "metadata": dict(self.metadata or {}),
        }


__all__ = ["Signal"]
