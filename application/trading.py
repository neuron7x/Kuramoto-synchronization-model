"""Mapping utilities between domain objects and DTOs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from domain import Order, Position, Signal


def signal_to_dto(signal: Signal) -> dict[str, Any]:
    """Convert a :class:`domain.signal.Signal` into a DTO."""

    return signal.to_dict()


def order_to_dto(order: Order) -> dict[str, Any]:
    """Convert a :class:`domain.order.Order` into primitives."""

    return order.to_dict()


def position_to_dto(position: Position) -> dict[str, Any]:
    """Convert a :class:`domain.position.Position` into primitives."""

    return position.to_dict()


def dto_to_signal(data: Mapping[str, Any]) -> Signal:
    """Instantiate a domain signal from serialized data."""

    raw_ts = data.get("timestamp")
    confidence_raw = data.get("confidence", 0.0)
    confidence = 0.0 if confidence_raw is None else float(confidence_raw)
    if isinstance(raw_ts, str):
        cleaned_ts = raw_ts.replace("Z", "+00:00") if raw_ts.endswith("Z") else raw_ts
        timestamp = datetime.fromisoformat(cleaned_ts)
    elif isinstance(raw_ts, datetime):
        timestamp = raw_ts
    elif raw_ts is None:
        timestamp = datetime.now(timezone.utc)
    else:  # pragma: no cover - defensive branch
        raise TypeError("timestamp must be str, datetime, or None")

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return Signal(
        symbol=str(data["symbol"]),
        action=data["action"],
        confidence=confidence,
        timestamp=timestamp,
        rationale=data.get("rationale"),
        metadata=data.get("metadata"),
    )


__all__ = ["signal_to_dto", "order_to_dto", "position_to_dto", "dto_to_signal"]
